"""Cada e-mail do sistema sai como conversa nova, mesmo com o titulo repetido.

Tres caminhoes do 041595 sairam com o mesmo titulo e o Gmail juntou tudo
numa conversa so. Nenhum e-mail sai daqui: o SMTP e simulado.
"""
from __future__ import annotations

import base64
import email
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos import comunicacao  # noqa: E402

ASSUNTO = "AUTORIZAÇÃO AGENDAMENTO: CARLOS LUCAS MENDES - Nº 041595"


class SmtpFalso:
    enviados: list[str] = []

    def __init__(self, *args, **kwargs):
        pass

    def starttls(self):
        pass

    def login(self, *args):
        pass

    def sendmail(self, remetente, destinatarios, texto):
        SmtpFalso.enviados.append(texto)

    def quit(self):
        pass


def enviar_dois(monkeypatch):
    SmtpFalso.enviados = []
    monkeypatch.setattr(comunicacao.smtplib, "SMTP", SmtpFalso)
    for _ in range(2):
        comunicacao.send_email_message(["fabrica@example.com"], ASSUNTO, "<p>oi</p>")
    return [email.message_from_string(texto) for texto in SmtpFalso.enviados]


def test_mesmo_titulo_sai_com_identificadores_diferentes(monkeypatch):
    primeiro, segundo = enviar_dois(monkeypatch)
    for cabecalho in ("Message-ID", "X-Entity-Ref-ID", "Thread-Index"):
        assert primeiro[cabecalho] and segundo[cabecalho], cabecalho
        assert primeiro[cabecalho] != segundo[cabecalho], cabecalho
    assert primeiro["Date"]
    # Nenhum dos dois se diz resposta de outro.
    assert primeiro["In-Reply-To"] is None and primeiro["References"] is None


def test_thread_index_no_formato_do_outlook(monkeypatch):
    primeiro, _ = enviar_dois(monkeypatch)
    bruto = base64.b64decode(primeiro["Thread-Index"])
    assert len(bruto) == 22
    assert bruto[0] == 1
    assert str(email.header.make_header(email.header.decode_header(primeiro["Thread-Topic"]))) == ASSUNTO
