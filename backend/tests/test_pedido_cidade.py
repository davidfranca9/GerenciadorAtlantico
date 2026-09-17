"""Definir a cidade de um pedido que a leitura do PDF deixou sem.

So entra cidade do cadastro, no formato da leitura ("Nome-UF") - e o que a
cotacao de frete usa pra achar a tarifa do destino.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import get_current_user  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models import Agendamento, AgendamentoItem, Cidade, Pedido, RespostaFabrica, BaixaPedido  # noqa: E402
from app.routers import pedidos  # noqa: E402
from tests.apoio_documentos import banco_em_memoria  # noqa: E402


@pytest.fixture
def db():
    sessao = banco_em_memoria(Pedido, BaixaPedido, Cidade, Agendamento, AgendamentoItem, RespostaFabrica)
    sessao.add_all([
        Cidade(nome="Águas Vermelhas", uf="MG", ibge="3101003"),
        Cidade(nome="Montes Claros", uf="MG", ibge="3143302"),
        # O 041555 real: dois produtos, sem cidade.
        Pedido(id=68, contrato="041555", cliente="WAGMAR JOSÉ DE OLIVEIRA", cidade="", toneladas_total=60,
               cidades_candidatas='["Águas Vermelhas-MG", "Montes Claros-MG"]'),
        Pedido(id=69, contrato="041555", cliente="WAGMAR JOSÉ DE OLIVEIRA", cidade="", toneladas_total=10),
        Pedido(id=4, contrato="041556", cliente="WAGMAR JOSE DE OLIVEIRA", cidade="Águas Vermelhas-MG", toneladas_total=32),
    ])
    sessao.commit()
    yield sessao
    sessao.close()


@pytest.fixture
def cliente(db):
    app = FastAPI()
    app.include_router(pedidos.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: None
    return TestClient(app)


def test_define_a_cidade_so_nos_pedidos_escolhidos(cliente, db):
    resposta = cliente.patch("/pedidos/cidade", json={"pedido_ids": [68, 69], "cidade": "aguas vermelhas", "uf": "mg"})
    assert resposta.status_code == 200, resposta.text
    # Grava com o acento e a caixa do cadastro, nao do que foi digitado.
    assert resposta.json()["cidade"] == "Águas Vermelhas-MG"
    assert db.get(Pedido, 68).cidade == "Águas Vermelhas-MG"
    assert db.get(Pedido, 69).cidade == "Águas Vermelhas-MG"
    assert db.get(Pedido, 68).cidades_candidatas == ""


def test_cidade_fora_do_cadastro_e_recusada(cliente, db):
    resposta = cliente.patch("/pedidos/cidade", json={"pedido_ids": [68], "cidade": "Atlantida", "uf": "MG"})
    assert resposta.status_code == 400
    assert "nao encontrada" in resposta.json()["detail"]
    assert db.get(Pedido, 68).cidade == ""


def test_uf_errada_e_recusada(cliente, db):
    resposta = cliente.patch("/pedidos/cidade", json={"pedido_ids": [68], "cidade": "Águas Vermelhas", "uf": "BA"})
    assert resposta.status_code == 400
    assert db.get(Pedido, 68).cidade == ""


def test_pedido_que_nao_existe(cliente, db):
    resposta = cliente.patch("/pedidos/cidade", json={"pedido_ids": [68, 999], "cidade": "Águas Vermelhas", "uf": "MG"})
    assert resposta.status_code == 404
    assert db.get(Pedido, 68).cidade == ""


def test_sem_pedidos(cliente):
    assert cliente.patch("/pedidos/cidade", json={"pedido_ids": [], "cidade": "Águas Vermelhas", "uf": "MG"}).status_code == 400


def test_listagem_leva_as_cidades_possiveis(cliente):
    lista = {p["id"]: p for p in cliente.get("/pedidos").json()}
    assert lista[68]["cidades_candidatas"] == ["Águas Vermelhas-MG", "Montes Claros-MG"]
    assert lista[69]["cidades_candidatas"] == []
    assert lista[4]["cidades_candidatas"] == []


def test_correcao_da_cidade_chega_nos_agendamentos(cliente, db):
    # 041594: lido como Capitao-RS, o destino era Capitao Eneas-MG. Os
    # agendamentos ja criados guardam a copia errada.
    db.add_all([
        Cidade(nome="Capitão", uf="RS", ibge="4304697"),
        Cidade(nome="Capitão Enéas", uf="MG", ibge="3112703"),
        Pedido(id=47, contrato="041594", cliente="CARLOS LUCAS MENDES", cidade="Capitão-RS", toneladas_total=24),
        Agendamento(id=80, supplier="Fertimaxi", itens=[
            AgendamentoItem(id=138, pedido="041594", cidade="Capitão-RS", toneladas=24, pedido_ref_id=47),
            # Outro pedido no mesmo agendamento nao muda.
            AgendamentoItem(id=140, pedido="041595", cidade="Taiobeiras-MG", toneladas=8, pedido_ref_id=4),
        ]),
        # Mudado a mao no agendamento: fica como esta.
        Agendamento(id=81, supplier="Fertimaxi", itens=[
            AgendamentoItem(id=139, pedido="041594", cidade="Montes Claros-MG", toneladas=8, pedido_ref_id=47),
        ]),
    ])
    db.commit()

    resposta = cliente.patch("/pedidos/cidade", json={"pedido_ids": [47], "cidade": "Capitão Enéas", "uf": "MG"})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["agendamento_itens_corrigidos"] == 1
    assert db.get(Pedido, 47).cidade == "Capitão Enéas-MG"
    assert db.get(AgendamentoItem, 138).cidade == "Capitão Enéas-MG"
    assert db.get(AgendamentoItem, 140).cidade == "Taiobeiras-MG"
    assert db.get(AgendamentoItem, 139).cidade == "Montes Claros-MG"
