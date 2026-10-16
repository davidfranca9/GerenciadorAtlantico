"""Gerar/enviar uma Ordem de Coleta nao pode reescrever a carga de outro caminhao.

A tela guardava o id do ultimo agendamento e mandava junto no proximo envio.
O servidor, em vez de criar outro, REESCREVIA o antigo com a carga nova: o
primeiro agendamento sumia e o segundo nunca ganhava registro proprio. E o
e-mail saia ANTES da gravacao - se ela falhasse, a fabrica ficava avisada e
o sistema sem nada.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.apoio_documentos import banco_em_memoria, cliente_http, roteador_documentos  # noqa: E402

roteador_documentos()

from app.models import (Agendamento, AgendamentoEmail, AgendamentoItem, BaixaPedido, Cidade,  # noqa: E402
                        ListaEmail, Pedido, RespostaFabrica)

CLIENTE_A = "AGRODANTAS PRODUTOS AGRICOLAS LTDA"
CLIENTE_B = "RECANTO AGRONEGOCIOS LTDA"


def carga(contrato, produto, cliente, toneladas="32", **extra):
    return {"contrato": contrato, "produto": produto, "embalagem": "SACARIA", "toneladas": toneladas,
            "cidade": "Jaíba-MG", "cliente": cliente, **extra}


@pytest.fixture
def db():
    sessao = banco_em_memoria(Pedido, BaixaPedido, Cidade, Agendamento, AgendamentoItem,
                              AgendamentoEmail, RespostaFabrica, ListaEmail)
    sessao.add_all([
        Pedido(id=1, contrato="042666", produto="MAP 11-52-00", cliente=CLIENTE_A, toneladas_total=60),
        Pedido(id=2, contrato="043843", produto="SULFATO DE AMONIO", cliente=CLIENTE_B, toneladas_total=32),
    ])
    sessao.commit()
    yield sessao
    sessao.close()


@pytest.fixture
def api(db, monkeypatch):
    cliente, documentos = cliente_http(db)
    enviados = []
    monkeypatch.setattr(documentos, "send_email_message", lambda *a, **k: enviados.append(a) or "<id@teste>")
    return SimpleNamespace(http=cliente, documentos=documentos, enviados=enviados)


def enviar(api, produtos, **extra):
    corpo = {"template": "AFL", "produtos": produtos, "data_carregamento": "20/10/2026", **extra}
    return api.http.post("/ordens-coleta/enviar-autorizacao-email", json=corpo)


def test_id_de_outra_carga_nao_reescreve_o_agendamento_antigo(db, api):
    """O caso do Claus: o segundo caminhao reaproveitava o id do primeiro."""
    primeira = enviar(api, [carga("042666", "MAP 11-52-00", CLIENTE_A, pedido_id=1)])
    assert primeira.status_code == 200, primeira.text
    antigo = primeira.json()["agendamento_id"]

    segunda = enviar(api, [carga("043843", "SULFATO DE AMONIO", CLIENTE_B, pedido_id=2)], agendamento_id=antigo)

    assert segunda.status_code == 200, segunda.text
    novo = segunda.json()["agendamento_id"]
    assert novo != antigo
    # O primeiro continua com a carga dele.
    assert [i.pedido for i in db.get(Agendamento, antigo).itens] == ["042666"]
    assert [i.pedido for i in db.get(Agendamento, novo).itens] == ["043843"]
    # E cada pedido desconta o que e dele.
    assert db.get(Pedido, 1).toneladas_usadas == 32 and db.get(Pedido, 2).toneladas_usadas == 32


def test_mesma_carga_continua_no_mesmo_agendamento(db, api):
    """Gerar de novo a carga que ja existe atualiza ela - nao desconta o saldo
    duas vezes."""
    primeira = enviar(api, [carga("042666", "MAP 11-52-00", CLIENTE_A, toneladas="20", pedido_id=1)])
    antigo = primeira.json()["agendamento_id"]

    segunda = enviar(api, [carga("042666", "MAP 11-52-00", CLIENTE_A, toneladas="25", pedido_id=1)],
                     agendamento_id=antigo)

    assert segunda.json()["agendamento_id"] == antigo
    assert db.query(Agendamento).count() == 1
    assert db.get(Pedido, 1).toneladas_usadas == 25


def test_pedido_com_zero_a_esquerda_e_o_mesmo_pedido(db, api):
    primeira = enviar(api, [carga("042666", "MAP 11-52-00", CLIENTE_A, pedido_id=1)])
    antigo = primeira.json()["agendamento_id"]

    segunda = enviar(api, [carga("42666", "map 11-52-00", CLIENTE_A)], agendamento_id=antigo)

    assert segunda.json()["agendamento_id"] == antigo


def test_id_que_nao_existe_mais_cria_um_novo_em_vez_de_dar_404(db, api):
    """Dar 404 DEPOIS de mandar o e-mail deixava a fabrica avisada e o sistema
    sem agendamento: foi o que aconteceu com o pedido 043843."""
    resposta = enviar(api, [carga("043843", "SULFATO DE AMONIO", CLIENTE_B, pedido_id=2)], agendamento_id=999)

    assert resposta.status_code == 200, resposta.text
    assert db.query(Agendamento).count() == 1
    assert len(api.enviados) == 1


def test_o_agendamento_ja_esta_gravado_quando_o_e_mail_sai(db, api, monkeypatch):
    """Grava ANTES de mandar: se o registro nao puder ser feito, o e-mail nem
    sai."""
    visto = {}

    def envio(*a, **k):
        visto["agendamentos"] = db.query(Agendamento).count()
        return "<id@teste>"

    monkeypatch.setattr(api.documentos, "send_email_message", envio)

    enviar(api, [carga("043843", "SULFATO DE AMONIO", CLIENTE_B, pedido_id=2)])

    assert visto["agendamentos"] == 1


def test_e_mail_que_falha_nao_deixa_agendamento_nem_desconta_saldo(db, api, monkeypatch):
    def falha(*a, **k):
        raise RuntimeError("SMTP fora do ar")

    monkeypatch.setattr(api.documentos, "send_email_message", falha)

    resposta = enviar(api, [carga("043843", "SULFATO DE AMONIO", CLIENTE_B, pedido_id=2)])

    assert resposta.status_code == 502
    assert db.query(Agendamento).count() == 0
    assert db.get(Pedido, 2).toneladas_usadas == 0
