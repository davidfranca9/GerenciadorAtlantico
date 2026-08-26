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


def _levantar_com_corpo(resposta: requests.Response) -> None:
    """Igual resposta.raise_for_status(), mas inclui o corpo da resposta (onde
    a Graph API da Meta manda a mensagem de erro detalhada) na excecao."""
    if resposta.ok:
        return
    raise requests.HTTPError(f"{resposta.status_code} {resposta.reason} - corpo: {resposta.text[:500]}", response=resposta)


def obter_url_midia(media_id: str) -> str:
    token = _token_ou_erro()
    resposta = requests.get(f"{GRAPH_URL}/{media_id}", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    _levantar_com_corpo(resposta)
    return resposta.json()["url"]


def baixar_midia(url: str) -> bytes:
    token = _token_ou_erro()
    resposta = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    _levantar_com_corpo(resposta)
    return resposta.content


def _phone_number_id_ou_erro() -> str:
    if not settings.whatsapp_phone_number_id:
        raise WhatsAppIndisponivel("WHATSAPP_PHONE_NUMBER_ID nao configurado")
    return settings.whatsapp_phone_number_id


def enviar_mensagem_texto(numero_destino: str, texto: str) -> None:
    token = _token_ou_erro()
    phone_number_id = _phone_number_id_ou_erro()
    resposta = requests.post(
        f"{GRAPH_URL}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"messaging_product": "whatsapp", "to": numero_destino, "type": "text", "text": {"body": texto}},
        timeout=30,
    )
    _levantar_com_corpo(resposta)


def enviar_arquivo(numero_destino: str, conteudo: bytes, mime_type: str, nome_arquivo: str, legenda: str = "") -> None:
    """Sobe o arquivo pra Meta e manda como mensagem de documento ou imagem,
    dependendo do mime_type. Documentos preservam o nome do arquivo original;
    imagens sao exibidas inline no chat."""
    token = _token_ou_erro()
    phone_number_id = _phone_number_id_ou_erro()

    upload = requests.post(
        f"{GRAPH_URL}/{phone_number_id}/media",
        headers={"Authorization": f"Bearer {token}"},
        data={"messaging_product": "whatsapp", "type": mime_type},
        files={"file": (nome_arquivo, conteudo, mime_type)},
        timeout=60,
    )
    _levantar_com_corpo(upload)
    media_id = upload.json()["id"]

    eh_imagem = mime_type.startswith("image/")
    corpo_midia = {"id": media_id}
    if legenda:
        corpo_midia["caption"] = legenda
    if not eh_imagem:
        corpo_midia["filename"] = nome_arquivo

    resposta = requests.post(
        f"{GRAPH_URL}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "messaging_product": "whatsapp",
            "to": numero_destino,
            "type": "image" if eh_imagem else "document",
            ("image" if eh_imagem else "document"): corpo_midia,
        },
        timeout=30,
    )
    _levantar_com_corpo(resposta)
