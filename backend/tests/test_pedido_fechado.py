"""Pedido que encheu nao some da tela de Pedidos.

O 041594 sumiu quando os agendamentos ocuparam as 64 t: a lista escondia todo
pedido sem saldo. Agora ele fica, marcado como carregamento fechado, e sai so
quando alguem tira na mao.
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
from app.models import Pedido, BaixaPedido  # noqa: E402
from app.routers import pedidos  # noqa: E402
from tests.apoio_documentos import banco_em_memoria  # noqa: E402

SUPER = "SUPER SIMPLES GR 19% P2O5 10% S 16% CA"
UREIA = "UREIA PRILL MICROGRANULADA 46% N"


@pytest.fixture
def db():
    sessao = banco_em_memoria(Pedido, BaixaPedido)
    sessao.add_all([
        Pedido(id=47, contrato="041594", cliente="CARLOS LUCAS MENDES", produto=SUPER, toneladas_total=56, toneladas_usadas=56),
        Pedido(id=48, contrato="041594", cliente="CARLOS LUCAS MENDES", produto=UREIA, toneladas_total=8, toneladas_usadas=8),
        Pedido(id=45, contrato="041595", cliente="CARLOS LUCAS MENDES", produto="CLORETO", toneladas_total=72, toneladas_usadas=40),
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


def ids(resposta):
    return sorted(p["id"] for p in resposta.json())


def tela_de_pedidos(cliente):
    return cliente.get("/pedidos", params={"mostrar_esgotados": True, "ocultar_retirados": True})


def test_pedido_que_encheu_continua_na_tela_marcado_como_fechado(cliente):
    lista = {p["id"]: p for p in tela_de_pedidos(cliente).json()}
    assert sorted(lista) == [45, 47, 48]
    assert lista[47]["fechado"] and lista[48]["fechado"]
    assert not lista[45]["fechado"]


def test_escolha_de_pedido_pra_agendar_continua_sem_os_cheios(cliente):
    assert ids(cliente.get("/pedidos")) == [45]


def test_tirar_da_lista_e_desfazer(cliente, db):
    resposta = cliente.post("/pedidos/retirar", json={"pedido_ids": [47, 48]})
    assert resposta.status_code == 200, resposta.text
    assert ids(tela_de_pedidos(cliente)) == [45]
    # Nao apaga: continua no banco e aparece pra quem pede os esgotados (edicao de agendamento).
    assert db.get(Pedido, 47) is not None
    assert ids(cliente.get("/pedidos", params={"mostrar_esgotados": True})) == [45, 47, 48]

    assert cliente.post("/pedidos/devolver", json={"pedido_ids": [47, 48]}).status_code == 200
    assert ids(tela_de_pedidos(cliente)) == [45, 47, 48]


def test_pedido_com_saldo_nao_sai_da_lista(cliente, db):
    resposta = cliente.post("/pedidos/retirar", json={"pedido_ids": [45]})
    assert resposta.status_code == 400
    assert "041595" in resposta.json()["detail"]
    assert db.get(Pedido, 45).retirado_em is None


def test_saldo_que_volta_traz_o_pedido_de_volta(cliente, db):
    cliente.post("/pedidos/retirar", json={"pedido_ids": [47]})
    # Agendamento cancelado devolve 32 t.
    db.get(Pedido, 47).toneladas_usadas = 24
    db.commit()
    assert 47 in ids(tela_de_pedidos(cliente))


def test_pedido_inexistente(cliente):
    assert cliente.post("/pedidos/retirar", json={"pedido_ids": [47, 999]}).status_code == 404
    assert cliente.post("/pedidos/retirar", json={"pedido_ids": []}).status_code == 400
