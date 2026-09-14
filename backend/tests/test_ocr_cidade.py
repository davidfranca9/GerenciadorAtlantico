"""A cidade do pedido lida do PDF.

O pedido 041555 entrou sem cidade: a leitura procurava "CIDADE AGUAS
VERMELHAS" e o formato comum e com dois-pontos, "CIDADE: AGUAS VERMELHAS".
Quando nao decide, a leitura devolve as possiveis - que agora ficam
guardadas no pedido pra tela sugerir, em vez de sumirem.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos import ocr  # noqa: E402

CIDADES = [
    ("Águas Vermelhas", "MG"), ("Montes Claros", "MG"), ("Santa Maria", "RS"),
    ("Santa Maria da Vitória", "BA"), ("Conceição do Jacuípe", "BA"),
    ("Bom Jesus", "PI"), ("Bom Jesus", "RS"), ("Salvador", "BA"),
]


def candidatas(texto):
    return ocr.encontrar_cidades_candidatas(texto, CIDADES)


def test_cidade_seguida_da_uf_continua_funcionando():
    assert candidatas("CLIENTE: WAGMAR JOSE DE OLIVEIRA\nFAZENDA BOA VISTA - AGUAS VERMELHAS - MG") == [("Águas Vermelhas", "MG")]


def test_rotulo_cidade_com_dois_pontos():
    assert candidatas("CLIENTE: WAGMAR JOSÉ DE OLIVEIRA\nCIDADE: ÁGUAS VERMELHAS") == [("Águas Vermelhas", "MG")]


def test_rotulo_municipio():
    assert candidatas("CLIENTE: WAGMAR JOSÉ DE OLIVEIRA\nMUNICÍPIO: ÁGUAS VERMELHAS") == [("Águas Vermelhas", "MG")]


def test_rotulo_sem_dois_pontos_continua_funcionando():
    assert candidatas("CLIENTE: WAGMAR\nCIDADE AGUAS VERMELHAS") == [("Águas Vermelhas", "MG")]


def test_vale_o_nome_mais_longo():
    # "SANTA MARIA" tambem casa, mas o texto e "SANTA MARIA DA VITORIA".
    assert candidatas("CLIENTE: FULANO\nCIDADE: SANTA MARIA DA VITORIA") == [("Santa Maria da Vitória", "BA")]


def test_homonimo_em_dois_estados_continua_em_duvida():
    # Sem a UF no texto, nao da pra saber qual Bom Jesus: a tela pergunta.
    assert sorted(candidatas("CLIENTE: FULANO\nCIDADE: BOM JESUS")) == [("Bom Jesus", "PI"), ("Bom Jesus", "RS")]


def test_mesma_cidade_repetida_nao_vira_duvida():
    texto = "CLIENTE: FULANO\nCIDADE: MONTES CLAROS\nLOCAL DE ENTREGA CIDADE: MONTES CLAROS"
    assert candidatas(texto) == [("Montes Claros", "MG")]


def test_cidade_da_fabrica_nao_conta():
    assert candidatas("CLIENTE: FULANO\nCIDADE: CONCEICAO DO JACUIPE") == []


def test_formato_gravado_no_pedido():
    assert ocr.formatar_cidade("ÁGUAS VERMELHAS", "mg") == "Águas Vermelhas-MG"
    assert ocr.formatar_cidade("Águas Vermelhas", "MG") == "Águas Vermelhas-MG"


def test_candidatas_guardadas_em_json():
    resultado = {"cidades_candidatas": [{"cidade": "Bom Jesus", "uf": "PI"}, {"cidade": "Bom Jesus", "uf": "RS"}]}
    assert json.loads(ocr.candidatas_para_guardar(resultado)) == ["Bom Jesus-PI", "Bom Jesus-RS"]
    assert json.loads(ocr.candidatas_para_guardar({})) == []
