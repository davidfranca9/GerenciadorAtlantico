from __future__ import annotations

import os
import tempfile
from pathlib import Path

from docx import Document
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..auth import get_current_user
from ..servicos.documentos import fill_carta_frete_docx, gerar_oc_docx
from ..servicos.pdf_convert import docx_to_pdf

router = APIRouter(dependencies=[Depends(get_current_user)])

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
