"""E-mails separados em Recebidos e Enviados.

O sistema se copia nos envios e a caixa de entrada misturava o que chegou com
o que saiu. Nenhum Gmail de verdade aqui: a conexao IMAP e simulada.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos import email_inbox  # noqa: E402

LIST_DO_GMAIL = [
    b'(\\HasNoChildren) "/" "INBOX"',
    b'(\\HasChildren \\Noselect) "/" "[Gmail]"',
    b'(\\All \\HasNoChildren) "/" "[Gmail]/Todos os e-mails"',
    b'(\\HasNoChildren \\Sent) "/" "[Gmail]/E-mails enviados"',
    b'(\\HasNoChildren \\Trash) "/" "[Gmail]/Lixeira"',
]
CABECALHO = (
    b"From: Atlantico Fertlog <atlanticofertlog.comercial@gmail.com>\r\n"
    b"To: agendamento@fertimaxi.com.br\r\nSubject: AUTORIZACAO AGENDAMENTO\r\n"
    b"Date: Thu, 17 Sep 2026 12:44:00 -0300\r\n\r\n"
)


class ImapFalso:
    def __init__(self):
        self.selecoes, self.buscas = [], []

    def list(self):
        return "OK", LIST_DO_GMAIL

    def select(self, nome, readonly=False):
        self.selecoes.append((nome, readonly))
        return "OK", [b"2"]

    def search(self, charset, *criterios):
        self.buscas.append(criterios)
        if criterios[0] == "X-GM-MSGID":
            return "OK", [b"7"]
        if criterios[0] == "X-GM-THRID":
            return "OK", [b"5 7"]
        return "OK", [b"1 2"]

    def fetch(self, numeros, partes):
        if partes == "(X-GM-THRID)":
            return "OK", [b"7 (X-GM-THRID 999)"]
        if partes == "(X-GM-MSGID)":
            return "OK", [b"5 (X-GM-MSGID 1111)", b"7 (X-GM-MSGID 2222)"]
        return "OK", [
            (b"1 (X-GM-MSGID 1111 FLAGS (\\Seen) BODY[HEADER.FIELDS (FROM TO SUBJECT DATE)] {160}", CABECALHO), b")",
            (b"2 (X-GM-MSGID 2222 FLAGS () BODY[HEADER.FIELDS (FROM TO SUBJECT DATE)] {160}", CABECALHO), b")",
        ]


@pytest.fixture
def imap(monkeypatch):
    falso = ImapFalso()
    monkeypatch.setattr(email_inbox, "_obter_conexao", lambda: falso)
    monkeypatch.setattr(email_inbox, "_caixas_especiais", {})
    monkeypatch.setattr(email_inbox, "_selecao_atual", None)
    return falso


def test_nome_das_pastas_pelo_atributo_e_nao_pelo_idioma():
    assert email_inbox.nome_da_caixa_especial(LIST_DO_GMAIL, "\\Sent") == "[Gmail]/E-mails enviados"
    assert email_inbox.nome_da_caixa_especial(LIST_DO_GMAIL, "\\All") == "[Gmail]/Todos os e-mails"
    assert email_inbox.nome_da_caixa_especial(LIST_DO_GMAIL, "\\Drafts") == ""


def test_recebidos_nao_mostra_o_que_a_conta_mandou():
    assert email_inbox.consulta_da_pasta("", "recebidos") == "-category:promotions -from:me"
    assert email_inbox.consulta_da_pasta("from:fertimaxi", "recebidos") == "from:fertimaxi -from:me"
    assert email_inbox.consulta_da_pasta("", "enviados") == ""
    assert email_inbox.consulta_da_pasta("fertimaxi", "enviados") == "fertimaxi"


def test_enviados_abre_a_pasta_de_enviados_e_devolve_o_id_do_gmail(imap):
    lista = email_inbox.listar_mensagens(1, 25, "", "enviados")
    assert imap.selecoes == [('"[Gmail]/E-mails enviados"', True)]
    assert imap.buscas == [("ALL",)]
    # Mais nova primeiro, com o id que nao muda de pasta pra pasta.
    assert [m["id"] for m in lista["mensagens"]] == ["2222", "1111"]
    assert lista["mensagens"][0]["para"] == "agendamento@fertimaxi.com.br"
    assert lista["pasta"] == "enviados"


def test_recebidos_filtra_na_caixa_de_entrada(imap):
    email_inbox.listar_mensagens(1, 25, "", "recebidos")
    assert imap.selecoes == [('"INBOX"', True)]
    assert imap.buscas == [("X-GM-RAW", '"-category:promotions -from:me"')]


def test_conversa_junta_o_que_chegou_e_o_que_saiu(imap):
    assert email_inbox.obter_thread("2222") == ["1111", "2222"]
    assert imap.selecoes == [('"[Gmail]/Todos os e-mails"', True)]
    assert imap.buscas[0] == ("X-GM-MSGID", "2222")


def test_pasta_ja_aberta_nao_e_reaberta(imap):
    email_inbox.obter_thread("2222")
    email_inbox.obter_thread("1111")
    assert len(imap.selecoes) == 1


def test_id_que_nao_e_do_gmail_e_recusado(imap):
    with pytest.raises(email_inbox.InboxIndisponivel):
        email_inbox.obter_thread("../1")


def test_pasta_invalida(imap):
    with pytest.raises(email_inbox.InboxIndisponivel):
        email_inbox.listar_mensagens(1, 25, "", "lixeira")
