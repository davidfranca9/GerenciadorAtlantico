"""Recebimento de pedidos via WhatsApp (Meta Cloud API).

Fluxo: cliente manda um PDF de pedido pro numero do WhatsApp Business ->
Meta chama nosso webhook -> baixamos o arquivo, extraimos os produtos com
o mesmo parser ja usado em /pedidos/importar-pdf, criamos os Pedidos no
banco e respondemos confirmando pro remetente.

Este router NAO exige login (get_current_user) porque quem chama e a
propria Meta, nao um usuario logado no sistema. A seguranca aqui e feita
validando a assinatura HMAC do corpo da requisicao (X-Hub-Signature-256)
contra o WHATSAPP_APP_SECRET.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import tempfile

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from ..config import settings
from ..database import SessionLocal
from ..models import Cidade, Pedido
from ..servicos import ocr, whatsapp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

_EXT_POR_MIME = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

MENSAGEM_SEM_PRODUTOS = (
    "Recebi o arquivo, mas nao consegui identificar nenhum produto nele. "
    "Confira o pedido e envie novamente, ou entre em contato com nossa equipe."
)
MENSAGEM_ERRO = "Nao consegui processar o arquivo enviado agora. Nossa equipe vai verificar em breve."
MENSAGEM_FORMATO_INVALIDO = "No momento so consigo ler pedidos em PDF. Pode reenviar nesse formato?"


@router.get("/webhook")
def verificar_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Chamado pela Meta uma unica vez, ao cadastrar a URL do webhook."""
    if hub_mode == "subscribe" and settings.whatsapp_verify_token and hub_verify_token == settings.whatsapp_verify_token:
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(status_code=403, detail="Token de verificacao invalido")


def _assinatura_valida(corpo: bytes, assinatura_recebida: str) -> bool:
    if not settings.whatsapp_app_secret:
        # Sem app secret configurado ainda nao da pra validar - permite
        # passar (usado so na fase inicial, antes do secret ser setado).
        return True
    esperado = "sha256=" + hmac.new(settings.whatsapp_app_secret.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, assinatura_recebida or "")


def _processar_arquivo_recebido(numero_remetente: str, media_id: str, mime_type: str) -> None:
    """Roda em background (fora do request do webhook): baixa o arquivo,
    extrai os produtos e cria os Pedidos. Sempre responde ao remetente,
    mesmo em caso de erro, pra ele saber que algo deu errado."""
    if mime_type != "application/pdf":
        try:
            whatsapp.enviar_mensagem_texto(numero_remetente, MENSAGEM_FORMATO_INVALIDO)
        except Exception:
            logger.exception("Falha ao responder remetente sobre formato invalido")
        return

    db = SessionLocal()
    path = None
    try:
        url = whatsapp.obter_url_midia(media_id)
        conteudo = whatsapp.baixar_midia(url)

        suffix = _EXT_POR_MIME.get(mime_type, ".pdf")
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(conteudo)

        cidades = [(c.nome, c.uf) for c in db.query(Cidade).all()]
        resultado = ocr.parse_pdf_fields(path, cidades)
        produtos = resultado.get("produtos") or []

        criados = 0
        for item in produtos:
            toneladas = float(item.get("toneladas") or 0)
            if toneladas <= 0:
                continue
            db.add(
                Pedido(
                    contrato=str(item.get("contrato") or ""),
                    produto=str(item.get("produto") or ""),
                    embalagem=str(item.get("embalagem") or ""),
                    cidade=str(item.get("cidade") or ""),
                    cliente=str(item.get("cliente") or ""),
                    supplier=settings.whatsapp_supplier_padrao or "AFL",
                    toneladas_total=toneladas,
                    toneladas_usadas=0,
                )
            )
            criados += 1
        db.commit()

        mensagem = (
            f"Pedido recebido! {criados} produto(s) cadastrado(s) no sistema."
            if criados
            else MENSAGEM_SEM_PRODUTOS
        )
        whatsapp.enviar_mensagem_texto(numero_remetente, mensagem)
    except Exception:
        logger.exception("Falha ao processar pedido recebido via WhatsApp")
        try:
            whatsapp.enviar_mensagem_texto(numero_remetente, MENSAGEM_ERRO)
        except Exception:
            logger.exception("Falha ao responder remetente sobre erro de processamento")
    finally:
        db.close()
        if path:
            try:
                os.remove(path)
            except OSError:
                pass


@router.post("/webhook")
async def receber_webhook(request: Request, background_tasks: BackgroundTasks):
    corpo = await request.body()
    if not _assinatura_valida(corpo, request.headers.get("X-Hub-Signature-256", "")):
        raise HTTPException(status_code=403, detail="Assinatura invalida")

    try:
        payload = json.loads(corpo)
    except ValueError:
        return {"status": "ok"}

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            valor = change.get("value", {})
            for msg in valor.get("messages") or []:
                numero = msg.get("from")
                anexo = msg.get("document") or msg.get("image")
                if not (numero and anexo and anexo.get("id")):
                    continue
                background_tasks.add_task(
                    _processar_arquivo_recebido,
                    numero,
                    anexo["id"],
                    anexo.get("mime_type", "application/pdf"),
                )

    # Responde 200 rapido - a Meta reenvia o webhook se demorar ou falhar.
    return {"status": "ok"}
