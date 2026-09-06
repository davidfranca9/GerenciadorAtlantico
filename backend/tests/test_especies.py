"""Embalagem do pedido -> especie do CT-e.

O OCR normaliza toda embalagem pra GRANEL, BIG BAG ou SACARIA (ver
servicos/ocr.py), entao o de-para cobre exatamente esse vocabulario.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos.cte_montagem import ESPECIES_BSOFT, sugerir_especie  # noqa: E402


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


def test_catalogo_tem_todas_as_especies_da_tela():
    esperadas = [
        "GRANEL", "SACOS", "FARDOS", "BIG BAG", "PALLETS", "CAIXAS",
        "SACO DE 50 KG", "Saco de 20kg", "BIG BAG 1000 KG",
        "SACO DE 25 KG", "SC X 25 KG", "Tonelada", "SACOS 50 KG",
    ]
    assert list(ESPECIES_BSOFT.values()) == esperadas


def test_ids_confirmados_pela_api_nao_mudam():
    # Estes sete vieram da API, nao da posicao na lista.
    for especie_id, nome in {
        1: "GRANEL", 3: "SACOS", 5: "BIG BAG", 8: "SACO DE 50 KG",
        10: "BIG BAG 1000 KG", 13: "Tonelada", 14: "SACOS 50 KG",
    }.items():
        assert ESPECIES_BSOFT[especie_id] == nome
