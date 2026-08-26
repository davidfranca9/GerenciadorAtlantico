"""Envio de e-mail (Gmail SMTP). Portado de servicos/comunicacao.py sem tkinter."""
from __future__ import annotations

import mimetypes
import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import settings


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
