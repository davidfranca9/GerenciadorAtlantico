"""Envio de e-mail (Gmail SMTP). Portado de servicos/comunicacao.py sem tkinter."""
from __future__ import annotations

import base64
import html
import mimetypes
import os
import smtplib
import time
import uuid
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from pathlib import Path

from ..config import settings

ASSINATURA_EMAIL_PATH = Path(__file__).resolve().parents[2] / "dados" / "assinatura_email.png"


def imagem_assinatura_inline() -> dict[str, str]:
    """Referencie no HTML do corpo via <img src="cid:assinatura_fertlog">."""
    return {"assinatura_fertlog": str(ASSINATURA_EMAIL_PATH)}


def montar_autorizacao_agendamento(cliente: str, pedido: str, data_carregamento: str, motorista: str = "") -> tuple[str, str]:
    """Monta (assunto, corpo_html) do pedido de autorizacao de agendamento
    pra fornecedores tipo Fertimaxi - usado tanto no "Novo Agendamento"
    rapido quanto no fluxo de Ordem de Coleta, pra manter o mesmo texto nos
    dois lugares onde esse e-mail e disparado.

    O assunto leva o nome do motorista quando ele ja foi definido, e o do
    cliente enquanto nao foi - a mesma regra do nome do arquivo anexado."""
    partes_data = (data_carregamento or "").split("/")
    data_formatada = f"{partes_data[0]}.{partes_data[1]}" if len(partes_data) == 3 else ""
    prazo = f"para dia {data_formatada} ou para o próximo dia disponível" if data_formatada else "para o próximo dia disponível"

    nome = (motorista or "").strip() or cliente
    titulo = f"AUTORIZAÇÃO AGENDAMENTO: {nome} - Nº {pedido}"
    corpo = f"""
        <p>Prezados,</p>
        <p>Solicitamos, por gentileza, o agendamento do pedido {html.escape(prazo)}.</p>
        <p>Ficamos no aguardo da confirmação do agendamento.</p>
        <img src="cid:assinatura_fertlog" alt="Atlântico Fertlog" style="max-width:420px;margin-top:18px">
    """
    return titulo, corpo


def _thread_index_novo() -> str:
    """Cabecalho Thread-Index do Outlook marcando o comeco de uma conversa nova:
    1 byte reservado, os 5 bytes mais altos do FILETIME de agora e um GUID."""
    filetime = int((time.time() + 11644473600) * 10_000_000)
    cabeca = bytes([1]) + (filetime >> 24).to_bytes(5, "big")
    return base64.b64encode(cabeca + uuid.uuid4().bytes).decode("ascii")


def marcar_conversa_nova(msg, assunto: str) -> None:
    """Cada e-mail do sistema e uma conversa nova, mesmo com titulo repetido.

    Mandado na mao, o Gmail ja cria cada e-mail como conversa separada. Pelo
    SMTP ele juntava tudo que tinha o mesmo titulo: tres caminhoes do 041595
    viraram uma conversa so, e a fabrica respondeu dois de uma vez. Aqui vai
    o que o e-mail manual leva: identificador proprio (Gmail) e o comeco de
    conversa do Outlook, que e o que a fabrica usa.
    """
    msg["Message-ID"] = make_msgid(idstring=uuid.uuid4().hex, domain="atlanticofertlog.com.br")
    msg["Date"] = formatdate(localtime=True)
    msg["X-Entity-Ref-ID"] = uuid.uuid4().hex
    msg["Thread-Topic"] = assunto
    msg["Thread-Index"] = _thread_index_novo()


def send_email_message(
    destinatarios: list[str],
    assunto: str,
    corpo: str,
    anexos: list[str] | None = None,
    imagens_inline: dict[str, str] | None = None,
) -> bool:
    """imagens_inline mapeia um Content-ID (sem os "<>") pro caminho de uma
    imagem no disco - referencie no HTML do corpo via <img src="cid:o_id">
    pra ela aparecer embutida na mensagem, tipo uma assinatura."""
    anexos = anexos or []
    imagens_inline = imagens_inline or {}

    corpo_msg = MIMEMultipart("related")
    corpo_msg.attach(MIMEText(corpo, "html"))
    for cid, caminho_imagem in imagens_inline.items():
        if not os.path.exists(caminho_imagem):
            continue
        with open(caminho_imagem, "rb") as f:
            imagem = MIMEImage(f.read())
        imagem.add_header("Content-ID", f"<{cid}>")
        imagem.add_header("Content-Disposition", "inline", filename=os.path.basename(caminho_imagem))
        corpo_msg.attach(imagem)

    msg = MIMEMultipart("mixed")
    msg["From"] = settings.gmail_sender_email
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = assunto
    marcar_conversa_nova(msg, assunto)
    msg.attach(corpo_msg)

    for caminho_arquivo in anexos:
        if not os.path.exists(caminho_arquivo):
            continue
        ctype, encoding = mimetypes.guess_type(caminho_arquivo)
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        with open(caminho_arquivo, "rb") as attachment:
            part = MIMEBase(maintype, subtype)
            part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=os.path.basename(caminho_arquivo))
        msg.attach(part)

    server = smtplib.SMTP("smtp.gmail.com", 587)
    try:
        server.starttls()
        server.login(settings.gmail_sender_email, settings.gmail_app_password_send)
        server.sendmail(settings.gmail_sender_email, destinatarios, msg.as_string())
    finally:
        server.quit()

    return True
