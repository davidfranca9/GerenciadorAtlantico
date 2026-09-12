"""Pessoa != motorista != dono do caminhao; e o conjunto dispensa a cadeia.

No Bsoft uma pessoa e UM cadastro em varios grupos (motoristas,
proprietariosVeiculos, favorecidos...). O campo motorista_id do CT-e so
aceita quem esta no grupo de motoristas. E sem conjunto de veiculos a API
cobra os quatro veiculos, um erro por vez - o que o print do usuario
mostrou: carreta, depois semireboque.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos import bsoft_fiscal, cte_montagem  # noqa: E402
from tests.test_payload_cte import payload  # noqa: E402

TALISSON = {"id": "3010", "nome": "TALISSON JUNIOR", "sobrenome": "GUIMARAES RIBEIRO", "cpf": "12159781622"}


# --------------------------------------------------------------------------
# A lupa procura no grupo de motoristas, e avisa quando so acha fora dele
# --------------------------------------------------------------------------


def test_lupa_manda_o_filtro_de_grupo(monkeypatch):
    consultas = []
    def listar(caminho, params=None):
        consultas.append(params)
        return [TALISSON] if params.get("grupo") == "motoristas" else []
    monkeypatch.setattr(bsoft_fiscal, "listar", listar)
    resposta = bsoft_fiscal.procurar_motoristas("juni")
    assert consultas[0] == {"descricao": "juni", "grupo": "motoristas"}
    assert resposta["aviso"] == ""
    assert resposta["resultados"][0]["id"] == "3010"
    assert "fora_do_grupo" not in resposta["resultados"][0]


def test_lupa_avisa_quando_a_pessoa_existe_mas_nao_e_motorista(monkeypatch):
    def listar(caminho, params=None):
        # Existe como pessoa, nao no grupo de motoristas.
        return [] if params.get("grupo") else [TALISSON]
    monkeypatch.setattr(bsoft_fiscal, "listar", listar)
    resposta = bsoft_fiscal.procurar_motoristas("juni")
    assert resposta["resultados"][0]["fora_do_grupo"] is True
    assert "nao no grupo de motoristas" in resposta["aviso"]
    assert "TALISSON" in resposta["aviso"]


def test_lupa_diz_quando_nao_ha_ninguem(monkeypatch):
    monkeypatch.setattr(bsoft_fiscal, "listar", lambda caminho, params=None: [])
    monkeypatch.setattr(bsoft_fiscal, "_todas_as_pessoas_fisicas", lambda: [])
    assert "Ninguem" in bsoft_fiscal.procurar_motoristas("zzz")["aviso"]


# --------------------------------------------------------------------------
# Conjunto pelo CPF do motorista
# --------------------------------------------------------------------------


def test_conjunto_por_cpf_usa_o_filtro_documentado(monkeypatch):
    consultas = []
    def listar(caminho, params=None):
        consultas.append((caminho, params))
        return [{"id": "17", "motorista": "TALISSON JUNIOR ", "veiculo": "ABC-1D23", "carreta": "DEF-4E56"}]
    monkeypatch.setattr(bsoft_fiscal, "listar", listar)
    conjunto = bsoft_fiscal.buscar_conjunto_por_cpf("121.597.816-22")
    assert consultas == [("/transporte/v1/conjuntoVeiculos", {"cpf": "12159781622"})]
    assert conjunto["id"] == "17"
    assert conjunto["placas"] == ["ABC-1D23", "DEF-4E56"]
    assert conjunto["descricao"] == "TALISSON JUNIOR · ABC-1D23 · DEF-4E56"


def test_sem_conjunto_devolve_none(monkeypatch):
    monkeypatch.setattr(bsoft_fiscal, "listar", lambda caminho, params=None: [])
    assert bsoft_fiscal.buscar_conjunto_por_cpf("12159781622") is None
    assert bsoft_fiscal.buscar_conjunto_por_cpf("123") is None


def test_criar_conjunto_manda_placas_e_nao_apaga_vinculos(monkeypatch):
    enviado = {}
    def chamar(metodo, caminho, json_body=None, **kw):
        enviado.update({"metodo": metodo, "caminho": caminho, "corpo": json_body})
        return 200, {"codConjunto": "18"}
    monkeypatch.setattr(bsoft_fiscal, "chamar", chamar)
    bsoft_fiscal.criar_conjunto_veiculos("3010", {"placa_cavalo": "ABC-1D23", "placa_carreta1": "DEF-4E56", "placa_carreta2": "", "placa_quarto": ""})
    assert enviado["metodo"] == "POST" and enviado["caminho"] == "/transporte/v1/conjuntoVeiculos"
    assert enviado["corpo"] == {"motoristaId": "3010", "removerVinculacoes": "N", "veiculo": "ABC-1D23", "carreta": "DEF-4E56"}


def test_criar_conjunto_exige_o_cavalo():
    import pytest
    with pytest.raises(ValueError):
        bsoft_fiscal.criar_conjunto_veiculos("3010", {"placa_carreta1": "DEF-4E56"})


# --------------------------------------------------------------------------
# Sem conjunto, a conferencia cobra os quatro de uma vez
# --------------------------------------------------------------------------


def test_sem_conjunto_os_quatro_veiculos_aparecem_juntos():
    corpo = payload()
    corpo["carreta_id"] = corpo["semireboque_id"] = corpo["quartoVeiculo_id"] = ""
    faltas = cte_montagem.conferir_payload(corpo)
    assert sum(1 for f in faltas if "Carreta" in f or "Semi-reboque" in f or "Quarto veiculo" in f) == 3


def test_com_conjunto_nenhum_veiculo_e_cobrado():
    corpo = payload()
    corpo["conjuntoVeiculos_id"] = "17"
    for campo in ("motorista_id", "veiculos_id", "carreta_id", "semireboque_id", "quartoVeiculo_id"):
        corpo[campo] = ""
    faltas = cte_montagem.conferir_payload(corpo)
    assert not any(palavra in f for f in faltas for palavra in ("Motorista", "Cavalo", "Carreta", "Semi-reboque", "Quarto"))
