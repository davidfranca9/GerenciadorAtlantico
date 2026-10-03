"""Pedido parado: produto que ninguem agenda ha dias demais acende na tela.

Regra pedida: 100% em aberto passa de 10 dias, o nome do produto fica
amarelo; passa de 20, vermelho. Agendado pela metade, muda so a cor das
toneladas que sobraram. Tudo agendado nao acende nada.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.apoio_documentos import banco_em_memoria, usuario_de_teste  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import get_current_user  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models import Agendamento, AgendamentoItem, BaixaPedido, Pedido  # noqa: E402
from app.routers import pedidos as rotas_pedidos  # noqa: E402

AGORA = datetime.utcnow()


def dias_atras(dias: int) -> datetime:
    return AGORA - timedelta(days=dias)


@pytest.fixture
def db():
    sessao = banco_em_memoria(Pedido, BaixaPedido, Agendamento, AgendamentoItem)
    sessao.add_all([
        # Novo em folha: nada a cobrar ainda.
        Pedido(id=1, contrato="042001", produto="MAP", toneladas_total=30, created_at=dias_atras(5)),
        # Parado ha 15 dias, ninguem agendou nada.
        Pedido(id=2, contrato="042002", produto="KCL", toneladas_total=30, created_at=dias_atras(15)),
        # Parado ha 25 dias.
        Pedido(id=3, contrato="042003", produto="UREIA", toneladas_total=30, created_at=dias_atras(25)),
        # Agendado pela metade, e o agendamento foi ontem.
        Pedido(id=4, contrato="042004", produto="SSP", toneladas_total=30, toneladas_usadas=10, created_at=dias_atras(40)),
        # Agendado pela metade, mas o ultimo agendamento foi ha 16 dias.
        Pedido(id=5, contrato="042005", produto="NPK", toneladas_total=30, toneladas_usadas=10, created_at=dias_atras(40)),
        # Tudo agendado: nao acende.
        Pedido(id=6, contrato="042006", produto="MAP", toneladas_total=30, toneladas_usadas=30, created_at=dias_atras(40)),
    ])
    sessao.add_all([
        Agendamento(id=10, created_at=dias_atras(1), itens=[AgendamentoItem(pedido="042004", produto="SSP", pedido_ref_id=4, toneladas=10)]),
        Agendamento(id=11, created_at=dias_atras(16), itens=[AgendamentoItem(pedido="042005", produto="NPK", pedido_ref_id=5, toneladas=10)]),
        Agendamento(id=12, created_at=dias_atras(30), itens=[AgendamentoItem(pedido="042006", produto="MAP", pedido_ref_id=6, toneladas=30)]),
    ])
    sessao.commit()
    yield sessao
    sessao.close()


@pytest.fixture
def cliente(db):
    app = FastAPI()
    app.include_router(rotas_pedidos.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: usuario_de_teste("/pedidos")
    return TestClient(app)


def alertas(cliente) -> dict[int, dict | None]:
    resposta = cliente.get("/pedidos", params={"mostrar_esgotados": True})
    assert resposta.status_code == 200, resposta.text
    return {p["id"]: p["alerta"] for p in resposta.json()}


def test_pedido_recente_nao_acende(cliente):
    assert alertas(cliente)[1] is None


def test_dez_dias_sem_agendar_pinta_o_produto_de_amarelo(cliente):
    assert alertas(cliente)[2] == {"dias": 15, "nivel": "amarelo", "onde": "produto"}


def test_vinte_dias_sem_agendar_pinta_de_vermelho(cliente):
    assert alertas(cliente)[3] == {"dias": 25, "nivel": "vermelho", "onde": "produto"}


def test_agendado_ontem_nao_acende_mesmo_com_pedido_velho(cliente):
    assert alertas(cliente)[4] is None


def test_saldo_esquecido_acende_so_nas_toneladas(cliente):
    assert alertas(cliente)[5] == {"dias": 16, "nivel": "amarelo", "onde": "saldo"}


def test_tudo_agendado_nao_acende(cliente):
    assert alertas(cliente)[6] is None


def test_item_antigo_sem_vinculo_vale_pelo_numero_e_produto(cliente, db):
    """Agendamento de antes do pedido_ref_id: casa por pedido + produto."""
    db.add(Agendamento(id=13, created_at=dias_atras(2), itens=[
        AgendamentoItem(pedido="042002", produto="KCL", toneladas=5),
    ]))
    db.get(Pedido, 2).toneladas_usadas = 5
    db.commit()
    assert alertas(cliente)[2] is None
