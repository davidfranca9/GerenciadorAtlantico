"""Escolher o motorista traz as placas dele, e carreta vazia nao vai pro Bsoft.

O cadastro de veiculo do Bsoft guarda o motorista como texto, com o CPF
parcialmente mascarado ("042.xxx.xxx-39 - Joao"). E por esse campo que as
placas sao encontradas - sem depender dos tres conjuntos do tenant.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos import bsoft_fiscal, cte_montagem  # noqa: E402
from tests.test_payload_cte import payload  # noqa: E402

FROTA = [
    {"id": "1", "placa": "PFJ-2I64", "categoria": "CAVALO", "motorista": "827.xxx.xxx-15 - CARLOS ALBERTO MATEUS DIAS", "atualizacao": "2026-08-01 10:00:00"},
    {"id": "2", "placa": "QOH-9J46", "categoria": "CARRETA", "motorista": "827.xxx.xxx-15 - CARLOS ALBERTO MATEUS DIAS", "atualizacao": "2026-08-01 10:00:00"},
    {"id": "3", "placa": "ABC-1D23", "categoria": "2º CARRETA", "motorista": "827.xxx.xxx-15 - CARLOS ALBERTO MATEUS DIAS", "atualizacao": "2026-08-01 10:00:00"},
    {"id": "4", "placa": "OLD-0A00", "categoria": "CARRETA", "motorista": "827.xxx.xxx-15 - CARLOS ALBERTO MATEUS DIAS", "atualizacao": "2024-01-01 10:00:00"},
    {"id": "5", "placa": "TDP-9G89", "categoria": "CAVALO", "motorista": "111.xxx.xxx-22 - ELIVAN PINHEIRO ROCHA", "atualizacao": "2026-08-01 10:00:00"},
    {"id": "6", "placa": "SEM-0M00", "categoria": "CAVALO", "motorista": "", "atualizacao": ""},
]


def frota(monkeypatch):
    monkeypatch.setattr(bsoft_fiscal, "_todos_os_veiculos", lambda: FROTA)


# --------------------------------------------------------------------------
# Reconhecer o motorista no texto do veiculo
# --------------------------------------------------------------------------


def test_cpf_mascarado_bate_digito_a_digito():
    assert bsoft_fiscal._mesmo_motorista("827.xxx.xxx-15 - CARLOS", "827.808.547-15", "")
    # Um digito visivel diferente ja descarta.
    assert not bsoft_fiscal._mesmo_motorista("827.xxx.xxx-15 - CARLOS", "827.808.547-16", "")


def test_cpf_completo_diferente_nao_cai_no_nome():
    # CPF inteiro e diferente: mesmo com nome parecido, nao e a mesma pessoa.
    assert not bsoft_fiscal._mesmo_motorista("111.222.333-44 - CARLOS ALBERTO", "827.808.547-15", "CARLOS ALBERTO")


def test_nome_decide_quando_nao_ha_cpf():
    assert bsoft_fiscal._mesmo_motorista("827.xxx.xxx-15 - CARLOS ALBERTO MATEUS DIAS", "", "carlos alberto mateus dias")
    assert bsoft_fiscal._mesmo_motorista("JOÃO DA SILVA", "", "Joao da Silva")
    assert not bsoft_fiscal._mesmo_motorista("827.xxx.xxx-15 - CARLOS", "", "ELIVAN")


def test_veiculo_sem_motorista_nao_bate_com_ninguem():
    assert not bsoft_fiscal._mesmo_motorista("", "827.808.547-15", "CARLOS")


# --------------------------------------------------------------------------
# Um veiculo por slot do CT-e
# --------------------------------------------------------------------------


def test_placas_do_motorista_por_slot(monkeypatch):
    frota(monkeypatch)
    placas = bsoft_fiscal.veiculos_do_motorista(cpf="827.808.547-15")
    assert placas["placa_cavalo"] == "PFJ-2I64"
    assert placas["placa_carreta1"] == "QOH-9J46"   # a mais recente, nao a OLD
    assert placas["placa_carreta2"] == "ABC-1D23"
    assert len(placas["veiculos"]) == 4


def test_pelo_nome_quando_o_cpf_nao_esta_na_mao(monkeypatch):
    frota(monkeypatch)
    assert bsoft_fiscal.veiculos_do_motorista(nome="Elivan Pinheiro Rocha")["placa_cavalo"] == "TDP-9G89"


def test_sem_cpf_nem_nome_nao_varre_a_frota(monkeypatch):
    frota(monkeypatch)
    assert bsoft_fiscal.veiculos_do_motorista()["veiculos"] == []


def test_categoria_com_ordinal_e_acento():
    assert bsoft_fiscal._normalizar_categoria("2º CARRETA") == "2 CARRETA"
    assert bsoft_fiscal._normalizar_categoria("VEÍCULO LIVRE") == "VEICULO LIVRE"


# --------------------------------------------------------------------------
# A conferencia nao pode dizer "tudo ok" com a carreta vazia
# --------------------------------------------------------------------------


def test_carreta_vazia_vira_pendencia():
    corpo = payload()
    corpo["carreta_id"] = ""
    assert any("carreta_id" in p for p in cte_montagem.conferir_payload(corpo))


def test_com_conjunto_a_cadeia_de_veiculos_nao_e_cobrada():
    corpo = payload()
    corpo["conjuntoVeiculos_id"] = "7"
    corpo["carreta_id"] = ""
    corpo["veiculos_id"] = ""
    assert not any("carreta_id" in p or "Cavalo" in p for p in cte_montagem.conferir_payload(corpo))


# --------------------------------------------------------------------------
# Segunda fonte: o ultimo CT-e com o mesmo cavalo ou motorista
# --------------------------------------------------------------------------

CTES = [
    {"nro": "5089", "dtEmissao": "2026-09-11 21:02:00", "dados_motorista": {"motorista": "EDELSON FERREIRA BARROS", "veiculo": "KPM-4G46", "carreta": "MCY-2I23"}},
    {"nro": "5041", "dtEmissao": "2026-09-05 09:21:00", "dados_motorista": {"motorista": "ISMAEL LUCIANO NUNES ", "veiculo": "HIA-2E45", "carreta": "CUB-2C04"}},
    {"nro": "5010", "dtEmissao": "2026-08-20 10:00:00", "dados_motorista": {"motorista": "ISMAEL LUCIANO NUNES ", "veiculo": "HIA-2E45", "carreta": "VEL-0H00", "semiReboque": "SEG-0N00"}},
]


def test_ultimo_cte_do_cavalo_traz_a_carreta():
    achado = bsoft_fiscal.placas_do_ultimo_cte(placa_cavalo="hia2e45", ctes=CTES)
    assert achado["placa_carreta1"] == "CUB-2C04"      # o de 05/09, nao o de 20/08
    assert achado["fonte"].startswith("CT-e 5041")


def test_cavalo_vale_mais_que_motorista():
    # Motorista do 5089 dirigindo o cavalo do 5041: a carreta segue o cavalo.
    achado = bsoft_fiscal.placas_do_ultimo_cte(placa_cavalo="HIA-2E45", motorista_nome="EDELSON FERREIRA BARROS", ctes=CTES)
    assert achado["placa_carreta1"] == "CUB-2C04"


def test_sem_o_cavalo_no_historico_cai_no_motorista():
    achado = bsoft_fiscal.placas_do_ultimo_cte(placa_cavalo="ZZZ-0Z00", motorista_nome="Ismael Luciano Nunes", ctes=CTES)
    assert achado["placa_cavalo"] == "HIA-2E45" and achado["placa_carreta1"] == "CUB-2C04"


def test_ninguem_no_historico_devolve_vazio():
    achado = bsoft_fiscal.placas_do_ultimo_cte(placa_cavalo="PFJ-2I64", motorista_nome="CARLOS ALBERTO", ctes=CTES)
    assert achado["fonte"] == "" and achado["placa_carreta1"] == ""
