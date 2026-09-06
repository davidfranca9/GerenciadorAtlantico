"""Embalagem do pedido -> especie do CT-e.

O OCR normaliza toda embalagem pra GRANEL, BIG BAG ou SACARIA (ver
servicos/ocr.py), entao o de-para cobre exatamente esse vocabulario.
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos.cte_montagem import (  # noqa: E402
    ESPECIES_BSOFT,
    _conferir_volumes,
    sugerir_especie,
)


@pytest.mark.parametrize(
    "embalagem, especie_id, nome",
    [
        ("GRANEL", 1, "GRANEL"),
        ("BIG BAG", 10, "BIG BAG 1000 KG"),
        ("SACARIA", 8, "SACO DE 50 KG"),
    ],
)
def test_vocabulario_do_ocr_resolve_direto(embalagem, especie_id, nome):
    resultado = sugerir_especie(embalagem)
    assert resultado["especie_id"] == especie_id
    assert resultado["nome"] == nome
    assert resultado["confianca"] == "alta"


def test_aceita_o_nome_exato_de_uma_especie_do_cadastro():
    # Caso de embalagem digitada na mao, fora do vocabulario do OCR.
    assert sugerir_especie("SACOS 50 KG")["especie_id"] == 14


def test_embalagem_vazia_nao_inventa_especie():
    resultado = sugerir_especie("")
    assert resultado["especie_id"] is None
    assert resultado["confianca"] == "nenhuma"


def test_embalagem_desconhecida_nao_inventa_especie():
    # DESCONHECIDA e o que o OCR devolve quando nao identifica a embalagem.
    assert sugerir_especie("DESCONHECIDA")["especie_id"] is None


def test_todas_as_embalagens_do_ocr_tem_especie():
    from app.servicos.cte_montagem import EMBALAGEM_PARA_ESPECIE
    for especie_id in EMBALAGEM_PARA_ESPECIE.values():
        assert especie_id in ESPECIES_BSOFT


def test_volumes_fecham_com_saco_de_50():
    # 540 sacos de 50 kg = 27 toneladas.
    assert _conferir_volumes(8, "540", Decimal("27000")) == ""


def test_volumes_nao_fecham_com_big_bag_de_1000():
    # A conta torta que apareceu no CT-e 5053.
    aviso = _conferir_volumes(10, "540", Decimal("27000"))
    assert "nao fecham" in aviso
    assert "540000" in aviso


def test_granel_nao_tem_conferencia_de_volume():
    assert _conferir_volumes(1, "540", Decimal("27000")) == ""


def test_sem_quantidade_nao_reclama():
    assert _conferir_volumes(8, "", Decimal("27000")) == ""
