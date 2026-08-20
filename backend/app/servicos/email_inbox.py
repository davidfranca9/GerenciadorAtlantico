"""Leitura da caixa de entrada do Gmail via IMAP.

Usa o mesmo app password ja previsto em config.py (GMAIL_APP_PASSWORD_IMAP)
para logar via IMAP e listar/ler as mensagens do INBOX, sem precisar de
OAuth/credenciais do Google Cloud Console.
"""
from __future__ import annotations

import base64
import email
import imaplib
import re
import threading
from email.header import decode_header
from email.utils import parsedate_to_datetime

from ..config import settings

IMAP_HOST = "imap.gmail.com"

_lock = threading.Lock()
_conexao_ativa: imaplib.IMAP4_SSL | None = None


class InboxIndisponivel(Exception):
    pass


def credenciais_limpas() -> tuple[str, str]:
    usuario = re.sub(r"\s+", "", settings.gmail_sender_email or "")
    senha = re.sub(r"\s+", "", settings.gmail_app_password_imap or "")
    return usuario, senha


def _logar(usuario: str, senha: str) -> imaplib.IMAP4_SSL:
    conexao = imaplib.IMAP4_SSL(IMAP_HOST)
    try:
        conexao.login(usuario, senha)
    except imaplib.IMAP4.error as exc:
        raise InboxIndisponivel(
            "Login IMAP falhou. Confira: (1) a senha de app em GMAIL_APP_PASSWORD_IMAP esta correta e sem "
            "espacos, (2) o IMAP esta habilitado nas configuracoes do Gmail (Config. > Encaminhamento e "
            f"POP/IMAP > Ativar IMAP) da conta {usuario}. Erro original: {exc}"
        ) from exc
    return conexao


def _obter_conexao() -> imaplib.IMAP4_SSL:
    """Reaproveita uma unica conexao IMAP entre requisicoes (evita repetir o
    handshake TLS + login a cada acao, que era o principal motivo da lentidao).
    Verifica com NOOP se ainda esta viva antes de reusar; reconecta se nao."""
    global _conexao_ativa

    if _conexao_ativa is not None:
        try:
            _conexao_ativa.noop()
            return _conexao_ativa
        except Exception:
            try:
                _conexao_ativa.logout()
            except Exception:
                pass
            _conexao_ativa = None

    usuario, senha = credenciais_limpas()
    if not usuario or not senha:
        raise InboxIndisponivel("GMAIL_SENDER_EMAIL / GMAIL_APP_PASSWORD_IMAP nao configurados")
    _conexao_ativa = _logar(usuario, senha)
    return _conexao_ativa


def _decodificar(valor: str | None) -> str:
    if not valor:
        return ""
    texto = ""
    for parte, codificacao in decode_header(valor):
        if isinstance(parte, bytes):
            texto += parte.decode(codificacao or "utf-8", errors="replace")
        else:
            texto += parte
    return texto


def _extrair_remetente(msg: email.message.Message) -> dict:
    bruto = _decodificar(msg.get("From", ""))
    if "<" in bruto and ">" in bruto:
        nome, endereco = bruto.rsplit("<", 1)
        return {"nome": nome.strip().strip('"'), "email": endereco.strip(">").strip()}
    return {"nome": bruto, "email": bruto}


def _extrair_data(msg: email.message.Message) -> str:
    bruto = msg.get("Date")
    if not bruto:
        return ""
    try:
        return parsedate_to_datetime(bruto).isoformat()
    except (TypeError, ValueError):
        return bruto


def listar_mensagens(pagina: int = 1, tamanho_pagina: int = 25) -> dict:
    with _lock:
        conexao = _obter_conexao()
        status, _ = conexao.select("INBOX", readonly=True)
        if status != "OK":
            raise InboxIndisponivel("Nao foi possivel abrir a caixa de entrada")

        status, dados = conexao.search(None, "X-GM-RAW", '"-category:promotions"')
        if status != "OK":
            raise InboxIndisponivel("Nao foi possivel listar as mensagens")

        todos_ids = dados[0].split()
        todos_ids.reverse()
        total = len(todos_ids)
        inicio = (pagina - 1) * tamanho_pagina
        pagina_ids = todos_ids[inicio : inicio + tamanho_pagina]

        if not pagina_ids:
            return {"mensagens": [], "total": total, "pagina": pagina, "tamanho_pagina": tamanho_pagina}

        # Busca todas as mensagens da pagina numa unica chamada FETCH (uma
        # unica ida-e-volta ao servidor) em vez de uma chamada por mensagem.
        status, dados_msg = conexao.fetch(b",".join(pagina_ids), "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        if status != "OK":
            raise InboxIndisponivel("Nao foi possivel buscar as mensagens")

        por_id: dict[bytes, dict] = {}
        for item in dados_msg:
            if not isinstance(item, tuple):
                continue
            linha_info, cabecalho_bruto = item
            correspondencia = re.match(rb"(\d+) \(", linha_info)
            if not correspondencia:
                continue
            msg_id = correspondencia.group(1)
            msg = email.message_from_bytes(cabecalho_bruto)
            flags = imaplib.ParseFlags(linha_info)
            por_id[msg_id] = {
                "id": msg_id.decode(),
                "remetente": _extrair_remetente(msg),
                "assunto": _decodificar(msg.get("Subject", "")) or "(sem assunto)",
                "data": _extrair_data(msg),
                "lida": b"\\Seen" in flags,
            }

        mensagens = [por_id[mid] for mid in pagina_ids if mid in por_id]
        return {"mensagens": mensagens, "total": total, "pagina": pagina, "tamanho_pagina": tamanho_pagina}


def obter_mensagem(msg_id: str) -> dict:
    with _lock:
        conexao = _obter_conexao()
        status, _ = conexao.select("INBOX")
        if status != "OK":
            raise InboxIndisponivel("Nao foi possivel abrir a caixa de entrada")

        status, dados_msg = conexao.fetch(msg_id.encode(), "(BODY[])")
        if status != "OK" or not dados_msg or not isinstance(dados_msg[0], tuple):
            raise InboxIndisponivel("Mensagem nao encontrada")

        msg = email.message_from_bytes(dados_msg[0][1])

        corpo_html = ""
        corpo_texto = ""
        anexos: list[str] = []
        imagens_inline: dict[str, str] = {}

        if msg.is_multipart():
            for parte in msg.walk():
                content_type = parte.get_content_type()
                disposicao = str(parte.get("Content-Disposition", ""))
                content_id = (parte.get("Content-ID") or "").strip().strip("<>")

                if content_type.startswith("image/") and (content_id or "inline" in disposicao):
                    payload = parte.get_payload(decode=True)
                    if payload and content_id:
                        imagens_inline[content_id] = f"data:{content_type};base64,{base64.b64encode(payload).decode('ascii')}"
                    continue

                if "attachment" in disposicao:
                    anexos.append(_decodificar(parte.get_filename()) or "arquivo")
                    continue

                payload = parte.get_payload(decode=True)
                if payload is None:
                    continue
                texto = payload.decode(parte.get_content_charset() or "utf-8", errors="replace")
                if content_type == "text/html" and not corpo_html:
                    corpo_html = texto
                elif content_type == "text/plain" and not corpo_texto:
                    corpo_texto = texto
        else:
            payload = msg.get_payload(decode=True)
            texto = payload.decode(msg.get_content_charset() or "utf-8", errors="replace") if payload else ""
            if msg.get_content_type() == "text/html":
                corpo_html = texto
            else:
                corpo_texto = texto

        if corpo_html and imagens_inline:
            def _substituir_cid(match: re.Match) -> str:
                cid = match.group(1).strip("'\"")
                return f"cid:{cid}" if cid not in imagens_inline else imagens_inline[cid]

            corpo_html = re.sub(r"cid:([^\"'\)\s]+)", _substituir_cid, corpo_html)

        return {
            "id": msg_id,
            "remetente": _extrair_remetente(msg),
            "para": _decodificar(msg.get("To", "")),
            "assunto": _decodificar(msg.get("Subject", "")) or "(sem assunto)",
            "data": _extrair_data(msg),
            "corpo_html": corpo_html,
            "corpo_texto": corpo_texto,
            "anexos": anexos,
        }
