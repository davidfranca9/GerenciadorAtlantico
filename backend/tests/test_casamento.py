"""A nota casa com o agendamento certo - e so com ele.

Casamento errado vira CT-e errado, entao a regra e conservadora: na
duvida, nao casa e explica. Os casos aqui sao os da operacao: Fertimaxi
mandando ureia pra produtor rural em Montes Claros, dois agendamentos
parecidos no mesmo dia, cliente cadastrado pelo CNPJ.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos import casamento  # noqa: E402

NOTA = {
    "destinatario_doc": "368.314.176-04",
    "destinatario_nome": "ELTON CALDEIRA DA SILVA",
    "municipio_destino": "MONTES CLAROS",
    "peso_kg": "27000.000",
    "emissao": "2026-09-05",
}


def agendamento(id_, cliente="ELTON CALDEIRA", cidade="Montes Claros - MG", toneladas=27, data="05/09/2026", status="Agendado"):
    return {"id": id_, "status": status, "data": data, "itens": [{"cliente": cliente, "cidade": cidade, "toneladas": toneladas}]}


def test_casa_quando_so_um_encaixa():
    escolhido, motivo = casamento.escolher(NOTA, [agendamento(1), agendamento(2, cliente="OUTRO", cidade="Salvador", toneladas=10)])
    assert escolhido["id"] == 1
    assert "Montes Claros" in motivo and "27 t" in motivo


def test_cliente_cadastrado_pelo_cnpj_vale_mais_que_o_nome():
    # O nome no agendamento e o fantasia; o cadastro liga pelo documento.
    por_doc = {"36831417604": "FAZENDA BOA VISTA"}
    ag = agendamento(7, cliente="Fazenda Boa Vista")
    pontos, motivos = casamento.pontuar(NOTA, ag, por_doc)
    assert pontos >= 50
    assert any("CNPJ/CPF" in m for m in motivos)


def test_nome_parecido_conta_quando_nao_ha_cadastro():
    pontos, _ = casamento.pontuar(NOTA, agendamento(1, cliente="Elton Caldeira Silva"))
    assert pontos >= 30 + 25 + 15


def test_dois_iguais_nao_casa_e_avisa():
    escolhido, motivo = casamento.escolher(NOTA, [agendamento(1), agendamento(2)])
    assert escolhido is None
    assert "mais de um agendamento" in motivo


def test_parecido_demais_de_longe_nao_casa():
    # So a cidade bate: pouco pra ter certeza.
    escolhido, motivo = casamento.escolher(NOTA, [agendamento(1, cliente="JOSE", toneladas=5)])
    assert escolhido is None
    assert "pouco pra ter certeza" in motivo


def test_fora_da_janela_de_dias_nem_e_candidato():
    pontos, motivos = casamento.pontuar(NOTA, agendamento(1, data="01/08/2026"))
    assert pontos == 0
    assert "dias da nota" in motivos[0]


def test_data_em_qualquer_formato():
    assert casamento._data("05/09/2026") == casamento._data("2026-09-05")
    assert casamento._data("") is None


def test_cidade_ignora_uf_e_acento():
    assert casamento._cidade("Montes Claros - MG") == "MONTES CLAROS"
    assert casamento._cidade("Conceição do Jacuípe/BA") == "CONCEICAO DO JACUIPE"


def test_sem_candidatos_explica():
    escolhido, motivo = casamento.escolher(NOTA, [])
    assert escolhido is None
    assert "nenhum agendamento" in motivo
