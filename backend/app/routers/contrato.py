from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Cidade
from ..servicos import ocr, ocr_gemini
from ..servicos.bsoft_lookup import BSOFT_SIMPLE_BRANDS_LIST, BSOFT_TIPOS_CARROCERIA_NOMES

router = APIRouter(prefix="/contrato", tags=["contrato"], dependencies=[Depends(get_current_user)])


async def _save_upload(file: UploadFile) -> str:
    suffix = os.path.splitext(file.filename or "")[1] or ".pdf"
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(await file.read())
    return path


def _ocr_texto_ou_erro(path: str) -> str:
    try:
        return ocr.obter_texto_do_arquivo_ocr(path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro no OCR: {exc!r}")


@router.post("/ocr/pedido-heringer")
async def ocr_pedido_heringer(file: UploadFile):
    path = await _save_upload(file)
    try:
        texto = _ocr_texto_ou_erro(path)
        produtos = ocr.extrair_dados_pedido_heringer(texto)
        return {"produtos": produtos}
    finally:
        os.remove(path)


@router.post("/ocr/cnh")
async def ocr_cnh(file: UploadFile):
    path = await _save_upload(file)
    try:
        try:
            return ocr_gemini.extrair_dados_cnh_com_gemini(path)
        except ocr_gemini.GeminiIndisponivel:
            pass
        except Exception:
            pass
        texto = _ocr_texto_ou_erro(path)
        return ocr.extrair_dados_cnh_com_azure_api(texto)
    finally:
        os.remove(path)


@router.post("/ocr/crlv")
async def ocr_crlv(file: UploadFile):
    path = await _save_upload(file)
    try:
        try:
            return ocr_gemini.extrair_dados_crlv_com_gemini(path)
        except ocr_gemini.GeminiIndisponivel:
            pass
        except Exception:
            pass
        texto = _ocr_texto_ou_erro(path)
        return ocr.extrair_dados_crlv_com_azure_api(texto, BSOFT_SIMPLE_BRANDS_LIST, BSOFT_TIPOS_CARROCERIA_NOMES)
    finally:
        os.remove(path)


@router.post("/parse-pdf")
async def parse_pdf(file: UploadFile, db: Session = Depends(get_db)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo PDF")
    path = await _save_upload(file)
    try:
        cidades = [(c.nome, c.uf) for c in db.query(Cidade).all()]
        return ocr.parse_pdf_fields(path, cidades)
    finally:
        os.remove(path)
