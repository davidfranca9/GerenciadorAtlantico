"""Baixa manual: tonelada que saiu do pedido sem agendamento.

O 040393 carregou MAP e UREIA fora do sistema, e o 041595 teve UREIA que a
fabrica disse que o pedido nem tinha. Sem isso o saldo ficava preso.
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
from app.models import Agendamento, AgendamentoEmail, AgendamentoItem, BaixaPedido, Pedido  # noqa: E402
from app.routers import pedidos  # noqa: E402
from app.servicos import saldo_pedidos  # noqa: E402
from tests.apoio_documentos import banco_em_memoria  # noqa: E402

UREIA = "UREIA PRILL MICROGRANULADA 46% N"


@pytest.fixture
def db():
    sessao = banco_em_memoria(Pedido, BaixaPedido, Agendamento, AgendamentoItem, AgendamentoEmail)
    sessao.add_all([
        Pedido(id=44, contrato="041595", cliente="CARLOS LUCAS MENDES", produto=UREIA, toneladas_total=72, toneladas_usadas=40),
        Pedido(id=60, contrato="040393", cliente="MGX FLORESTAL", produto="MAP PURIFICADO 12.61.00", toneladas_total=30, toneladas_usadas=0),
    ])
    sessao.commit()
    yield sessao
    sessao.close()


@pytest.fixture
def cliente(db):
    app = FastAPI()
    app.include_router(pedidos.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"email": "dono@atlantico.com"})()
    return TestClient(app)


def test_baixa_fecha_o_que_sobrou_do_pedido(cliente, db):
    resposta = cliente.post("/pedidos/44/baixa", json={"toneladas": 32, "motivo": "pedido nao tem ureia"})
    assert resposta.status_code == 200, resposta.text
    pedido = resposta.json()
    assert pedido["toneladas_usadas"] == 72 and pedido["toneladas_restante"] == 0 and pedido["fechado"] is True
    assert [(b["toneladas"], b["motivo"], b["criado_por"]) for b in pedido["baixas"]] == [
        (32.0, "pedido nao tem ureia", "dono@atlantico.com"),
    ]


def test_baixa_de_tudo_e_de_parte(cliente, db):
    assert cliente.post("/pedidos/60/baixa", json={"toneladas": 10}).json()["toneladas_restante"] == 20
    assert cliente.post("/pedidos/60/baixa", json={"toneladas": 20}).json()["toneladas_restante"] == 0
    assert len(db.get(Pedido, 60).baixas) == 2


def test_nao_da_baixa_de_mais_do_que_sobra(cliente, db):
    resposta = cliente.post("/pedidos/44/baixa", json={"toneladas": 33})
    assert resposta.status_code == 400
    assert "32" in resposta.json()["detail"]
    assert cliente.post("/pedidos/44/baixa", json={"toneladas": 0}).status_code == 400
    assert cliente.post("/pedidos/44/baixa", json={"toneladas": -5}).status_code == 400
    assert cliente.post("/pedidos/999/baixa", json={"toneladas": 1}).status_code == 404
    assert db.get(Pedido, 44).toneladas_usadas == 40


def test_desfazer_devolve_o_saldo(cliente, db):
    baixa = cliente.post("/pedidos/44/baixa", json={"toneladas": 32}).json()["baixas"][0]
    voltou = cliente.delete(f"/pedidos/baixas/{baixa['id']}")
    assert voltou.status_code == 200
    assert voltou.json()["toneladas_restante"] == 32 and voltou.json()["baixas"] == []
    assert cliente.delete(f"/pedidos/baixas/{baixa['id']}").status_code == 404


def test_conciliacao_nao_apaga_a_baixa_manual(cliente, db):
    cliente.post("/pedidos/44/baixa", json={"toneladas": 32})
    # O que estava agendado antes continua contando junto com a baixa.
    agendamento = Agendamento(id=1, supplier="Fertimaxi", status="Aguardando Agendamento")
    agendamento.itens = [AgendamentoItem(pedido="041595", produto=UREIA, toneladas=40, pedido_ref_id=44)]
    db.add(agendamento)
    db.commit()

    conciliacao = saldo_pedidos.conciliar(db, aplicar=True)
    assert conciliacao["mudancas"] == []
    assert db.get(Pedido, 44).toneladas_usadas == 72


def test_excluir_o_pedido_leva_as_baixas(cliente, db):
    cliente.post("/pedidos/60/baixa", json={"toneladas": 30})
    assert cliente.delete("/pedidos/60").status_code == 200
    assert db.query(BaixaPedido).count() == 0
