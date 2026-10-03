"""Dashboard de outra semana: o que ja esta agendado pra semana que vem
precisa aparecer antes de ela chegar."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.apoio_documentos import banco_em_memoria, usuario_de_teste  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import get_current_user  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models import Agendamento, AgendamentoItem, Pedido  # noqa: E402
from app.routers import dashboard as rotas_dashboard  # noqa: E402

HOJE = date.today()
SEGUNDA = HOJE - timedelta(days=HOJE.weekday())
PROXIMA_QUARTA = SEGUNDA + timedelta(days=9)


def br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


@pytest.fixture
def db():
    sessao = banco_em_memoria(Pedido, Agendamento, AgendamentoItem)
    sessao.add_all([
        Agendamento(id=1, supplier="Fertimaxi", loading_date=br(SEGUNDA), total_tons=40, status="Agendado"),
        Agendamento(id=2, supplier="Heringer", loading_date=br(PROXIMA_QUARTA), total_tons=34, status="Agendado"),
    ])
    sessao.commit()
    yield sessao
    sessao.close()


@pytest.fixture
def cliente(db):
    app = FastAPI()
    app.include_router(rotas_dashboard.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: usuario_de_teste("/dashboard")
    return TestClient(app)


def test_semana_atual_e_o_padrao(cliente):
    semana = cliente.get("/dashboard/resumo").json()["semana"]
    assert semana["inicio"] == br(SEGUNDA)
    assert semana["eh_semana_atual"] is True
    assert semana["toneladas_total"] == 40
    assert semana["proxima"] == (SEGUNDA + timedelta(days=7)).isoformat()


def test_proxima_semana_mostra_o_que_ja_esta_agendado(cliente):
    proxima = cliente.get("/dashboard/resumo").json()["semana"]["proxima"]
    semana = cliente.get("/dashboard/resumo", params={"semana": proxima}).json()["semana"]
    assert semana["inicio"] == br(SEGUNDA + timedelta(days=7))
    assert semana["eh_semana_atual"] is False
    assert semana["toneladas_total"] == 34
    assert semana["agendamentos_total"] == 1
    # Quarta-feira: o terceiro dia da lista (segunda a sabado).
    assert semana["dias"][2]["toneladas"] == 34


def test_qualquer_dia_da_semana_serve_de_referencia(cliente):
    sexta = (SEGUNDA + timedelta(days=4)).isoformat()
    semana = cliente.get("/dashboard/resumo", params={"semana": sexta}).json()["semana"]
    assert semana["inicio"] == br(SEGUNDA)


def test_data_invalida_e_recusada(cliente):
    assert cliente.get("/dashboard/resumo", params={"semana": "semana que vem"}).status_code == 400
