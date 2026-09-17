from __future__ import annotations

import logging
import tempfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import STATUS_AGENDAMENTO, Agendamento, AgendamentoEmail, AgendamentoItem, Cidade, Pedido
from ..servicos import emails_agendamento, ocr, saldo_pedidos
from ..servicos.comunicacao import imagem_assinatura_inline, montar_autorizacao_agendamento, send_email_message
from .documentos import Produto, OrdemColetaRequest, _gerar_oc_arquivos

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agendamentos", tags=["agendamentos"], dependencies=[Depends(get_current_user)])

RECIPIENTES_AUTORIZACAO_FERTIMAXI = [
    "atlanticofertlog.comercial@gmail.com",
    "luan.santos@fertimaxi.com.br",
    "paulo.moura@fertimaxi.com.br",
]


def _eh_fertimaxi(supplier: str) -> bool:
    return (supplier or "").strip().lower() in {"afl", "fertimaxi", "fertimax"}


def _gerar_anexos_oc(agendamento: Agendamento) -> list[str]:
    """Gera a Autorizacao de Coleta (planilha) do agendamento, pra anexar no
    e-mail - so a autorizacao, nao a O.C. em si (que tem seu proprio botao
    de download na tela de Ordem de Coleta)."""
    template = "HERINGER" if agendamento.supplier.strip().lower() == "heringer" else "AFL"
    payload = OrdemColetaRequest(
        template=template,
        produtos=[
            Produto(
                contrato=item.pedido,
                produto=item.produto,
                embalagem=item.embalagem,
                toneladas=str(item.toneladas),
                cidade=item.cidade,
                cliente=item.cliente,
                pedido_id=item.pedido_ref_id,
            )
            for item in agendamento.itens
        ],
        cpf=agendamento.driver_cpf,
        nome=agendamento.driver_name,
        cnh=agendamento.cnh,
        fone=agendamento.driver_phone,
        placa1=agendamento.plate_cavalo,
        placa2=agendamento.plate_carreta1,
        placa3=agendamento.plate_carreta2,
        modelo_veiculo=agendamento.modelo_veiculo,
        data_carregamento=agendamento.loading_date,
        observacoes=agendamento.observacoes,
    )
    arquivos = _gerar_oc_arquivos(payload, tempfile.mkdtemp())
    return [arquivos["xlsx"]] if arquivos.get("xlsx") else []


def _enviar_autorizacoes_agendamento_fertimaxi(agendamento: Agendamento, teste: bool = False) -> None:
    """Pra cada pedido/cliente distinto do agendamento, manda um e-mail pra
    Fertimaxi solicitando a autorizacao de agendamento, com a Autorizacao
    de Coleta (planilha) anexada. Falha no envio nao derruba a criacao do
    agendamento - so fica registrada no log."""
    try:
        anexos = _gerar_anexos_oc(agendamento)
    except Exception:
        logger.exception("Falha ao gerar a Autorizacao de Coleta pro e-mail de autorizacao - enviando sem anexo")
        anexos = []

    vistos: set[tuple[str, str]] = set()
    for item in agendamento.itens:
        cliente, pedido = item.cliente.strip(), item.pedido.strip()
        if not cliente or not pedido or (cliente, pedido) in vistos:
            continue
        vistos.add((cliente, pedido))

        titulo, corpo = montar_autorizacao_agendamento(
            cliente, pedido, agendamento.loading_date, motorista=agendamento.driver_name
        )
        try:
            send_email_message(
                emails_agendamento.destino(RECIPIENTES_AUTORIZACAO_FERTIMAXI, True) if teste else RECIPIENTES_AUTORIZACAO_FERTIMAXI,
                f"[TESTE] {titulo}" if teste else titulo,
                corpo,
                anexos,
                imagens_inline=imagem_assinatura_inline(),
            )
        except Exception:
            logger.exception("Falha ao enviar e-mail de autorizacao de agendamento pra Fertimaxi (pedido %s)", pedido)


class AgendamentoItemIn(BaseModel):
    pedido: str = ""
    cliente: str = ""
    produto: str = ""
    cidade: str = ""
    embalagem: str = ""
    toneladas: float = 0
    pedido_id: Optional[int] = None


class AgendamentoIn(BaseModel):
    status: str = STATUS_AGENDAMENTO[0]
    supplier: str = ""
    loading_date: str = ""
    data_agendada: str = ""
    driver_name: str = ""
    driver_cpf: str = ""
    driver_phone: str = ""
    cnh: str = ""
    plate_cavalo: str = ""
    plate_carreta1: str = ""
    plate_carreta2: str = ""
    modelo_veiculo: str = ""
    roteiro: str = ""
    localizador: str = ""
    contato_cliente: str = ""
    observacoes: str = ""
    itens: list[AgendamentoItemIn] = []
    # So pros testes: e-mail pro endereco de teste em vez da fabrica.
    teste: bool = False


class AgendamentoStatusIn(BaseModel):
    status: str


def _to_dict(a: Agendamento) -> dict:
    return {
        "id": a.id,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
        "status": a.status,
        "supplier": a.supplier,
        "loading_date": a.loading_date,
        "data_agendada": a.data_agendada,
        "agendamento_confirmado_em": a.agendamento_confirmado_em,
        "agendamento_confirmado_por": a.agendamento_confirmado_por,
        "driver_name": a.driver_name,
        "driver_cpf": a.driver_cpf,
        "driver_phone": a.driver_phone,
        "cnh": a.cnh,
        "plate_cavalo": a.plate_cavalo,
        "plate_carreta1": a.plate_carreta1,
        "plate_carreta2": a.plate_carreta2,
        "modelo_veiculo": a.modelo_veiculo,
        "total_items": a.total_items,
        "total_tons": a.total_tons,
        "roteiro": a.roteiro,
        "localizador": a.localizador,
        "contato_cliente": a.contato_cliente,
        "observacoes": a.observacoes,
        "itens": [
            {
                "id": it.id,
                "pedido": it.pedido,
                "cliente": it.cliente,
                "produto": it.produto,
                "cidade": it.cidade,
                "embalagem": it.embalagem,
                "toneladas": it.toneladas,
                # O vinculo com o pedido volta pra tela: sem ele, "Salvar e
                # regerar" reescrevia os itens soltos e a barra parava.
                "pedido_id": it.pedido_ref_id,
            }
            for it in a.itens
        ],
        "emails": [
            {
                "tipo": e.tipo,
                "assunto": e.assunto,
                "destinatarios": e.destinatarios,
                "teste": e.teste,
                "motorista": e.motorista,
                "motorista_anterior": e.motorista_anterior,
                "enviado_por": e.enviado_por,
                "created_at": e.created_at,
            }
            for e in a.emails
        ],
    }


@router.get("")
def listar_agendamentos(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Agendamento)
    if status:
        query = query.filter(Agendamento.status == status)
    agendamentos = query.order_by(Agendamento.created_at.desc()).all()
    return [_to_dict(a) for a in agendamentos]


@router.post("")
def criar_agendamento(payload: AgendamentoIn, db: Session = Depends(get_db)):
    itens = payload.itens
    agendamento = Agendamento(
        **payload.model_dump(exclude={"itens", "teste"}),
        total_items=len(itens),
        total_tons=sum(i.toneladas for i in itens),
    )
    db.add(agendamento)
    # Itens ligados ao pedido - pelo id, ou pelo numero + produto quando a
    # tela nao mandou - e a barra do pedido acompanhando.
    saldo_pedidos.gravar_itens(db, agendamento, [i.model_dump() for i in itens])

    db.commit()
    db.refresh(agendamento)

    if _eh_fertimaxi(agendamento.supplier):
        _enviar_autorizacoes_agendamento_fertimaxi(agendamento, teste=payload.teste)

    return _to_dict(agendamento)


@router.get("/{agendamento_id}")
def obter_agendamento(agendamento_id: int, db: Session = Depends(get_db)):
    agendamento = db.get(Agendamento, agendamento_id)
    if agendamento is None:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado")
    return _to_dict(agendamento)


@router.delete("/{agendamento_id}")
def excluir_agendamento(agendamento_id: int, db: Session = Depends(get_db)):
    agendamento = db.get(Agendamento, agendamento_id)
    if agendamento is None:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado")

    # Devolve o saldo pros pedidos vinculados antes de apagar - excluir uma
    # O.C. libera de volta a tonelada que tinha sido descontada dela.
    saldo_pedidos.liberar(db, agendamento)

    db.delete(agendamento)
    db.commit()
    return {"ok": True}


class ConfirmarAgendamentoIn(BaseModel):
    data_agendada: str
    confirmado_por: str = ""


@router.patch("/{agendamento_id}/data-agendada")
def confirmar_data_agendada(
    agendamento_id: int,
    payload: ConfirmarAgendamentoIn,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    """Registra a data que o fornecedor confirmou (que costuma chegar depois
    da solicitacao, e nem sempre e a data pedida)."""
    agendamento = db.get(Agendamento, agendamento_id)
    if agendamento is None:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado")
    agendamento.data_agendada = payload.data_agendada.strip()
    agendamento.agendamento_confirmado_em = datetime.utcnow()
    agendamento.agendamento_confirmado_por = payload.confirmado_por or getattr(usuario, "email", "")
    agendamento.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(agendamento)
    return _to_dict(agendamento)


@router.patch("/{agendamento_id}/status")
def atualizar_status(agendamento_id: int, payload: AgendamentoStatusIn, db: Session = Depends(get_db)):
    agendamento = db.get(Agendamento, agendamento_id)
    if agendamento is None:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado")
    if payload.status not in STATUS_AGENDAMENTO:
        raise HTTPException(status_code=400, detail=f"Status invalido. Use um de: {STATUS_AGENDAMENTO}")
    # Cancelado nao ocupa saldo: cancelar devolve, reabrir desconta de novo.
    saldo_pedidos.mudar_status(db, agendamento, payload.status)
    agendamento.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(agendamento)
    return _to_dict(agendamento)


class CidadeItemIn(BaseModel):
    cidade: str
    uf: str


@router.patch("/{agendamento_id}/itens/{item_id}/cidade")
def corrigir_cidade_do_item(agendamento_id: int, item_id: int, payload: CidadeItemIn, db: Session = Depends(get_db)):
    """Troca a cidade de um item do agendamento - so dele, sem mexer no pedido
    nem nos outros agendamentos do mesmo pedido.

    So aceita cidade do cadastro, gravada como a leitura grava ("Nome-UF"):
    e o formato que a cotacao de frete usa pra achar a tarifa do destino.
    """
    item = db.get(AgendamentoItem, item_id)
    if item is None or item.agendamento_id != agendamento_id:
        raise HTTPException(status_code=404, detail="Item nao encontrado neste agendamento")
    uf = payload.uf.strip().upper()
    procurada = ocr.normalizar_texto_sem_acento(payload.cidade)
    cidade = next(
        (c for c in db.query(Cidade).filter(Cidade.uf == uf).all()
         if ocr.normalizar_texto_sem_acento(c.nome) == procurada),
        None,
    )
    if cidade is None:
        raise HTTPException(
            status_code=400,
            detail=f"Cidade '{payload.cidade.strip()}' nao encontrada em {uf or '(sem UF)'} no cadastro de cidades.",
        )
    agendamento = item.agendamento
    item.cidade = ocr.formatar_cidade(cidade.nome, cidade.uf)
    agendamento.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(agendamento)
    return _to_dict(agendamento)


# --------------------------------------------------------------------------
# Inclusao e substituicao de motorista
# --------------------------------------------------------------------------


class ItemNovoIn(BaseModel):
    pedido_id: Optional[int] = None
    pedido: str = ""
    cliente: str = ""
    produto: str = ""
    cidade: str = ""
    embalagem: str = ""
    toneladas: float = 0


class EmailMotoristaIn(BaseModel):
    tipo: str
    driver_name: str = ""
    driver_cpf: str = ""
    driver_phone: str = ""
    cnh: str = ""
    plate_cavalo: str = ""
    plate_carreta1: str = ""
    plate_carreta2: str = ""
    modelo_veiculo: str = ""
    novos_itens: list[ItemNovoIn] = []
    assunto: str = ""
    mensagem: str = ""
    teste: bool = False


@router.get("/email-motorista/config")
def config_email_motorista():
    """Pra tela: pra onde o e-mail vai, se esta em teste, e o texto pronto."""
    return {
        "em_teste": settings.emails_motorista_em_teste,
        "email_teste": settings.email_teste_fabrica,
        "copia": settings.gmail_sender_email,
        "destinatarios": {
            "Fertimaxi": emails_agendamento.destinatarios_da_fabrica("Fertimaxi"),
            "Heringer": emails_agendamento.destinatarios_da_fabrica("Heringer"),
        },
        "modelos": emails_agendamento.MODELOS_MENSAGEM,
    }


@router.post("/{agendamento_id}/email-motorista")
def enviar_email_motorista(
    agendamento_id: int,
    payload: EmailMotoristaIn,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    """Inclusao ou substituicao de motorista.

    Grava o motorista (e os pedidos que entraram junto) no agendamento e
    manda um e-mail NOVO pra fabrica, com a autorizacao atualizada em anexo.
    Se o e-mail nao sair, nada e gravado - da pra tentar de novo.
    """
    agendamento = db.get(Agendamento, agendamento_id)
    if agendamento is None:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado")

    tipo = (payload.tipo or "").strip().lower()
    if tipo not in emails_agendamento.TIPOS:
        raise HTTPException(status_code=400, detail="Tipo de e-mail invalido: use inclusao ou substituicao")
    motorista_atual = (agendamento.driver_name or "").strip()
    if tipo == "inclusao" and motorista_atual:
        raise HTTPException(status_code=409, detail=f"Este agendamento ja tem motorista ({motorista_atual}): use substituicao.")
    if tipo == "substituicao" and not motorista_atual:
        raise HTTPException(status_code=409, detail="Este agendamento ainda nao tem motorista: use inclusao.")
    if not payload.driver_name.strip():
        raise HTTPException(status_code=400, detail="Informe o nome do motorista.")
    if not payload.plate_cavalo.strip():
        raise HTTPException(status_code=400, detail="Informe a placa do cavalo.")

    anterior = {
        "nome": agendamento.driver_name, "cpf": agendamento.driver_cpf, "fone": agendamento.driver_phone,
        "cnh": agendamento.cnh, "placa1": agendamento.plate_cavalo, "placa2": agendamento.plate_carreta1,
        "placa3": agendamento.plate_carreta2, "modelo": agendamento.modelo_veiculo,
    }
    itens = [
        {"pedido": i.pedido, "cliente": i.cliente, "produto": i.produto, "cidade": i.cidade,
         "embalagem": i.embalagem, "toneladas": i.toneladas, "pedido_id": i.pedido_ref_id}
        for i in agendamento.itens
    ]
    itens += [
        i.model_dump() for i in payload.novos_itens
        if (i.pedido.strip() or i.pedido_id) and i.toneladas > 0
    ]

    agendamento.driver_name = payload.driver_name.strip()
    agendamento.driver_cpf = payload.driver_cpf.strip()
    agendamento.driver_phone = payload.driver_phone.strip()
    agendamento.cnh = payload.cnh.strip()
    agendamento.plate_cavalo = payload.plate_cavalo.strip()
    agendamento.plate_carreta1 = payload.plate_carreta1.strip()
    agendamento.plate_carreta2 = payload.plate_carreta2.strip()
    agendamento.modelo_veiculo = payload.modelo_veiculo.strip()
    # Pedidos que entraram junto descontam o saldo; os que ja estavam, nao.
    saldo_pedidos.gravar_itens(db, agendamento, itens)
    agendamento.total_items = len(agendamento.itens)
    agendamento.total_tons = sum(i.toneladas for i in agendamento.itens)
    agendamento.updated_at = datetime.utcnow()

    novo = {
        "nome": agendamento.driver_name, "cpf": agendamento.driver_cpf, "fone": agendamento.driver_phone,
        "cnh": agendamento.cnh, "placa1": agendamento.plate_cavalo, "placa2": agendamento.plate_carreta1,
        "placa3": agendamento.plate_carreta2, "modelo": agendamento.modelo_veiculo,
    }
    template = "HERINGER" if (agendamento.supplier or "").strip().lower() == "heringer" else "AFL"
    documento = OrdemColetaRequest(
        template=template,
        produtos=[
            Produto(contrato=i.pedido, produto=i.produto, embalagem=i.embalagem, toneladas=str(i.toneladas),
                    cidade=i.cidade, cliente=i.cliente, pedido_id=i.pedido_ref_id)
            for i in agendamento.itens
        ],
        cpf=agendamento.driver_cpf, nome=agendamento.driver_name, cnh=agendamento.cnh, fone=agendamento.driver_phone,
        placa1=agendamento.plate_cavalo, placa2=agendamento.plate_carreta1, placa3=agendamento.plate_carreta2,
        modelo_veiculo=agendamento.modelo_veiculo, data_carregamento=agendamento.loading_date,
        observacoes=agendamento.observacoes,
    )
    try:
        arquivos = _gerar_oc_arquivos(documento, tempfile.mkdtemp())
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Falha ao gerar a autorizacao: {exc}. Nada foi alterado.")
    anexos = [arquivos["xlsx"]] if template == "AFL" and arquivos.get("xlsx") else [arquivos["pdf"]]

    teste = payload.teste or settings.emails_motorista_em_teste
    reais = emails_agendamento.destinatarios_da_fabrica(agendamento.supplier)
    para = emails_agendamento.destino(reais, teste)
    assunto = payload.assunto.strip() or emails_agendamento.assunto_padrao(tipo, agendamento.driver_name, agendamento.itens)
    if teste:
        assunto = f"[TESTE] {assunto}"
    mensagem = payload.mensagem.strip() or emails_agendamento.mensagem_padrao(
        tipo, agendamento.itens, agendamento.data_agendada or agendamento.loading_date, anterior["nome"]
    )
    corpo = emails_agendamento.montar_corpo(
        tipo, mensagem, novo, agendamento.itens,
        anterior=anterior if tipo == "substituicao" else None,
        iria_para=reais if teste else None,
    )
    try:
        send_email_message(para, assunto, corpo, anexos, imagens_inline=imagem_assinatura_inline())
    except Exception as exc:
        db.rollback()
        logger.warning("E-mail de %s do agendamento %s nao saiu: %s", tipo, agendamento_id, str(exc)[:200])
        raise HTTPException(status_code=502, detail=f"O e-mail nao saiu ({exc}). Nada foi alterado no agendamento.")

    agendamento.email_subject = assunto[:500]
    agendamento.email_recipients = ", ".join(para)[:1000]
    db.add(AgendamentoEmail(
        agendamento_id=agendamento.id,
        tipo=tipo,
        assunto=assunto[:500],
        destinatarios=", ".join(para)[:1000],
        teste=teste,
        motorista=agendamento.driver_name,
        motorista_anterior=(anterior["nome"] or "") if tipo == "substituicao" else "",
        enviado_por=getattr(usuario, "email", "") or "",
    ))
    db.commit()
    db.refresh(agendamento)
    return {"agendamento": _to_dict(agendamento), "email": {"tipo": tipo, "assunto": assunto, "para": para, "teste": teste}}
