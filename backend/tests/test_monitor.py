"""Diagnostico das rotinas automaticas e a trava que evita coleta repetida.

Em 25/09/2026 a API engasgava em ondas e nao dava pra saber qual rotina
estava segurando o servidor.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import get_current_user  # noqa: E402
from app.database import get_db  # noqa: E402
from app.routers import configuracoes  # noqa: E402
from app.servicos import coleta_automatica, monitor  # noqa: E402


@pytest.fixture(autouse=True)
def limpar():
    monitor._tarefas.clear()
    yield
    monitor._tarefas.clear()


def test_guarda_duracao_resultado_e_erro():
    monitor.registrar("e-mail", time.monotonic() - 3, resultado=2)
    monitor.registrar("e-mail", time.monotonic() - 1, erro="IMAP fora do ar")

    tarefa = monitor.estado()["tarefas"]["e-mail"]
    assert tarefa["execucoes"] == 2 and tarefa["falhas"] == 1
    assert tarefa["erro"] == "IMAP fora do ar"
    assert 0.9 <= tarefa["duracao_s"] <= 1.5
    # A pior volta nao se perde na volta seguinte.
    assert 2.9 <= tarefa["pior_duracao_s"] <= 3.5


def test_rajada_de_email_nao_dispara_coleta_a_cada_mensagem():
    assert coleta_automatica.pode_coletar_agora(0.0, 1000.0) is True
    assert coleta_automatica.pode_coletar_agora(1000.0, 1010.0) is False
    assert coleta_automatica.pode_coletar_agora(1000.0, 1061.0) is True


def test_rota_de_diagnostico_so_pra_administrador():
    app = FastAPI()
    app.include_router(configuracoes.router)
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"role": "admin", "email": "dono@x.com"})()
    monitor.registrar("carregamentos do Bsoft", time.monotonic() - 2, resultado=5)

    dados = TestClient(app).get("/configuracoes/diagnostico").json()
    assert dados["tarefas"]["carregamentos do Bsoft"]["resultado"] == 5
    assert "banco" in dados and "agora" in dados

    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"role": "user", "email": "op@x.com"})()
    assert TestClient(app).get("/configuracoes/diagnostico").status_code == 403
