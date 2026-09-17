"""Corrigir a cidade de um item do agendamento, so dele.

O 041594 foi lido como Capitao-RS; o destino era Capitao Eneas-MG. A
correcao pedida foi so no agendamento de 18/09 - o pedido e o agendamento
antigo do mesmo pedido ficam como estao.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.apoio_documentos import banco_em_memoria, roteador_documentos  # noqa: E402

roteador_documentos()  # substitui o gerador de O.C. em HTML quando o WeasyPrint nao carrega

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import get_current_user  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models import Agendamento, AgendamentoEmail, AgendamentoItem, Cidade, Pedido  # noqa: E402
from app.routers import agendamentos as rotas_agendamentos  # noqa: E402


@pytest.fixture
def db():
    sessao = banco_em_memoria(Pedido, Cidade, Agendamento, AgendamentoItem, AgendamentoEmail)
    sessao.add_all([
        Cidade(nome="Capitão", uf="RS", ibge="4304697"),
        Cidade(nome="Capitão Enéas", uf="MG", ibge="3112703"),
        Pedido(id=47, contrato="041594", cliente="CARLOS LUCAS MENDES", cidade="Capitão-RS", toneladas_total=56),
        Agendamento(id=80, supplier="Fertimaxi", itens=[
            AgendamentoItem(id=138, pedido="041594", cidade="Capitão-RS", toneladas=24, pedido_ref_id=47),
        ]),
        Agendamento(id=137, supplier="Fertimaxi", itens=[
            AgendamentoItem(id=237, pedido="041594", cidade="Capitão-RS", toneladas=32, pedido_ref_id=47),
            AgendamentoItem(id=238, pedido="038864", cidade="Taiobeiras-MG", toneladas=8),
        ]),
    ])
    sessao.commit()
    yield sessao
    sessao.close()


@pytest.fixture
def cliente(db):
    app = FastAPI()
    app.include_router(rotas_agendamentos.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: None
    return TestClient(app)


def test_corrige_so_o_item_escolhido(cliente, db):
    resposta = cliente.patch("/agendamentos/137/itens/237/cidade", json={"cidade": "capitao eneas", "uf": "mg"})
    assert resposta.status_code == 200, resposta.text
    itens = {i["id"]: i["cidade"] for i in resposta.json()["itens"]}
    # Com o acento e a caixa do cadastro, nao do que foi digitado.
    assert itens == {237: "Capitão Enéas-MG", 238: "Taiobeiras-MG"}
    assert db.get(AgendamentoItem, 138).cidade == "Capitão-RS"
    assert db.get(Pedido, 47).cidade == "Capitão-RS"


def test_cidade_fora_do_cadastro_e_recusada(cliente, db):
    resposta = cliente.patch("/agendamentos/137/itens/237/cidade", json={"cidade": "Capitão Poço", "uf": "MG"})
    assert resposta.status_code == 400
    assert "nao encontrada" in resposta.json()["detail"]
    assert db.get(AgendamentoItem, 237).cidade == "Capitão-RS"


def test_item_de_outro_agendamento(cliente, db):
    assert cliente.patch("/agendamentos/80/itens/237/cidade", json={"cidade": "Capitão Enéas", "uf": "MG"}).status_code == 404
    assert db.get(AgendamentoItem, 237).cidade == "Capitão-RS"
