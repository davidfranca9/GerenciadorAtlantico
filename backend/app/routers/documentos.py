from __future__ import annotations

import html
import os
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
from ..servicos.documentos import fill_carta_frete_docx, gerar_oc_docx
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
TEMPLATES_OC = {
    "AFL": DADOS_DIR / "O.C_AFL.docx",
    "HERINGER": DADOS_DIR / "O.C_HERINGER.docx",
}
TEMPLATE_CF = DADOS_DIR / "CARTA FRETE atlantico (1).docx"


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
    formato: str = "docx"  # "docx" | "pdf"


class CartaFreteRequest(BaseModel):
    DATA: str = ""
    CONDUTOR: str = ""
    CPF: str = ""
    PLACA_CAVALO: str = ""
    VALOR_FRETE: str = ""
    AUTORIZACAO_NUM: str = ""
    formato: str = "docx"


@router.post("/ordens-coleta/gerar")
def gerar_ordem_coleta(payload: OrdemColetaRequest):
    template_path = TEMPLATES_OC.get(payload.template.upper())
    if template_path is None or not template_path.exists():
        raise HTTPException(status_code=400, detail=f"Template '{payload.template}' invalido")

    tmp_dir = tempfile.mkdtemp()
    docx_path = os.path.join(tmp_dir, "ordem_coleta.docx")

    gerar_oc_docx(
        str(template_path),
        docx_path,
        [p.model_dump() for p in payload.produtos],
        payload.cpf,
        payload.nome,
        payload.cnh,
        payload.fone,
        payload.placa1,
        payload.placa2,
        payload.placa3,
        payload.data_carregamento,
    )

    if payload.formato.lower() == "pdf":
        pdf_path = docx_to_pdf(docx_path)
        return FileResponse(pdf_path, filename="ordem_coleta.pdf", media_type="application/pdf")

    return FileResponse(
        docx_path,
        filename="ordem_coleta.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


class EnviarOrdemColetaRequest(OrdemColetaRequest):
    roteiro: str = ""
    localizador: str = ""
    contato_cliente: str = ""


def _gerar_oc_arquivos(payload: OrdemColetaRequest) -> tuple[str, str]:
    template_path = TEMPLATES_OC.get(payload.template.upper())
    if template_path is None or not template_path.exists():
        raise HTTPException(status_code=400, detail=f"Template '{payload.template}' invalido")

    tmp_dir = tempfile.mkdtemp()
    docx_path = os.path.join(tmp_dir, "ordem_coleta.docx")
    gerar_oc_docx(
        str(template_path),
        docx_path,
        [p.model_dump() for p in payload.produtos],
        payload.cpf,
        payload.nome,
        payload.cnh,
        payload.fone,
        payload.placa1,
        payload.placa2,
        payload.placa3,
        payload.data_carregamento,
    )
    pdf_path = docx_to_pdf(docx_path)
    return docx_path, pdf_path


@router.post("/ordens-coleta/enviar-email")
def enviar_ordem_coleta_email(payload: EnviarOrdemColetaRequest, db: Session = Depends(get_db)):
    if not payload.produtos:
        raise HTTPException(status_code=400, detail="Selecione ao menos um produto/pedido")
    if not payload.nome.strip():
        raise HTTPException(status_code=400, detail="Nome do motorista e obrigatorio")

    supplier_label = "Heringer" if payload.template.upper() == "HERINGER" else "Fertimax"
    recipients = RECIPIENTS_HERINGER if supplier_label == "Heringer" else RECIPIENTS_FERTIMAX

    _docx_path, pdf_path = _gerar_oc_arquivos(payload)

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
        send_email_message(recipients, subject, body, [pdf_path])
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
        oc_pdf_path=pdf_path,
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
