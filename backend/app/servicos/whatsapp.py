"""Integracao com a API oficial do WhatsApp (Meta Cloud API).

Usada pelo webhook em routers/whatsapp.py para baixar arquivos recebidos
(media_id -> URL -> bytes) e responder ao remetente. Precisa de
WHATSAPP_ACCESS_TOKEN e WHATSAPP_PHONE_NUMBER_ID configurados (gerados no
Meta for Developers, dentro do app do WhatsApp Business).
"""
from __future__ import annotations

import os
import subprocess
import tempfile

import requests

from ..config import settings

GRAPH_URL = "https://graph.facebook.com/v21.0"

# Mime type exato que a Meta espera pra nota de voz: ogg com codec Opus,
# unico canal (mono). Sem o ";codecs=opus" a mensagem chega a ser enviada
# (a API aceita o upload), mas o audio fica indisponivel no celular do
# destinatario ("este audio nao esta mais disponivel").
_MIME_AUDIO_WHATSAPP = "audio/ogg; codecs=opus"


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


def tipo_mensagem_para_mime(mime_type: str) -> str:
    """Mapeia o mime type do arquivo pro tipo de mensagem do WhatsApp
    (image/video/audio tem preview nativo no chat; o resto vira documento)."""
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"
    return "document"


def _normalizar_audio(conteudo: bytes) -> bytes:
    """Sempre reencoda o audio pra ogg/opus mono (formato exato que o
    WhatsApp exige pra nota de voz) via ffmpeg, seja audio gravado no
    navegador (webm/opus) ou arquivo solto escolhido manualmente (mp3, wav,
    etc) - garante que bate certinho com o que a Meta espera, em vez de
    confiar que o mime type recebido ja esta no formato certo."""
    with tempfile.TemporaryDirectory() as tmp:
        entrada = os.path.join(tmp, "entrada")
        saida = os.path.join(tmp, "saida.ogg")
        with open(entrada, "wb") as f:
            f.write(conteudo)
        resultado = subprocess.run(
            ["ffmpeg", "-y", "-i", entrada, "-vn", "-c:a", "libopus", "-b:a", "32k", "-ar", "48000", "-ac", "1", saida],
            capture_output=True,
        )
        if resultado.returncode != 0:
            raise WhatsAppIndisponivel(f"Falha ao converter audio: {resultado.stderr.decode(errors='ignore')[:300]}")
        with open(saida, "rb") as f:
            return f.read()


def enviar_arquivo(numero_destino: str, conteudo: bytes, mime_type: str, nome_arquivo: str, legenda: str = "") -> tuple[bytes, str, str]:
    """Sobe o arquivo pra Meta e manda como mensagem de imagem/video/audio ou
    documento, dependendo do mime_type. Documentos, imagens e videos aceitam
    legenda; audio nao (a API da Meta rejeita caption em mensagens de audio).

    Retorna (conteudo, mime_type, nome_arquivo) reais que foram enviados -
    podem diferir dos recebidos quando o audio precisa ser convertido -, pra
    quem chamou conseguir guardar exatamente o que foi mandado."""
    token = _token_ou_erro()
    phone_number_id = _phone_number_id_ou_erro()

    if tipo_mensagem_para_mime(mime_type) == "audio":
        conteudo = _normalizar_audio(conteudo)
        mime_type = _MIME_AUDIO_WHATSAPP
        if not nome_arquivo.lower().endswith(".ogg"):
            nome_arquivo = f"{os.path.splitext(nome_arquivo)[0]}.ogg"

    upload = requests.post(
        f"{GRAPH_URL}/{phone_number_id}/media",
        headers={"Authorization": f"Bearer {token}"},
        data={"messaging_product": "whatsapp", "type": mime_type},
        files={"file": (nome_arquivo, conteudo, mime_type)},
        timeout=60,
    )
    _levantar_com_corpo(upload)
    media_id = upload.json()["id"]

    tipo_msg = tipo_mensagem_para_mime(mime_type)
    corpo_midia = {"id": media_id}
    if tipo_msg == "audio":
        corpo_midia["voice"] = True
    elif legenda:
        corpo_midia["caption"] = legenda
    if tipo_msg == "document":
        corpo_midia["filename"] = nome_arquivo

    resposta = requests.post(
        f"{GRAPH_URL}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"messaging_product": "whatsapp", "to": numero_destino, "type": tipo_msg, tipo_msg: corpo_midia},
        timeout=30,
    )
    _levantar_com_corpo(resposta)
    return conteudo, mime_type, nome_arquivo
