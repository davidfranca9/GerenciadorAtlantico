"""Quem apagou, quando e o quê.

Pedido e agendamento somem com um clique e nao deixavam rastro: quando
perguntavam "sumiu, quem apagou?", nao havia resposta - e sem os dados nao
dava nem pra refazer na mao.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.apoio_documentos import banco_em_memoria  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import get_current_user, require_admin  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models import (Agendamento, AgendamentoEmail, AgendamentoItem, BaixaPedido, Cidade,  # noqa: E402
                        Pedido, RegistroExclusao, RespostaFabrica, User)
from app.routers import admin as rotas_admin  # noqa: E402
from app.routers import pedidos as rotas_pedidos  # noqa: E402


@pytest.fixture
def db():
    sessao = banco_em_memoria(Pedido, BaixaPedido, Cidade, Agendamento, AgendamentoItem,
                              AgendamentoEmail, RespostaFabrica, RegistroExclusao, User)
    sessao.add(Pedido(id=7, contrato="042666", produto="MAP 11-52-00",
                      cliente="AGRODANTAS PRODUTOS AGRICOLAS LTDA", cidade="Jaíba-MG",
                      toneladas_total=15, toneladas_usadas=0))
    sessao.commit()
    yield sessao
    sessao.close()


@pytest.fixture
def cliente(db):
    app = FastAPI()
    app.include_router(rotas_pedidos.router)
    app.include_router(rotas_admin.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        email="claus@atlanticofertlog.com.br", role="admin",
    )
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(
        email="claus@atlanticofertlog.com.br", role="admin",
    )
    return TestClient(app)


def test_apagar_pedido_guarda_quem_apagou_e_o_que_era(cliente, db):
    assert cliente.delete("/pedidos/7").status_code == 200

    registro = db.query(RegistroExclusao).one()
    assert registro.tabela == "pedidos" and registro.registro_id == 7
    assert registro.usuario == "claus@atlanticofertlog.com.br"
    assert "042666" in registro.descricao and "AGRODANTAS" in registro.descricao
    # A linha inteira fica guardada: da pra refazer o pedido na mao.
    dados = json.loads(registro.dados)
    assert dados["contrato"] == "042666" and dados["toneladas_total"] == 15
    assert dados["cidade"] == "Jaíba-MG"


def test_a_lista_de_exclusoes_responde_quem_apagou(cliente):
    cliente.delete("/pedidos/7")

    resposta = cliente.get("/admin/usuarios/exclusoes")

    assert resposta.status_code == 200
    item = resposta.json()[0]
    assert item["tabela"] == "pedidos"
    assert item["usuario"] == "claus@atlanticofertlog.com.br"
    assert item["quando"]


def test_o_registro_quebrado_nao_impede_a_exclusao(cliente, db, monkeypatch):
    """Auditoria nao pode travar o usuario: se ela falhar (tabela que ainda
    nao subiu, por exemplo), o pedido sai igual - fica sem o rastro daquela
    linha, mas ninguem fica preso sem conseguir apagar."""
    from app.servicos import exclusoes

    def explode(*a, **k):
        raise RuntimeError("tabela nao existe")

    monkeypatch.setattr(exclusoes, "RegistroExclusao", explode)

    assert cliente.delete("/pedidos/7").status_code == 200
    assert db.get(Pedido, 7) is None
    assert db.query(RegistroExclusao).count() == 0
