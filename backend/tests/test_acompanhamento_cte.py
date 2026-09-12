"""O que o resumo do Bsoft diz sobre o CT-e, traduzido pra operacao.

Os dois registros abaixo sao reais: o rascunho 5072 e o CT-e 5053
(autorizado, chave ...9151), lidos pelo GET /conhecimentos/{id}.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos.acompanhamento_cte import interpretar_resumo  # noqa: E402

RASCUNHO_5072 = {"id": "5072", "nro": "Rascunho", "tipoTalao": "CT-e", "dtEmissao": "2026-09-08 02:34:00"}
AUTORIZADO_5053 = {
    "id": "5053", "nro": "5041", "chaveAcesso": "29260908187322000101570010000050411572889151",
    "protocoloAverbacao": "7AOE7C528G58CQ1T1851M5437JVXS", "statusAverbacao": "S",
}


def test_rascunho_continua_rascunho():
    lido = interpretar_resumo(RASCUNHO_5072)
    assert lido["situacao"] == "rascunho"
    assert lido["numero"] == "" and lido["chave"] == ""


def test_autorizado_traz_numero_chave_e_protocolo():
    lido = interpretar_resumo(AUTORIZADO_5053)
    assert lido["situacao"] == "autorizado"
    assert lido["numero"] == "5041"
    assert lido["chave"].endswith("9151") and len(lido["chave"]) == 44
    assert lido["protocolo"].startswith("7AOE")
    assert lido["averbado"] is True


def test_numerado_sem_chave_fica_em_aberto():
    # E o unico sinal que o resumo da de que algo nao andou: numero sem chave.
    lido = interpretar_resumo({"id": "5200", "nro": "5188"})
    assert lido["situacao"] == "em_aberto"


def test_registro_vazio_e_desconhecido():
    assert interpretar_resumo({})["situacao"] == "desconhecido"
