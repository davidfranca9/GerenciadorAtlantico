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


# Pedido 041594: a cidade do cliente quebra de linha, e no contrato da
# Fertimaxi o quadro da empresa fica ao lado do do cliente. Lido linha a
# linha, o resto do nome caia depois do endereco da fabrica e so "CAPITAO"
# era achado - Capitao-RS, quando o destino era Capitao Eneas-MG.
CIDADES_CAPITAO = CIDADES + [
    ("Capitão", "RS"), ("Capitão Enéas", "MG"), ("Capitão Poço", "PA"),
    ("Vitória", "ES"), ("Vitória da Conquista", "BA"), ("Conquista", "BA"),
]


def _contrato_fertimaxi(tmp_path, linhas_cliente):
    import fitz

    empresa = [
        "EMPRESA: FERTIMAXI INDUSTRIA, COMERCIO E SERVICOS DE FERTILIZANTES",
        "End: Br. 324, KM 537, Distrito do Bessa, CEP 44.245-000, Cidade",
        "Conceicao do Jacuipe - BA. E-mail comercial@fertimaxi.com.br,",
        "CNPJ: 08.068.476/0001-76 / INSCRICAO ESTADUAL: 69222228",
    ]
    doc = fitz.open()
    pagina = doc.new_page(width=842, height=595)
    for i, (esquerda, direita) in enumerate(zip(empresa, linhas_cliente)):
        y = 80 + i * 12
        pagina.insert_text((20, y), esquerda, fontsize=7)
        pagina.insert_text((393, y), direita, fontsize=7)
    pagina.insert_text((20, 160), "Nr. Pedido 041594", fontsize=7)
    pagina.insert_text((20, 180), "70010005: SUPER SIMPLES GR 19% P2O5 10% S 16% CA BIG BAG 24,0000 2.000,00 48.000,00", fontsize=7)
    caminho = tmp_path / "contrato.pdf"
    doc.save(str(caminho))
    doc.close()
    return str(caminho)


def test_cidade_que_quebra_de_linha_no_quadro_do_cliente(tmp_path):
    pdf = _contrato_fertimaxi(tmp_path, [
        "CLIENTE: CARLOS LUCAS MENDES",
        "End: FAZENDA SAO JOSE, ZONA RURAL, CEP 39470000, Cidade CAPITAO",
        "ENEAS - MG. E-mail , Telefones: (38) 99999-0000",
        "CNPJ/CPF: 000.000.000-00 / INSCRICAO ESTADUAL:",
    ])
    resultado = ocr.parse_pdf_fields(pdf, CIDADES_CAPITAO)
    assert resultado["cidades_candidatas"] == [{"cidade": "Capitão Enéas", "uf": "MG"}]
    assert [p["cidade"] for p in resultado["produtos"]] == ["Capitão Enéas-MG"]


def test_nome_de_duas_linhas_nao_vira_a_cidade_mais_curta(tmp_path):
    pdf = _contrato_fertimaxi(tmp_path, [
        "CLIENTE: MODULO CHAPADA INSUMOS AGROPECUARIOS LTDA",
        "End: PRACA VICTOR BRITO 15, CENTRO, CEP 45000235, Cidade VITORIA DA",
        "CONQUISTA - BA. E-mail , Telefones: (77) 34135333",
        "CNPJ/CPF: 04.807.641/0003-75 / INSCRICAO ESTADUAL: 233070537",
    ])
    assert ocr.parse_pdf_fields(pdf, CIDADES_CAPITAO)["cidades_candidatas"] == [{"cidade": "Vitória da Conquista", "uf": "BA"}]


def test_pdf_sem_quadro_do_cliente_usa_o_texto_todo(tmp_path):
    import fitz
    import pdfplumber

    doc = fitz.open()
    doc.new_page().insert_text((40, 80), "CIDADE: MONTES CLAROS", fontsize=9)
    caminho = tmp_path / "outro.pdf"
    doc.save(str(caminho))
    doc.close()
    with pdfplumber.open(str(caminho)) as pdf:
        assert ocr.texto_com_cliente_separado(pdf) == ""
    assert ocr.parse_pdf_fields(str(caminho), CIDADES)["cidades_candidatas"] == [{"cidade": "Montes Claros", "uf": "MG"}]


def test_comeco_do_nome_nao_casa_com_cidade_de_outro_estado():
    # Texto intercalado, como a leitura antiga fazia: melhor sem cidade (a
    # tela pergunta) do que Capitao-RS.
    texto = (
        "CLIENTE: CARLOS LUCAS MENDES\nEnd: Br. 324, Cidade End: FAZENDA X, Cidade CAPITAO\n"
        "Conceicao do Jacuipe - BA. E-mail comercial@fertimaxi.com.br, ENEAS - MG."
    )
    assert ocr.encontrar_cidades_candidatas(texto, CIDADES_CAPITAO) == []
    assert ocr.encontrar_cidades_candidatas("CLIENTE: FULANO\nCIDADE CAPITAO - MG", CIDADES_CAPITAO) == []
    assert ocr.encontrar_cidades_candidatas("CLIENTE: FULANO\nCIDADE CAPITAO - RS", CIDADES_CAPITAO) == [("Capitão", "RS")]


def test_cidade_dentro_do_nome_de_outra_nao_e_candidata():
    texto = "CLIENTE: FULANO\nFAZENDA X - VITORIA DA CONQUISTA - BA"
    assert ocr.encontrar_cidades_candidatas(texto, CIDADES_CAPITAO) == [("Vitória da Conquista", "BA")]
