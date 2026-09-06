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


def test_cfops_estadual_quando_mesma_uf():
    from app.routers.fiscal import escolher_cfops_id
    assert escolher_cfops_id("BA", "BA") == 1  # CFOP 5352


def test_cfops_interestadual_quando_uf_diferente():
    from app.routers.fiscal import escolher_cfops_id
    assert escolher_cfops_id("BA", "MG") == 3  # CFOP 6352


def test_cfops_cai_para_interestadual_sem_informacao():
    from app.routers.fiscal import escolher_cfops_id
    assert escolher_cfops_id("", "") == 3


NFE_EXEMPLO = b"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe29260908187322000101570010000050341342801843">
<ide><nNF>12345</nNF><serie>1</serie><tpNF>1</tpNF><dhEmi>2026-09-04T10:00:00-03:00</dhEmi></ide>
<emit><CNPJ>08187322000101</CNPJ><xNome>FERTIMAXI</xNome></emit>
<dest><CNPJ>11222333000144</CNPJ><xNome>CLIENTE TESTE</xNome>
<enderDest><xMun>Jaiba</xMun><UF>MG</UF></enderDest></dest>
<det nItem="1"><prod><xProd>FERTILIZANTE NPK</xProd><NCM>31052000</NCM><CFOP>5101</CFOP><qCom>640.0000</qCom></prod></det>
<total><ICMSTot><vProd>50000.00</vProd><vBC>50000.00</vBC><vICMS>6000.00</vICMS>
<vBCST>1000.00</vBCST><vST>180.00</vST><vNF>50000.00</vNF></ICMSTot></total>
<transp><vol><qVol>640</qVol><pesoB>32000.000</pesoB></vol></transp>
</infNFe></NFe></nfeProc>"""


def test_extrai_dados_da_nfe():
    dados = nfe_xml.extrair_dados(NFE_EXEMPLO)
    assert dados["chave"] == CHAVE_VALIDA
    assert dados["emitente_nome"] == "FERTIMAXI"
    assert dados["uf_destino"] == "MG"
    assert dados["peso_bruto"] == "32000.000"


def test_mercadoria_transcreve_valores_fiscais_sem_calcular():
    m = nfe_xml.extrair_mercadoria(NFE_EXEMPLO)
    assert m["vBC"] == "50000.00"
    assert m["vICMS"] == "6000.00"
    assert m["vBCST"] == "1000.00"
    assert m["vST"] == "180.00"
    assert m["nCFOP"] == "5101"
    assert m["NCM"] == "31052000"


def test_mercadoria_traz_identificacao_da_nota():
    m = nfe_xml.extrair_mercadoria(NFE_EXEMPLO)
    assert m["notaFiscal"] == "12345"
    assert m["serieNotaFiscal"] == "1"
    assert m["tipoNF"] == "S"
    assert m["chaveNFe"] == CHAVE_VALIDA


def test_mercadoria_usa_peso_e_volume_do_transporte():
    m = nfe_xml.extrair_mercadoria(NFE_EXEMPLO)
    assert m["quantKg"] == "32000.000"
    assert m["quant"] == "640"
