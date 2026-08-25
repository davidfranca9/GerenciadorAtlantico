"""Integracao com a API oficial do WhatsApp (Meta Cloud API).

Usada pelo webhook em routers/whatsapp.py para baixar arquivos recebidos
(media_id -> URL -> bytes) e responder ao remetente. Precisa de
WHATSAPP_ACCESS_TOKEN e WHATSAPP_PHONE_NUMBER_ID configurados (gerados no
Meta for Developers, dentro do app do WhatsApp Business).
"""
from __future__ import annotations

import requests

from ..config import settings

GRAPH_URL = "https://graph.facebook.com/v21.0"


class WhatsAppIndisponivel(Exception):
    pass


def _token_ou_erro() -> str:
    if not settings.whatsapp_access_token:
        raise WhatsAppIndisponivel("WHATSAPP_ACCESS_TOKEN nao configurado")
    return settings.whatsapp_access_token


def obter_url_midia(media_id: str) -> str:
    token = _token_ou_erro()
    resposta = requests.get(f"{GRAPH_URL}/{media_id}", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resposta.raise_for_status()
    return resposta.json()["url"]


def baixar_midia(url: str) -> bytes:
    token = _token_ou_erro()
    resposta = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    resposta.raise_for_status()
    return resposta.content


def enviar_mensagem_texto(numero_destino: str, texto: str) -> None:
    token = _token_ou_erro()
    if not settings.whatsapp_phone_number_id:
        raise WhatsAppIndisponivel("WHATSAPP_PHONE_NUMBER_ID nao configurado")
    resposta = requests.post(
        f"{GRAPH_URL}/{settings.whatsapp_phone_number_id}/messages",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"messaging_product": "whatsapp", "to": numero_destino, "type": "text", "text": {"body": texto}},
        timeout=30,
    )
    resposta.raise_for_status()
