"""Payload do POST /transporte/v1/conhecimentos.

Os nomes de campo vem da colecao oficial (request "Conhecimentos /
Inserir"). Os valores sao conferidos contra o CT-e 5053.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos.cte_montagem import (  # noqa: E402
    conferir_payload,
    derivar,
    montar_payload_conhecimento,
)
from tests.test_cte_5053 import NFE_158852, TARIFA_5053  # noqa: E402

PARTES_OK = {
    "remetente": {"pessoa_id": "101", "endereco_id": "9001"},
    "destinatario": {"pessoa_id": "202", "endereco_id": "9002"},
}
VEICULOS_OK = {"motorista_id": "652", "veiculo_id": "28", "carreta_id": "29"}


def payload(**kwargs):
    espelho = derivar(NFE_158852, tarifa_por_tonelada=TARIFA_5053, embalagem="BIG BAG")
    base = dict(partes=PARTES_OK, veiculos=VEICULOS_OK, aliquota_icms="12")
    base.update(kwargs)
    return montar_payload_conhecimento(espelho, **base)


def test_sai_como_rascunho_por_padrao():
    # Nenhuma emissao real sem alguem pedir explicitamente.
    assert payload()["rascunho"] == "S"
    assert payload(rascunho=False)["rascunho"] == "N"


def test_valores_batem_com_o_dacte_5053():
    corpo = payload()
    assert corpo["valorFrete"] == "8100.00"
    assert corpo["baseCalculo"] == "8100.00"
    assert corpo["totalPrestacao"] == "8100.00"
    assert corpo["tarifaDigitada"] == "300.00"  # valor por tonelada, nao o total


def test_icms_multiplica_a_base_pela_aliquota_informada():
    # DACTE 5053: base 8.100,00, aliquota 12%, ICMS 972,00.
    corpo = payload()
    assert corpo["aliquota"] == "12"
    assert corpo["valorICMS"] == "972.00"


def test_sem_aliquota_nao_inventa_icms():
    corpo = payload(aliquota_icms=None)
    assert corpo["valorICMS"] == ""
    assert "Aliquota de ICMS nao informada." in conferir_payload(corpo)


def test_cst_do_cte_e_proprio_e_nao_copia_o_da_nota():
    # A NF-e 158852 tem CST 20; o CT-e 5053 saiu 00.
    corpo = payload()
    assert corpo["CST"] == "000"
    assert corpo["definirCSTManualmente"] == "S"


def test_percurso_vem_da_nota():
    corpo = payload()
    assert corpo["cMunIni"] == "2908507"
    assert corpo["cMunFim"] == "3143302"
    assert corpo["UFIni"] == "BA"
    assert corpo["UFFim"] == "MG"


def test_partes_entram_pelos_ids_resolvidos():
    corpo = payload()
    assert corpo["remetente_id"] == "101"
    assert corpo["enderecoRemetente_id"] == "9001"
    assert corpo["destinatario_id"] == "202"
    assert corpo["enderecoDestinatario_id"] == "9002"


def test_veiculo_e_motorista_entram_quando_existem():
    corpo = payload()
    assert corpo["motorista_id"] == "652"
    assert corpo["veiculos_id"] == "28"
    assert corpo["carreta_id"] == "29"


def test_veiculo_ausente_nao_vira_campo_vazio():
    # Mandar id em branco e pior que nao mandar o campo.
    corpo = payload(veiculos={})
    assert "veiculos_id" not in corpo
    assert "motorista_id" not in corpo


def test_constantes_da_tela_de_emissao():
    corpo = payload()
    assert corpo["tipoDocumentos"] == "N"   # NF-e
    assert corpo["respSeg"] == "4"          # emitente
    assert corpo["modalidade"] == "R"       # rodoviario
    assert corpo["cteOS"] == "N"


def test_ids_do_tenant_entram_no_payload():
    corpo = payload()
    assert corpo["agencias_id"] == "2"
    assert corpo["tiposTaloes_id"] == "3"
    assert corpo["regraFrete_id"] == "35"
    assert corpo["numeroApolice"] == "202511"


def test_mercadoria_transcreve_a_nota():
    linha = payload()["mercadorias"][0]
    assert linha["chaveNFe"] == "29260908068476000176550010001588521343374682"
    assert linha["notaFiscal"] == "158852"
    assert linha["serieNotaFiscal"] == "1"
    assert linha["nCFOP"] == "6101"      # o CFOP da nota, nao o do CT-e
    assert linha["vBC"] == "22950.00"
    assert linha["vICMS"] == "2754.00"


def test_peso_da_mercadoria_vai_em_quilos():
    # O campo do Bsoft se chama quantKg: 27 toneladas viram 27000.
    linha = payload()["mercadorias"][0]
    assert linha["quantKg"] == "27000.000"
    assert linha["quant"] == "540"


def test_especie_e_natureza_da_carga_na_mercadoria():
    linha = payload()["mercadorias"][0]
    assert linha["especie"] == "10"        # BIG BAG 1000 KG
    assert linha["naturezaCarga"] == "4"   # FERTILIZANTES


def test_payload_completo_nao_tem_pendencia():
    assert conferir_payload(payload()) == []


def test_parte_nao_resolvida_vira_pendencia():
    corpo = payload(partes={"remetente": {}, "destinatario": {}})
    pendencias = conferir_payload(corpo)
    assert any("Remetente" in p for p in pendencias)
    assert any("Endereco do destinatario" in p for p in pendencias)


def test_sem_embalagem_a_especie_falta_no_payload():
    espelho = derivar(NFE_158852, tarifa_por_tonelada=TARIFA_5053)
    corpo = montar_payload_conhecimento(
        espelho, partes=PARTES_OK, veiculos=VEICULOS_OK, aliquota_icms="12"
    )
    assert any("Especie" in p for p in conferir_payload(corpo))
