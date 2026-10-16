"""Cliente do contrato quando o nome da empresa transborda sobre o quadro dele.

No contrato da Fertimaxi o texto "...FERTILIZANTES LT" passa por baixo do
quadro do cliente. Ordenados pela posicao, os caracteres dos dois textos se
embaralham ("FERTILIZANTECSL ILETNTE:") e a palavra CLIENTE: nunca aparece
inteira: o pedido 043567 e o 043579 chegaram sem cliente.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.apoio_documentos import roteador_documentos  # noqa: E402

roteador_documentos()

from app.servicos import ocr  # noqa: E402


def caracteres(texto: str, topo: float, x0: float, largura: float = 6.0) -> list[dict]:
    """Um texto desenhado de uma vez: cada letra logo depois da anterior."""
    return [
        {"text": letra, "top": topo, "x0": x0 + i * largura, "x1": x0 + (i + 1) * largura}
        for i, letra in enumerate(texto)
    ]


def pagina(*textos: tuple[str, float, float]):
    """Pagina cujos caracteres seguem a ordem em que o PDF desenha."""
    chars: list[dict] = []
    for texto, topo, x0 in textos:
        chars += caracteres(texto, topo, x0)
    return SimpleNamespace(chars=chars)


def contrato(*paginas):
    return SimpleNamespace(pages=list(paginas))


# A empresa termina em x=420 e o rotulo do cliente comeca em x=380: os dois
# ocupam o mesmo trecho da mesma linha, que e o que embaralha a leitura.
EMPRESA = ("EMPRESA: FERTIMAXI INDUSTRIA, COMERCIO E SERVICOS DE FERTILIZANTES LT", 100.0, 20.0)
CLIENTE = ("CLIENTE: JACSON COSTA VEIGA", 100.0, 380.0)


def test_cliente_e_lido_inteiro_mesmo_com_a_empresa_por_cima():
    cliente = ocr.cliente_do_contrato(contrato(pagina(EMPRESA, CLIENTE)))

    assert cliente == "JACSON COSTA VEIGA"


def test_o_texto_ordenado_pela_posicao_realmente_embaralharia():
    """Garante que o cenario do teste e o do problema: se as letras nao se
    misturassem, o teste acima passaria sem provar nada."""
    letras = sorted(pagina(EMPRESA, CLIENTE).chars, key=lambda c: (c["top"], c["x0"]))
    linha = "".join(c["text"] for c in letras)

    assert "CLIENTE:" not in linha.replace(" ", "")


def test_pdf_com_pagina_em_branco_na_frente():
    """O 043567 veio com a primeira pagina vazia e o contrato na segunda."""
    vazia = SimpleNamespace(chars=[])

    assert ocr.cliente_do_contrato(contrato(vazia, pagina(EMPRESA, CLIENTE))) == "JACSON COSTA VEIGA"


def test_nome_com_e_outros_vem_inteiro():
    cliente = ocr.cliente_do_contrato(contrato(pagina(
        EMPRESA, ("CLIENTE: PAULO MANOEL OLIVEIRA NETO E OUTROS", 100.0, 380.0),
    )))

    assert cliente == "PAULO MANOEL OLIVEIRA NETO E OUTROS"


def test_endereco_logo_abaixo_nao_entra_no_nome():
    cliente = ocr.cliente_do_contrato(contrato(pagina(
        EMPRESA, CLIENTE, ("End: FAZENDA SHANGRILA SN, ZONA RURAL, CEP 45260000", 112.0, 380.0),
    )))

    assert cliente == "JACSON COSTA VEIGA"


def test_pdf_sem_o_rotulo_devolve_none_e_nao_quebra():
    assert ocr.cliente_do_contrato(contrato(pagina(("CONTRATO DE COMPRA E VENDA", 20.0, 20.0)))) is None
    assert ocr.cliente_do_contrato(contrato(SimpleNamespace(chars=[]))) is None
