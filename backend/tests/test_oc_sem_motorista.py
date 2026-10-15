"""A Ordem de Coleta sem motorista mostra o cliente.

A fabrica agenda antes de sabermos quem dirige, e a O.C. saia com a linha
"Motorista:" em branco - sem dizer de quem era a carga.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PRODUTOS = [
    {"contrato": "042666", "produto": "MAP 11-52-00", "embalagem": "SACARIA", "toneladas": "15",
     "cidade": "Jaíba-MG", "cliente": "AGRODANTAS PRODUTOS AGRICOLAS LTDA"},
    {"contrato": "043008", "produto": "UREIA", "embalagem": "BIG BAG", "toneladas": "7",
     "cidade": "Janaúba-MG", "cliente": "CASA DO PRODUTOR RURAL DE JAIBA"},
]


@pytest.fixture
def oc_html(monkeypatch):
    """Importa o modulo de verdade, com o WeasyPrint simulado.

    Duas coisas atrapalham: o WeasyPrint nao carrega neste Windows (falta
    biblioteca nativa) e outros testes trocam `app.servicos.oc_html` por um
    dublê sem funcao nenhuma. Entao aqui o dublê sai de cena, o weasyprint
    entra simulado e o modulo e importado do arquivo - o monkeypatch devolve
    tudo ao normal no fim.
    """
    import importlib
    import types

    gerado = {}

    class HTMLFalso:
        def __init__(self, string="", base_url=""):
            gerado["conteudo"] = string

        def write_pdf(self, caminho):
            pass

    falso = types.ModuleType("weasyprint")
    falso.HTML = HTMLFalso
    monkeypatch.setitem(sys.modules, "weasyprint", falso)
    monkeypatch.delitem(sys.modules, "app.servicos.oc_html", raising=False)

    modulo = importlib.import_module("app.servicos.oc_html")
    monkeypatch.setattr(modulo, "HTML", HTMLFalso)
    modulo._conteudo = gerado
    return modulo


def montar(oc_html, nome="", cpf="", produtos=None) -> str:
    oc_html.gerar_oc_pdf_html(
        "AFL", produtos if produtos is not None else PRODUTOS, cpf, nome, "", "", "", "", "",
        "20/10/2026", "saida.pdf",
    )
    return oc_html._conteudo["conteudo"]


def test_sem_motorista_a_ordem_mostra_o_cliente(oc_html):
    conteudo = montar(oc_html, nome="")

    assert "Motorista a definir" in conteudo
    assert "Cliente:</span> AGRODANTAS PRODUTOS AGRICOLAS LTDA / CASA DO PRODUTOR RURAL DE JAIBA" in conteudo


def test_com_motorista_a_ordem_continua_como_era(oc_html):
    conteudo = montar(oc_html, nome="TALISSON JUNIOR GUIMARAES RIBEIRO", cpf="121.597.816-22")

    assert "Dados do Motorista" in conteudo
    assert "TALISSON JUNIOR GUIMARAES RIBEIRO" in conteudo
    assert "Motorista a definir" not in conteudo


def test_cliente_repetido_aparece_uma_vez_so(oc_html):
    iguais = [dict(PRODUTOS[0]), dict(PRODUTOS[0], produto="KCL")]
    conteudo = montar(oc_html, nome="", produtos=iguais)

    assert conteudo.count("Cliente:</span> AGRODANTAS PRODUTOS AGRICOLAS LTDA<") == 1
