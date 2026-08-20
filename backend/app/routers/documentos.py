from __future__ import annotations

import html
import os
import re
import tempfile
from pathlib import Path

from docx import Document
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Agendamento, AgendamentoItem
from ..servicos.comunicacao import send_email_message
from ..servicos.documentos import fill_carta_frete_docx, gerar_autorizacao_xlsx
from ..servicos.oc_html import gerar_oc_pdf_html
from ..servicos.pdf_convert import docx_to_pdf

router = APIRouter(dependencies=[Depends(get_current_user)])

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
TEMPLATE_CF = DADOS_DIR / "CARTA FRETE atlantico (1).docx"
TEMPLATE_AUTORIZACAO = DADOS_DIR / "Autorizacao de Carregamento (2).xlsx"


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
    data_carregamento: str = ""

class CartaFreteRequest(BaseModel):
    DATA: str = ""
    CONDUTOR: str = ""
    CPF: str = ""
    PLACA_CAVALO: str = ""
    VALOR_FRETE: str = ""
    AUTORIZACAO_NUM: str = ""
    formato: str = "docx"


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
    )

    xlsx_path = None
    if payload.template.upper() != "HERINGER" and TEMPLATE_AUTORIZACAO.exists():
        cliente_name = _client_name_from_produtos(produtos_dict)
        xlsx_path = os.path.join(tmp_dir, f"Autorizacao de carregamento_{cliente_name}.xlsx")
        gerar_autorizacao_xlsx(
            str(TEMPLATE_AUTORIZACAO),
            xlsx_path,
            produtos_dict,
            payload.data_carregamento,
            payload.nome,
            payload.placa1,
        )

    return {"pdf": pdf_path, "xlsx": xlsx_path, "safe_name": safe_name}


@router.post("/ordens-coleta/gerar")
def gerar_ordem_coleta(payload: OrdemColetaRequest):
    tmp_dir = tempfile.mkdtemp()
    arquivos = _gerar_oc_arquivos(payload, tmp_dir)
    safe_name = arquivos["safe_name"]
    return FileResponse(arquivos["pdf"], filename=f"Ordem de Coleta_{safe_name}.pdf", media_type="application/pdf")


@router.post("/ordens-coleta/gerar-autorizacao")
def gerar_autorizacao_coleta(payload: OrdemColetaRequest):
    if payload.template.upper() == "HERINGER":
        raise HTTPException(status_code=400, detail="Autorizacao de Coleta nao se aplica ao fornecedor Heringer")
    if not TEMPLATE_AUTORIZACAO.exists():
        raise HTTPException(status_code=400, detail="Template de Autorizacao de Coleta nao encontrado")

    tmp_dir = tempfile.mkdtemp()
    produtos_dict = [p.model_dump() for p in payload.produtos]
    cliente_name = _client_name_from_produtos(produtos_dict)
    xlsx_path = os.path.join(tmp_dir, f"Autorizacao de carregamento_{cliente_name}.xlsx")
    gerar_autorizacao_xlsx(
        str(TEMPLATE_AUTORIZACAO),
        xlsx_path,
        produtos_dict,
        payload.data_carregamento,
        payload.nome,
        payload.placa1,
    )
    return FileResponse(
        xlsx_path,
        filename=f"Autorizacao de carregamento_{cliente_name}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


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

    supplier_label = "Heringer" if payload.template.upper() == "HERINGER" else "Fertimax"
    recipients = RECIPIENTS_HERINGER if supplier_label == "Heringer" else RECIPIENTS_FERTIMAX

    tmp_dir = tempfile.mkdtemp()
    arquivos = _gerar_oc_arquivos(payload, tmp_dir)
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
        send_email_message(recipients, subject, body, anexos)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao enviar e-mail: {exc}")

    itens = [p for p in payload.produtos]
    agendamento = Agendamento(
        status="Aguardando Agendamento",
        supplier=supplier_label,
        loading_date=payload.data_carregamento,
        driver_name=payload.nome.strip(),
        driver_cpf=payload.cpf.strip(),
        driver_phone=payload.fone.strip(),
        cnh=payload.cnh.strip(),
        plate_cavalo=payload.placa1.strip(),
        plate_carreta1=payload.placa2.strip(),
        plate_carreta2=payload.placa3.strip(),
        total_items=len(itens),
        total_tons=sum(_safe_float(p.toneladas) for p in itens),
        roteiro=payload.roteiro.strip(),
        localizador=payload.localizador.strip(),
        contato_cliente=payload.contato_cliente.strip(),
        email_subject=subject,
        email_recipients=", ".join(recipients),
        oc_pdf_path=arquivos["pdf"],
        planilha_path=arquivos["xlsx"] or "",
    )
    agendamento.itens = [
        AgendamentoItem(
            pedido=p.contrato,
            cliente=p.cliente,
            produto=p.produto,
            cidade=p.cidade,
            embalagem=p.embalagem,
            toneladas=_safe_float(p.toneladas),
        )
        for p in itens
    ]
    db.add(agendamento)
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
    if not TEMPLATE_CF.exists():
        raise HTTPException(status_code=400, detail="Template de Carta Frete nao encontrado")

    doc = Document(str(TEMPLATE_CF))
    dados = payload.model_dump(exclude={"formato"})
    fill_carta_frete_docx(doc, dados)

    tmp_dir = tempfile.mkdtemp()
    docx_path = os.path.join(tmp_dir, "carta_frete.docx")
    doc.save(docx_path)

    if payload.formato.lower() == "pdf":
        pdf_path = docx_to_pdf(docx_path)
        return FileResponse(pdf_path, filename="carta_frete.pdf", media_type="application/pdf")

    return FileResponse(
        docx_path,
        filename="carta_frete.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
