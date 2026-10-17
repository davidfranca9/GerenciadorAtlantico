"""Remetente com varios enderecos: vale o do ultimo CT-e criado.

A Fertimaxi tem quatro enderecos no municipio da fabrica e o documento (IBGE,
CEP) nao distingue. O rascunho automatico parava em "escolha qual o CT-e deve
usar" e a nota do William ficou sem CT-e por isso.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.apoio_documentos import banco_em_memoria, roteador_documentos  # noqa: E402

roteador_documentos()

from app.models import OperacaoFiscal  # noqa: E402
from app.servicos import cte_montagem, emissao_cte  # noqa: E402

IBGE = "2908507"


def endereco(id_, rua, cep="44245000"):
    return {"id": id_, "codIBGE": IBGE, "cidade": "CONCEICAO DO JACUIPE", "uf": "BA",
            "logradouro": rua, "numero": "SN", "bairro": "BESSA", "cep": cep}


# Quatro enderecos no mesmo municipio e no mesmo CEP, ruas diferentes: nada
# no documento escolhe entre eles.
QUATRO = [endereco(1773, "ROD A"), endereco(1774, "ROD B"), endereco(1775, "ROD C"), endereco(1776, "ROD D")]


def resolver(usado_antes=None, endereco_id=None, enderecos=QUATRO):
    return cte_montagem.resolver_parte(
        "08068476000176", IBGE,
        buscar_pessoa=lambda doc: {"id": 9, "nome": "FERTIMAXI"},
        listar_enderecos=lambda pessoa_id: enderecos,
        cep="44245000", endereco_id=endereco_id, usado_antes=usado_antes,
    )


def test_sem_desempate_continua_ambiguo():
    resultado = resolver()

    assert resultado["endereco_id"] is None
    assert "4 enderecos possiveis" in resultado["aviso"]


def test_vale_o_endereco_do_ultimo_cte_da_mesma_pessoa():
    resultado = resolver(usado_antes=lambda pessoa_id: "1775")

    assert str(resultado["endereco_id"]) == "1775" and resultado["aviso"] == ""


def test_pergunta_pela_pessoa_certa():
    perguntas = []
    resolver(usado_antes=lambda pessoa_id: perguntas.append(pessoa_id))

    assert perguntas == [9]


def test_endereco_anterior_que_nao_e_mais_candidato_nao_vale():
    """O cadastro mudou: o id do ultimo CT-e nao esta entre os candidatos."""
    resultado = resolver(usado_antes=lambda pessoa_id: "9999")

    assert resultado["endereco_id"] is None and "4 enderecos possiveis" in resultado["aviso"]


def test_escolha_feita_na_tela_vence_o_desempate():
    resultado = resolver(usado_antes=lambda pessoa_id: "1775", endereco_id="1773")

    assert str(resultado["endereco_id"]) == "1773"


def test_o_documento_decide_antes_do_historico():
    """Se o CEP resolve, o historico nem entra."""
    perto = [endereco(1, "ROD A", cep="44245000"), endereco(2, "ROD B", cep="44245111")]
    resultado = resolver(usado_antes=lambda pessoa_id: "2", enderecos=perto)

    assert str(resultado["endereco_id"]) == "1"


# --------------------------------------------------------------------------
# De onde vem o "ultimo usado"
# --------------------------------------------------------------------------


@pytest.fixture
def db():
    sessao = banco_em_memoria(OperacaoFiscal)
    yield sessao
    sessao.close()


def operacao(db, cod, remetente, end_rem, destinatario="2166", end_dest="2256", payload_cortado=False):
    corpo = (f'{{"agencias_id": "2", "remetente_id": "{remetente}", "enderecoRemetente_id": "{end_rem}", '
             f'"destinatario_id": "{destinatario}", "enderecoDestinatario_id": "{end_dest}", "valorFrete": "5400.00"')
    # O campo e cortado em 4.000 caracteres: o JSON pode terminar no meio.
    db.add(OperacaoFiscal(
        chave_nfe="x" * 44, cod_conhecimento_bsoft=cod, status="CTE_CRIADO" if cod else "CTE_REJEITADO",
        ultimo_payload=corpo if payload_cortado else corpo + "}",
    ))
    db.commit()


def test_le_o_endereco_do_ultimo_cte_criado(db):
    operacao(db, "5102", remetente="9", end_rem="1775")

    buscar = emissao_cte.enderecos_do_ultimo_cte(db)

    assert buscar("remetente", 9) == "1775"
    assert buscar("destinatario", 2166) == "2256"


def test_payload_cortado_ainda_e_lido(db):
    operacao(db, "5102", remetente="9", end_rem="1775", payload_cortado=True)

    assert emissao_cte.enderecos_do_ultimo_cte(db)("remetente", 9) == "1775"


def test_rejeicao_nao_conta_so_cte_criado(db):
    operacao(db, "5102", remetente="9", end_rem="1775")
    operacao(db, "", remetente="9", end_rem="1773")  # rejeitado: nunca criou nada

    assert emissao_cte.enderecos_do_ultimo_cte(db)("remetente", 9) == "1775"


def test_o_mais_recente_vale(db):
    operacao(db, "5102", remetente="9", end_rem="1775")
    operacao(db, "5200", remetente="9", end_rem="1776")

    assert emissao_cte.enderecos_do_ultimo_cte(db)("remetente", 9) == "1776"


def test_pessoa_sem_historico_devolve_none(db):
    operacao(db, "5102", remetente="9", end_rem="1775")

    assert emissao_cte.enderecos_do_ultimo_cte(db)("remetente", 777) is None
