"""Pedido "novo": chegou ha pouco e ninguem tirou carga dele ainda."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.pedidos import JANELA_PEDIDO_NOVO, _eh_novo, _to_dict  # noqa: E402

AGORA = datetime(2026, 9, 14, 12, 0)


def pedido(horas_atras=1.0, usadas=0.0, **extra):
    base = dict(
        id=1, created_at=AGORA - timedelta(hours=horas_atras), contrato="41556", produto="UREIA",
        embalagem="SACARIA", cidade="Montes Claros", cliente="WAGMAR", supplier="AFL",
        toneladas_total=32.0, toneladas_usadas=usadas,
    )
    base.update(extra)
    return SimpleNamespace(**base)


def test_recem_chegado_e_novo():
    assert _eh_novo(pedido(horas_atras=1), AGORA)


def test_o_da_sexta_a_noite_ainda_e_novo_na_segunda_de_manha():
    assert _eh_novo(pedido(horas_atras=60), AGORA)


def test_depois_da_janela_deixa_de_ser_novo():
    horas = JANELA_PEDIDO_NOVO.total_seconds() / 3600 + 1
    assert not _eh_novo(pedido(horas_atras=horas), AGORA)


def test_usado_numa_coleta_deixa_de_ser_novo():
    assert not _eh_novo(pedido(horas_atras=1, usadas=12), AGORA)


def test_sem_data_de_chegada_nao_e_novo():
    assert not _eh_novo(pedido(created_at=None), AGORA)


def test_a_listagem_leva_o_selo():
    agora_de_verdade = datetime.utcnow()
    assert _to_dict(pedido(created_at=agora_de_verdade))["novo"] is True
    assert _to_dict(pedido(created_at=agora_de_verdade - timedelta(days=10)))["novo"] is False
