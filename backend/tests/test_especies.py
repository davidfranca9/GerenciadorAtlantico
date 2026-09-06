"""Mapeamento da embalagem do pedido para a especie do Bsoft.

A especie varia (big bag, saco, granel) e nao sai da NF-e: no CT-e 5053 a
nota dizia BAGS e o documento saiu BIG BAG 1000 KG. Quem manda e a
embalagem do pedido.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos.cte_montagem import sugerir_especie  # noqa: E402


@pytest.mark.parametrize(
    "embalagem, esperado",
    [
        ("GRANEL", 1),
        ("BIG BAG 1000 KG", 10),
        ("BAG 1000 KG", 10),
        ("SACO DE 50 KG", 8),
        ("Tonelada", 13),
    ],
)
def test_embalagens_conhecidas_resolvem_direto(embalagem, esperado):
    resultado = sugerir_especie(embalagem)
    assert resultado["especie_id"] == esperado
    assert resultado["confianca"] == "alta"


def test_big_bag_sem_tamanho_fica_ambiguo():
    # O cadastro tem BIG BAG e BIG BAG 1000 KG: sem o tamanho nao da pra
    # decidir sozinho.
    resultado = sugerir_especie("BIG BAG")
    assert resultado["especie_id"] == 5
    assert resultado["confianca"] == "alta"  # nome identico ao cadastro


def test_sacaria_lista_as_opcoes_parecidas():
    resultado = sugerir_especie("SACARIA")
    assert resultado["confianca"] == "ambigua"
    nomes = [a["nome"] for a in resultado["alternativas"]]
    assert "SACOS 50 KG" in nomes


def test_saco_de_50_generico_nao_escolhe_no_chute():
    # SACO DE 50 KG e SACOS 50 KG sao cadastros diferentes.
    resultado = sugerir_especie("SACOS 50")
    assert resultado["confianca"] == "ambigua"
    assert resultado["alternativas"]


def test_embalagem_vazia_nao_inventa_especie():
    resultado = sugerir_especie("")
    assert resultado["especie_id"] is None
    assert resultado["confianca"] == "nenhuma"


def test_embalagem_desconhecida_nao_inventa_especie():
    assert sugerir_especie("DESCONHECIDA")["especie_id"] is None
