"""Testes da leitura de NF-e e da montagem do payload de CT-e.

Nenhum teste toca a API do Bsoft nem o banco - tudo puro.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.fiscal import montar_payload_cte  # noqa: E402
from app.servicos import nfe_xml  # noqa: E402

# Chave real de CT-e da operacao (serve pra validar o calculo do DV).
CHAVE_VALIDA = "29260908187322000101570010000050341342801843"


def test_chave_valida_aceita_chave_real():
    assert nfe_xml.chave_valida(CHAVE_VALIDA)


def test_chave_valida_rejeita_digito_trocado():
    trocada = CHAVE_VALIDA[:43] + ("0" if CHAVE_VALIDA[43] != "0" else "1")
    assert not nfe_xml.chave_valida(trocada)


def test_chave_valida_rejeita_tamanho_errado():
    assert not nfe_xml.chave_valida("123")
    assert not nfe_xml.chave_valida("")


def test_chave_valida_ignora_formatacao():
    assert nfe_xml.chave_valida(" ".join(CHAVE_VALIDA[i:i + 4] for i in range(0, 44, 4)))


def test_xml_invalido_levanta_erro():
    with pytest.raises(nfe_xml.NFeInvalida):
        nfe_xml.extrair_dados(b"isso nao e xml")


def test_xml_sem_infnfe_levanta_erro():
    with pytest.raises(nfe_xml.NFeInvalida):
        nfe_xml.extrair_dados(b"<?xml version='1.0'?><qualquer/>")


def test_payload_usa_chave_e_omite_ids():
    corpo = montar_payload_cte(
        chave_nfe=CHAVE_VALIDA, parametro_criacao_cte="16", valor_frete=5550, cod_nfe="4975"
    )
    assert corpo["chavesNFe"] == [CHAVE_VALIDA]
    assert "ids" not in corpo  # quando ha chave, o Bsoft ignora ids
    assert corpo["parametroCriacaoCTe"] == "16"


def test_payload_cai_para_id_quando_nao_ha_chave():
    corpo = montar_payload_cte(chave_nfe="", parametro_criacao_cte="16", valor_frete=100, cod_nfe="4975")
    assert corpo["ids"] == ["4975"]
    assert "chavesNFe" not in corpo


def test_payload_formata_valores_com_duas_casas():
    corpo = montar_payload_cte(chave_nfe=CHAVE_VALIDA, parametro_criacao_cte="16", valor_frete=5550)
    assert corpo["valorFrete"] == "5550.00"
    assert corpo["totalPrestacao"] == "5550.00"
    assert corpo["baseCalculo"] == "5550.00"


def test_payload_zera_campos_opcionais_em_vez_de_omitir():
    corpo = montar_payload_cte(chave_nfe=CHAVE_VALIDA, parametro_criacao_cte="16", valor_frete=1)
    for campo in ("gris", "valorSeguro", "diaria", "valorPedagioConhecimento"):
        assert corpo[campo] == "0.00"
