"""Tarifa de reserva do CT-e automatico: o que ja foi cobrado no destino.

O automatico exigia a tarifa da ultima COTACAO, e nunca houve cotacao
cadastrada: ele jamais disparou, nem com nota, XML e agendamento prontos.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.apoio_documentos import banco_em_memoria, roteador_documentos  # noqa: E402

roteador_documentos()

from app.models import (Agendamento, AgendamentoItem, CarregamentoFinanceiro, CotacaoFrete,  # noqa: E402
                        NotaFiscalRecebida)
from app.routers.fiscal import sugerir_para_agendamento  # noqa: E402
from app.servicos import rascunho_automatico, tarifa_do_destino  # noqa: E402


def carga(ctes, destino="Taiobeiras MG", peso=40.0, total=9600.0, dia=15, cliente="CARLOS LUCAS MENDES", **extra):
    campos = {"cancelado": False, "complemento_de": "", **extra}
    return CarregamentoFinanceiro(
        competencia="2026-10", ctes=ctes, data_emissao=date(2026, 10, dia), destino=destino, peso=peso,
        frete_empresa_total=total, cliente=cliente, **campos,
    )


@pytest.fixture
def db():
    sessao = banco_em_memoria(CarregamentoFinanceiro, CotacaoFrete, Agendamento, AgendamentoItem, NotaFiscalRecebida)
    sessao.add(Agendamento(id=169, supplier="Fertimaxi", itens=[
        AgendamentoItem(pedido="041595", produto="UREIA", cidade="Taiobeiras-MG",
                        cliente="CARLOS LUCAS MENDES", embalagem="BIG BAG", toneladas=40),
    ]))
    sessao.commit()
    yield sessao
    sessao.close()


def sugestao(db):
    return sugerir_para_agendamento(db, db.get(Agendamento, 169))


def test_sem_cotacao_vale_o_que_foi_cobrado_no_ultimo_cte_do_destino(db):
    db.add_all([carga("5286", total=6960.0, peso=29.0, dia=9), carga("5337", total=9600.0, peso=40.0, dia=15)])
    db.commit()

    resultado = sugestao(db)

    assert resultado["tarifa"] == "240.00"
    # A origem diz de onde veio o numero: quem confere o rascunho ve antes de transmitir.
    assert "CT-e 5337" in resultado["origem_tarifa"] and "240.00" in resultado["origem_tarifa"]


def test_cotacao_registrada_vence_a_reserva(db):
    db.add_all([
        carga("5337"),
        CotacaoFrete(data_cotacao="2026-10-16", destino="Taiobeiras", valor_tonelada=260.0, cliente_nome=""),
    ])
    db.commit()

    resultado = sugestao(db)

    assert resultado["tarifa"] == "260.00" and resultado["origem_tarifa"] == "cotacao"


def test_icms_st_nao_baixa_a_tarifa(db):
    """Em carga CIF o "frete cobrado" e o valor a receber, ja sem o ICMS ST
    retido. A tarifa do CT-e e a do servico: 295 e nao 259,60."""
    db.add(carga("5250", destino="Águas Vermelhas MG", peso=32.0, total=8307.20, frete_servico_total=9440.0))
    db.add(Agendamento(id=170, supplier="Fertimaxi", itens=[
        AgendamentoItem(pedido="x", produto="y", cidade="Águas Vermelhas-MG", cliente="OUTRO", toneladas=32),
    ]))
    db.commit()

    assert sugerir_para_agendamento(db, db.get(Agendamento, 170))["tarifa"] == "295.00"


def test_complemento_nao_infla_a_tarifa(db):
    """11.700 de uma carga de 30 t inclui 600 de complemento: a tarifa e 370."""
    db.add(carga("5263/5264", destino="Pavão MG", peso=30.0, total=11700.0, complemento_total=600.0))
    db.add(Agendamento(id=171, supplier="Fertimaxi", itens=[
        AgendamentoItem(pedido="x", produto="y", cidade="Pavão-MG", cliente="OUTRO", toneladas=30),
    ]))
    db.commit()

    assert sugerir_para_agendamento(db, db.get(Agendamento, 171))["tarifa"] == "370.00"


def test_carga_cancelada_e_linha_de_complemento_nao_contam(db):
    db.add_all([
        carga("5300", total=9999.0, dia=16, cancelado=True),
        carga("5265", peso=0.0, total=400.0, dia=16, complemento_de="5263"),
        carga("5337", total=9600.0, dia=15),
    ])
    db.commit()

    assert sugestao(db)["tarifa"] == "240.00"


def test_sem_cotacao_e_sem_cte_anterior_continua_sem_tarifa(db):
    resultado = sugestao(db)

    assert resultado["tarifa"] == "" and resultado["origem_tarifa"] == ""


def test_do_mesmo_cliente_vale_mais_que_o_ultimo_do_destino(db):
    db.add_all([
        carga("5100", total=8800.0, peso=40.0, dia=2, cliente="CARLOS LUCAS MENDES"),
        carga("5337", total=9200.0, peso=40.0, dia=15, cliente="OUTRO CLIENTE"),
    ])
    db.commit()

    resultado = sugestao(db)

    assert resultado["tarifa"] == "220.00" and "CT-e 5100" in resultado["origem_tarifa"]


def test_com_tarifa_de_reserva_o_automatico_deixa_de_travar_na_tarifa(db):
    """Antes: "sem tarifa" e nunca tentava. Agora a tarifa existe e a decisao
    segue pras proximas conferencias (nota ja tem CT-e, XML, etc.)."""
    db.add(carga("5337"))
    db.commit()
    nota = SimpleNamespace(tem_cte=False, agendamento_id=169, rascunho_resultado="", xml="<xml/>")

    assert rascunho_automatico.decidir(nota, sugestao(db)) == ""

    sem_reserva = {"destino": "Taiobeiras-MG", "tarifa": ""}
    assert rascunho_automatico.decidir(nota, sem_reserva).startswith("sem tarifa")
