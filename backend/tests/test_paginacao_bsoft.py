"""A paginacao do Bsoft e `limit=offset,quantidade`; `inicio` nao existe.

Mandar `inicio` fazia toda pagina voltar sendo a primeira: o sistema so
enxergava os 100 primeiros veiculos e pessoas, e a tela mostrava 25 copias
do mesmo cadastro. Estes testes travam o formato e a parada em pagina
repetida.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos import bsoft_fiscal  # noqa: E402


def cadastro(total):
    return [{"id": str(i), "placa": f"P{i:03d}"} for i in range(total)]


def api_que_pagina(total):
    """Simula a API honrando limit=offset,quantidade."""
    chamadas = []
    def chamar(metodo, caminho, params=None):
        offset, quantidade = (int(x) for x in params["limit"].split(","))
        chamadas.append(offset)
        return 200, cadastro(total)[offset:offset + quantidade]
    return chamar, chamadas


def api_que_ignora_offset(total):
    """Simula o que acontecia: toda pagina e a primeira."""
    def chamar(metodo, caminho, params=None):
        assert "limit" in params, "a paginacao documentada e limit=offset,quantidade"
        return 200, cadastro(total)[:100]
    return chamar


def test_manda_limit_no_formato_documentado(monkeypatch):
    chamar, chamadas = api_que_pagina(250)
    monkeypatch.setattr(bsoft_fiscal, "chamar", chamar)
    todos = bsoft_fiscal._paginar("/transporte/v1/veiculos")
    assert len(todos) == 250
    assert sorted(chamadas)[:3] == [0, 100, 200]


def test_para_quando_a_api_nao_anda(monkeypatch):
    # Se a API devolve sempre a mesma pagina, o resultado tem cada registro
    # UMA vez e a varredura nao vai ate as 50 paginas.
    monkeypatch.setattr(bsoft_fiscal, "chamar", api_que_ignora_offset(100))
    todos = bsoft_fiscal._paginar("/transporte/v1/veiculos")
    assert len(todos) == 100
    assert len({v["id"] for v in todos}) == 100


def test_cadastro_pequeno_vem_inteiro_sem_duplicar(monkeypatch):
    chamar, _ = api_que_pagina(37)
    monkeypatch.setattr(bsoft_fiscal, "chamar", chamar)
    assert [v["id"] for v in bsoft_fiscal._paginar("/x")] == [str(i) for i in range(37)]


def test_busca_por_placa_usa_o_filtro_do_servidor(monkeypatch):
    # Com o filtro `placa` respondendo, a varredura completa nem acontece.
    def listar(caminho, params=None):
        assert "placa" in params
        return [{"id": "1644", "placa": "PFJ-2I64"}] if params["placa"] in ("PFJ-2I64", "PFJ2I64") else []
    monkeypatch.setattr(bsoft_fiscal, "listar", listar)
    monkeypatch.setattr(bsoft_fiscal, "_todos_os_veiculos", lambda: (_ for _ in ()).throw(AssertionError("varreu")))
    assert bsoft_fiscal.buscar_veiculo_por_placa("pfj2i64")["id"] == "1644"


def test_busca_por_placa_cai_na_varredura_se_o_filtro_nao_acha(monkeypatch):
    monkeypatch.setattr(bsoft_fiscal, "listar", lambda caminho, params=None: [])
    monkeypatch.setattr(bsoft_fiscal, "_todos_os_veiculos", lambda: [{"id": "9", "placa": "ABC1D23"}])
    assert bsoft_fiscal.buscar_veiculo_por_placa("ABC-1D23")["id"] == "9"
