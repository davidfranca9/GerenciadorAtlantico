from __future__ import annotations

import html
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from docx import Document
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Agendamento, AgendamentoItem, CartaFreteEnviada, Pedido
from ..servicos import carta_frete, emails_agendamento, saldo_pedidos
from ..servicos.comunicacao import imagem_assinatura_inline, montar_autorizacao_agendamento, send_email_message
from ..servicos.documentos import gerar_autorizacao_xlsx
from ..servicos.oc_html import gerar_oc_pdf_html
from ..servicos.pdf_convert import docx_to_pdf

router = APIRouter(dependencies=[Depends(get_current_user)])

# Destinatarios e modelo da carta frete moram no servico, que o envio
# agendado tambem usa.
RECIPIENTS_CARTA_FRETE = carta_frete.DESTINATARIOS
RECIPIENTS_HERINGER = [
    "expedicao.candeias@heringer.com.br",
    "faturamento.candeias@heringer.com.br",
]
RECIPIENTS_FERTIMAX = [
    "agendamento@fertimaxi.com.br",
    "luan.santos@fertimaxi.com.br",
    "paulo.moura@fertimaxi.com.br",
]

DADOS_DIR = Path(__file__).resolve().parents[2] / "dados"
SUPPLIERS_OC = {"AFL", "HERINGER"}
TEMPLATE_CF = carta_frete.TEMPLATE_CF
# Modelo da Fertimaxi: cartao vertical, um bloco por pedido. So o sistema web
# usa este; o app desktop antigo continua com o dados/ da raiz.
TEMPLATE_AUTORIZACAO = DADOS_DIR / "Autorizacao de Carregamento FERTIMAXI.xlsx"


def _safe_filename(nome: str) -> str:
    safe = re.sub(r'[\\/*?:"<>|]', "", (nome or "").strip())
    return safe or "Motorista"


def _client_name_from_produtos(produtos: list) -> str:
    for p in produtos:
        cliente = (p.get("cliente") if isinstance(p, dict) else p.cliente) or ""
        if cliente.strip():
            return _safe_filename(cliente)
    return "Cliente"


class Produto(BaseModel):
    contrato: str = ""
    produto: str = ""
    embalagem: str = ""
    toneladas: str = ""
    cidade: str = ""
    cliente: str = ""
    pedido_id: Optional[int] = None


class OrdemColetaRequest(BaseModel):
    template: str = "AFL"
    produtos: list[Produto]
    cpf: str = ""
    nome: str = ""
    cnh: str = ""
    fone: str = ""
    placa1: str = ""
    placa2: str = ""
    placa3: str = ""
    modelo_veiculo: str = ""
    data_carregamento: str = ""
    observacoes: str = ""
    agendamento_id: Optional[int] = None
    # So pros testes: manda pro endereco de teste em vez da fabrica, com
    # [TESTE] no assunto. As telas nunca mandam isso.
    teste: bool = False

class CartaFreteRequest(BaseModel):
    DATA: str = ""
    CONDUTOR: str = ""
    CPF: str = ""
    PLACA_CAVALO: str = ""
    VALOR_FRETE: str = ""
    AUTORIZACAO_NUM: str = ""
    formato: str = "docx"


def _nome_do_documento(payload: OrdemColetaRequest, produtos: list) -> str:
    """Nome que vai no arquivo da autorizacao (e no anexo do e-mail).

    Enquanto o agendamento nao tem motorista, a autorizacao e do cliente;
    quando o motorista e definido, ela passa a sair no nome dele - e ele que
    chega na portaria da fabrica.
    """
    if (payload.nome or "").strip():
        return _safe_filename(payload.nome)
    return _client_name_from_produtos(produtos)


def _gerar_autorizacao(payload: OrdemColetaRequest, produtos_dict: list, xlsx_path: str) -> None:
    """Preenche o modelo da Fertimaxi com os dados do motorista e das placas."""
    gerar_autorizacao_xlsx(
        str(TEMPLATE_AUTORIZACAO),
        xlsx_path,
        produtos_dict,
        motorista=payload.nome,
        cpf=payload.cpf,
        telefone=payload.fone,
        placas=(payload.placa1, payload.placa2, payload.placa3),
        modelo_veiculo=payload.modelo_veiculo,
    )


def _gerar_oc_arquivos(payload: OrdemColetaRequest, tmp_dir: str) -> dict:
    """Gera a Ordem de Coleta (PDF via HTML/WeasyPrint) e, para fornecedores
    que nao sejam Heringer, tambem a Autorizacao de Coleta (xlsx). Retorna um
    dict com os caminhos gerados: {"pdf": ..., "xlsx": ... | None}."""
    if payload.template.upper() not in SUPPLIERS_OC:
        raise HTTPException(status_code=400, detail=f"Fornecedor '{payload.template}' invalido")

    safe_name = _safe_filename(payload.nome)
    produtos_dict = [p.model_dump() for p in payload.produtos]

    pdf_path = os.path.join(tmp_dir, f"Ordem de Coleta_{safe_name}.pdf")
    gerar_oc_pdf_html(
        payload.template,
        produtos_dict,
        payload.cpf,
        payload.nome,
        payload.cnh,
        payload.fone,
        payload.placa1,
        payload.placa2,
        payload.placa3,
        payload.data_carregamento,
        pdf_path,
        observacoes=payload.observacoes,
    )

    xlsx_path = None
    if payload.template.upper() != "HERINGER" and TEMPLATE_AUTORIZACAO.exists():
        nome_documento = _nome_do_documento(payload, produtos_dict)
        xlsx_path = os.path.join(tmp_dir, f"Autorizacao de carregamento_{nome_documento}.xlsx")
        _gerar_autorizacao(payload, produtos_dict, xlsx_path)

    return {"pdf": pdf_path, "xlsx": xlsx_path, "safe_name": safe_name}


def _salvar_agendamento_oc(
    db: Session,
    payload: OrdemColetaRequest,
    produtos_dict: list[dict],
    arquivos: dict,
) -> Agendamento:
    """Cria ou atualiza (quando payload.agendamento_id e informado) o registro
    da Ordem de Coleta no banco, funcionando como o "banco de OCs geradas"."""
    if payload.agendamento_id:
        agendamento = db.get(Agendamento, payload.agendamento_id)
        if agendamento is None:
            raise HTTPException(status_code=404, detail="Ordem de Coleta nao encontrada para edicao")
    else:
        agendamento = Agendamento()
        db.add(agendamento)

    agendamento.supplier = "Heringer" if payload.template.upper() == "HERINGER" else "Fertimaxi"
    agendamento.loading_date = payload.data_carregamento
    agendamento.driver_name = payload.nome.strip()
    agendamento.driver_cpf = payload.cpf.strip()
    agendamento.driver_phone = payload.fone.strip()
    agendamento.cnh = payload.cnh.strip()
    agendamento.plate_cavalo = payload.placa1.strip()
    agendamento.plate_carreta1 = payload.placa2.strip()
    agendamento.plate_carreta2 = payload.placa3.strip()
    agendamento.modelo_veiculo = payload.modelo_veiculo.strip()
    agendamento.observacoes = payload.observacoes.strip()
    # Itens ligados ao pedido (pelo id, ou pelo numero + produto) e a barra
    # acertada pela DIFERENCA: gerar a O.C. e a autorizacao em sequencia nao
    # desconta duas vezes, e mudar a tonelada na edicao ajusta o saldo.
    saldo_pedidos.gravar_itens(db, agendamento, [
        {
            "pedido": p.get("contrato", ""),
            "cliente": p.get("cliente", ""),
            "produto": p.get("produto", ""),
            "cidade": p.get("cidade", ""),
            "embalagem": p.get("embalagem", ""),
            "toneladas": _safe_float(p.get("toneladas")),
            "pedido_id": p.get("pedido_id"),
        }
        for p in produtos_dict
    ])
    agendamento.total_items = len(agendamento.itens)
    agendamento.total_tons = sum(i.toneladas for i in agendamento.itens)
    if arquivos.get("pdf"):
        agendamento.oc_pdf_path = arquivos["pdf"]
    if arquivos.get("xlsx"):
        agendamento.planilha_path = arquivos["xlsx"]
    agendamento.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(agendamento)
    return agendamento


@router.post("/ordens-coleta/gerar")
def gerar_ordem_coleta(payload: OrdemColetaRequest, db: Session = Depends(get_db)):
    tmp_dir = tempfile.mkdtemp()
    try:
        arquivos = _gerar_oc_arquivos(payload, tmp_dir)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF da O.C.: {exc!r}")
    safe_name = arquivos["safe_name"]
    produtos_dict = [p.model_dump() for p in payload.produtos]
    agendamento = _salvar_agendamento_oc(db, payload, produtos_dict, arquivos)
    return FileResponse(
        arquivos["pdf"],
        filename=f"Ordem de Coleta_{safe_name}.pdf",
        media_type="application/pdf",
        headers={"X-Agendamento-Id": str(agendamento.id)},
    )


@router.post("/ordens-coleta/gerar-autorizacao")
def gerar_autorizacao_coleta(payload: OrdemColetaRequest, db: Session = Depends(get_db)):
    if payload.template.upper() == "HERINGER":
        raise HTTPException(status_code=400, detail="Autorizacao de Coleta nao se aplica ao fornecedor Heringer")
    if not TEMPLATE_AUTORIZACAO.exists():
        raise HTTPException(status_code=400, detail="Template de Autorizacao de Coleta nao encontrado")

    tmp_dir = tempfile.mkdtemp()
    produtos_dict = [p.model_dump() for p in payload.produtos]
    nome_documento = _nome_do_documento(payload, produtos_dict)
    xlsx_path = os.path.join(tmp_dir, f"Autorizacao de carregamento_{nome_documento}.xlsx")
    _gerar_autorizacao(payload, produtos_dict, xlsx_path)
    agendamento = _salvar_agendamento_oc(db, payload, produtos_dict, {"xlsx": xlsx_path})
    return FileResponse(
        xlsx_path,
        filename=f"Autorizacao de carregamento_{nome_documento}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"X-Agendamento-Id": str(agendamento.id)},
    )


def _assunto_teste(assunto: str, teste: bool) -> str:
    return f"[TESTE] {assunto}" if teste else assunto


@router.post("/ordens-coleta/enviar-autorizacao-email")
def enviar_autorizacao_email(payload: OrdemColetaRequest, db: Session = Depends(get_db)):
    """Manda a Autorizacao de Coleta (planilha) direto pra Fertimaxi, sem
    passar pela Ordem de Coleta - usado na tela de Contratos, onde o
    motorista/placa ainda podem nao estar definidos.

    Registra o agendamento: e nele que, depois, o motorista e incluido e sai
    o e-mail de inclusao de placas. Antes nada era gravado aqui, e o pedido
    enviado sem motorista nao aparecia em Agendamentos.
    """
    if not payload.produtos:
        raise HTTPException(status_code=400, detail="Selecione ao menos um produto/pedido")
    if payload.template.upper() == "HERINGER":
        raise HTTPException(status_code=400, detail="Autorizacao de Coleta nao se aplica ao fornecedor Heringer")
    if not TEMPLATE_AUTORIZACAO.exists():
        raise HTTPException(status_code=400, detail="Template de Autorizacao de Coleta nao encontrado")

    tmp_dir = tempfile.mkdtemp()
    produtos_dict = [p.model_dump() for p in payload.produtos]
    nome_documento = _nome_do_documento(payload, produtos_dict)
    xlsx_path = os.path.join(tmp_dir, f"Autorizacao de carregamento_{nome_documento}.xlsx")
    _gerar_autorizacao(payload, produtos_dict, xlsx_path)

    destinatarios = emails_agendamento.destino(RECIPIENTS_FERTIMAX, True) if payload.teste else RECIPIENTS_FERTIMAX
    vistos: set[tuple[str, str]] = set()
    assuntos_enviados: list[str] = []
    for produto in payload.produtos:
        cliente, pedido = produto.cliente.strip(), produto.contrato.strip()
        if not cliente or not pedido or (cliente, pedido) in vistos:
            continue
        vistos.add((cliente, pedido))
        titulo, corpo = montar_autorizacao_agendamento(cliente, pedido, payload.data_carregamento, motorista=payload.nome)
        titulo = _assunto_teste(titulo, payload.teste)
        try:
            send_email_message(destinatarios, titulo, corpo, [xlsx_path], imagens_inline=imagem_assinatura_inline())
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Falha ao enviar e-mail: {exc}")
        assuntos_enviados.append(titulo)

    if not assuntos_enviados:
        raise HTTPException(status_code=400, detail="Nenhum produto com cliente e pedido preenchidos pra enviar")

    agendamento = _salvar_agendamento_oc(db, payload, produtos_dict, {"xlsx": xlsx_path})
    agendamento.email_subject = "; ".join(assuntos_enviados)[:500]
    agendamento.email_recipients = ", ".join(destinatarios)[:1000]
    db.commit()
    return {"ok": True, "email_enviado_para": destinatarios, "agendamento_id": agendamento.id}


class EnviarOrdemColetaRequest(OrdemColetaRequest):
    roteiro: str = ""
    localizador: str = ""
    contato_cliente: str = ""


@router.post("/ordens-coleta/enviar-email")
def enviar_ordem_coleta_email(payload: EnviarOrdemColetaRequest, db: Session = Depends(get_db)):
    if not payload.produtos:
        raise HTTPException(status_code=400, detail="Selecione ao menos um produto/pedido")
    if not payload.nome.strip():
        raise HTTPException(status_code=400, detail="Nome do motorista e obrigatorio")

    supplier_label = "Heringer" if payload.template.upper() == "HERINGER" else "Fertimaxi"
    recipients = RECIPIENTS_HERINGER if supplier_label == "Heringer" else RECIPIENTS_FERTIMAX
    if payload.teste:
        recipients = emails_agendamento.destino(recipients, True)

    tmp_dir = tempfile.mkdtemp()
    arquivos = _gerar_oc_arquivos(payload, tmp_dir)

    if supplier_label == "Fertimaxi":
        # Mesmo modelo (cliente + pedido + assinatura) usado no "Novo
        # Agendamento" rapido - um e-mail por pedido/cliente distinto, com
        # a Autorizacao de Coleta (planilha) anexada, nao a O.C. em si.
        anexos = [arquivos["xlsx"]] if arquivos["xlsx"] else []
        vistos: set[tuple[str, str]] = set()
        assuntos_enviados: list[str] = []
        for produto in payload.produtos:
            cliente, pedido = produto.cliente.strip(), produto.contrato.strip()
            if not cliente or not pedido or (cliente, pedido) in vistos:
                continue
            vistos.add((cliente, pedido))
            titulo, corpo = montar_autorizacao_agendamento(cliente, pedido, payload.data_carregamento, motorista=payload.nome)
            try:
                send_email_message(recipients, _assunto_teste(titulo, payload.teste), corpo, anexos, imagens_inline=imagem_assinatura_inline())
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Falha ao enviar e-mail: {exc}")
            assuntos_enviados.append(titulo)
        subject = "; ".join(assuntos_enviados) or f"Autorizacao de {payload.nome.strip()}"
    else:
        anexos = [arquivos["pdf"]]
        if arquivos["xlsx"]:
            anexos.append(arquivos["xlsx"])
        subject = f"Autorizacao de {payload.nome.strip()} - Placa {payload.placa1.strip() or 'N/A'}"
        detail_blocks = []
        if payload.roteiro.strip():
            detail_blocks.append(f"<p><b>Roteiro:</b><br>{html.escape(payload.roteiro).replace(chr(10), '<br>')}</p>")
        if payload.contato_cliente.strip():
            detail_blocks.append(f"<p><b>Contato do Cliente:</b> {html.escape(payload.contato_cliente)}</p>")
        body = f"""
        <html><body>
        <p>Favor agendar motorista para {html.escape(payload.data_carregamento)}.</p>
        {''.join(detail_blocks)}
        <p>Atenciosamente,<br><b>Setor - Expedicao</b><br>ATLANTICO FERTLOG SERVICOS &amp; TRANSPORTES</p>
        </body></html>
        """
        try:
            send_email_message(recipients, _assunto_teste(subject, payload.teste), body, anexos)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Falha ao enviar e-mail: {exc}")

    produtos_dict = [p.model_dump() for p in payload.produtos]
    agendamento = _salvar_agendamento_oc(db, payload, produtos_dict, arquivos)
    agendamento.roteiro = payload.roteiro.strip()
    agendamento.localizador = payload.localizador.strip()
    agendamento.contato_cliente = payload.contato_cliente.strip()
    agendamento.email_subject = subject
    agendamento.email_recipients = ", ".join(recipients)
    db.commit()
    db.refresh(agendamento)

    return {"ok": True, "agendamento_id": agendamento.id, "email_enviado_para": recipients}


def _safe_float(value) -> float:
    try:
        text = str(value).strip().replace(",", ".")
        return float(text) if text else 0.0
    except (TypeError, ValueError):
        return 0.0


@router.post("/cartas-frete/gerar")
def gerar_carta_frete(payload: CartaFreteRequest):
    """Baixar: gera o documento e devolve, sem mandar e-mail nenhum."""
    dados = carta_frete.dados_de(payload.model_dump())
    try:
        docx_path = carta_frete.gerar_docx(dados)
    except carta_frete.CartaFreteInvalida as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    nome = carta_frete.nome_do_arquivo(dados)
    if payload.formato.lower() == "pdf":
        try:
            pdf_path = docx_to_pdf(docx_path)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Falha ao gerar o PDF: {exc}")
        return FileResponse(pdf_path, filename=f"{nome}.pdf", media_type="application/pdf")

    return FileResponse(
        docx_path,
        filename=f"{nome}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.post("/cartas-frete/enviar-email")
def enviar_carta_frete_email(payload: CartaFreteRequest, db: Session = Depends(get_db)):
    try:
        carta_frete.enviar_agora(db, payload.model_dump())
    except carta_frete.CartaFreteInvalida as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao enviar e-mail: {exc}")
    return {"ok": True, "email_enviado_para": carta_frete.DESTINATARIOS}


class AgendarCartaFreteRequest(CartaFreteRequest):
    # Com fuso (o que a tela manda) vira UTC; sem fuso, ja e tratado como UTC.
    enviar_em: datetime


@router.post("/cartas-frete/agendar")
def agendar_carta_frete(payload: AgendarCartaFreteRequest, db: Session = Depends(get_db)):
    """Agenda o envio do e-mail: o sistema manda sozinho na hora marcada."""
    quando = payload.enviar_em
    if quando.tzinfo is not None:
        quando = quando.astimezone(timezone.utc).replace(tzinfo=None)
    try:
        registro = carta_frete.agendar(db, payload.model_dump(exclude={"enviar_em", "formato"}), quando)
    except carta_frete.CartaFreteInvalida as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _carta_para_dict(registro)


@router.post("/cartas-frete/{carta_id}/cancelar")
def cancelar_carta_frete(carta_id: int, db: Session = Depends(get_db)):
    """Cancela um envio agendado que ainda nao saiu."""
    try:
        registro = carta_frete.cancelar(db, carta_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Autorização de abastecimento não encontrada")
    except carta_frete.CartaFreteInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _carta_para_dict(registro)


def _carta_para_dict(r: CartaFreteEnviada) -> dict:
    return {
        "id": r.id,
        "data": r.data,
        "condutor": r.condutor,
        "cpf": r.cpf,
        "placa_cavalo": r.placa_cavalo,
        "valor_frete": r.valor_frete,
        "autorizacao_num": r.autorizacao_num,
        "destinatarios": r.destinatarios,
        "status": r.status,
        "created_at": r.created_at,
        "agendada_para": r.agendada_para,
        "enviada_em": r.enviada_em,
        "erro": r.erro,
    }


@router.get("/cartas-frete")
def listar_cartas_frete(db: Session = Depends(get_db)):
    registros = db.query(CartaFreteEnviada).order_by(CartaFreteEnviada.created_at.desc()).all()
    return [_carta_para_dict(r) for r in registros]


@router.delete("/cartas-frete/{carta_id}")
def excluir_carta_frete(carta_id: int, db: Session = Depends(get_db)):
    registro = db.get(CartaFreteEnviada, carta_id)
    if registro is None:
        raise HTTPException(status_code=404, detail="Registro nao encontrado")
    db.delete(registro)
    db.commit()
    return {"ok": True}
