"""Dividas ativas: lancar o que foi pago, com valor e data.

O contador de parcelas nao dizia quanto saiu nem quando ("mandei 3000 pro
Rodrigo"). Aqui cada pagamento fica guardado, aparece no historico da divida e
pode ser desfeito - levando a saida do Caixa junto, quando houve uma.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import get_current_user  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models import ContaBancaria, Divida, DividaPagamento, LancamentoCaixa  # noqa: E402
from app.routers import financeiro as rotas  # noqa: E402
from app.servicos import financeiro as fin  # noqa: E402
from tests.apoio_documentos import banco_em_memoria  # noqa: E402

TABELAS = (ContaBancaria, LancamentoCaixa, Divida, DividaPagamento)


@pytest.fixture
def db():
    sessao = banco_em_memoria(*TABELAS)
    yield sessao
    sessao.close()


def cliente_http(db):
    app = FastAPI()
    app.include_router(rotas.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(email="dono@atlantico", role="admin")
    return TestClient(app)


def conta(db, nome="Nubank", saldo=10000.0):
    c = ContaBancaria(nome=nome, instituicao=nome, cor="#000", saldo_inicial=saldo, saldo_inicial_em=date(2026, 9, 1))
    db.add(c)
    db.commit()
    return c


def divida(http, **campos):
    """Rodrigo: 9000 em 3 parcelas de 3000, a proxima no fim de setembro."""
    corpo = {"credor": "Rodrigo", "valor_total": 9000, "parcelas_total": 3, "valor_parcela": 3000,
             "proximo_pagamento": "2026-09-30"}
    corpo.update(campos)
    return http.post("/financeiro/dividas", json=corpo).json()


def pagar(http, divida_id, **campos):
    return http.post(f"/financeiro/dividas/{divida_id}/pagamentos", json=campos)


def test_lancar_pagamento_guarda_valor_data_e_anda_a_parcela(db):
    http = cliente_http(db)
    rodrigo = divida(http)
    assert (rodrigo["restante"], rodrigo["pago"], rodrigo["pagamentos"]) == (9000, 0, [])

    depois = pagar(http, rodrigo["id"], valor=3000, pago_em="2026-09-12", observacao="PIX do celular").json()
    assert depois["pago"] == 3000 and depois["restante"] == 6000
    assert depois["parcelas_pagas"] == 1 and depois["proximo_pagamento"] == "2026-10-30"
    lancado = depois["pagamentos"][0]
    assert (lancado["valor"], lancado["pago_em"], lancado["observacao"]) == (3000, "2026-09-12", "PIX do celular")
    # Sem conta escolhida, nada entra no Caixa: foi acerto fora do banco.
    assert lancado["no_caixa"] is False and lancado["conta"] == ""
    assert db.query(LancamentoCaixa).count() == 0


def test_historico_abre_pelo_pagamento_mais_recente(db):
    http = cliente_http(db)
    hugo = divida(http, credor="Hugo", valor_total=None, parcelas_total=None, valor_parcela=None,
                  proximo_pagamento=None, observacao="A organizar")
    for valor, dia in ((1000, "2026-08-05"), (2500, "2026-09-20"), (700, "2026-07-10")):
        assert pagar(http, hugo["id"], valor=valor, pago_em=dia).status_code == 200

    atual = http.get("/financeiro/dividas").json()[0]
    assert [p["pago_em"] for p in atual["pagamentos"]] == ["2026-09-20", "2026-08-05", "2026-07-10"]
    assert [p["valor"] for p in atual["pagamentos"]] == [2500, 1000, 700]
    # Sem valor total nao da pra dizer quanto falta, mas quanto saiu da.
    assert atual["pago"] == 4200 and atual["restante"] is None


def test_pagamento_com_conta_sai_no_caixa_e_desfazer_leva_o_lancamento(db):
    nu = conta(db)
    http = cliente_http(db)
    rodrigo = divida(http)
    depois = pagar(http, rodrigo["id"], valor=3000, pago_em="2026-09-12", conta_id=nu.id, forma="pix").json()
    lancado = depois["pagamentos"][0]
    assert lancado["no_caixa"] is True and lancado["conta"] == "Nubank"

    saida = db.query(LancamentoCaixa).one()
    assert (saida.tipo, float(saida.valor), saida.forma, saida.origem) == ("saida", 3000.0, "PIX", "divida")
    assert saida.descricao == "Dívida · Rodrigo"
    assert fin.conta_para_dict(db, nu, hoje=date(2026, 9, 30))["saldo_atual"] == 7000

    voltou = http.delete(f"/financeiro/dividas/pagamentos/{lancado['id']}").json()
    assert voltou["pagamentos"] == [] and voltou["pago"] == 0 and voltou["restante"] == 9000
    assert voltou["parcelas_pagas"] == 0 and voltou["proximo_pagamento"] == "2026-09-30"
    assert db.query(LancamentoCaixa).count() == 0
    assert fin.conta_para_dict(db, nu, hoje=date(2026, 9, 30))["saldo_atual"] == 10000


def test_desfazer_a_ultima_parcela_reabre_a_divida(db):
    http = cliente_http(db)
    unica = divida(http, valor_total=3000, parcelas_total=1, valor_parcela=3000)
    quitada = pagar(http, unica["id"], valor=3000, pago_em="2026-09-28").json()
    assert quitada["quitada"] is True and quitada["restante"] == 0 and quitada["proximo_pagamento"] is None
    assert pagar(http, unica["id"], valor=10, pago_em="2026-09-29").status_code == 400

    reaberta = http.delete(f"/financeiro/dividas/pagamentos/{quitada['pagamentos'][0]['id']}").json()
    assert reaberta["quitada"] is False and reaberta["restante"] == 3000 and reaberta["pago"] == 0
    # Quitar apagou a data; volta pro dia em que o dinheiro tinha saido.
    assert reaberta["proximo_pagamento"] == "2026-09-28"


def test_parcela_pelo_botao_e_pagamento_lancado_nao_se_repetem(db):
    http = cliente_http(db)
    rodrigo = divida(http)
    assert http.post(f"/financeiro/dividas/{rodrigo['id']}/parcela-paga").status_code == 200
    pelo_botao = http.get("/financeiro/dividas").json()[0]
    # Parcela sem historico vale o valor da parcela - e tudo que se sabe dela.
    assert pelo_botao["pago"] == 3000 and pelo_botao["restante"] == 6000 and pelo_botao["pagamentos"] == []

    # Na segunda parcela saiu menos: entra pelo que foi pago mesmo, e a
    # parcela nao conta como fechada - faltam 500 dela.
    depois = pagar(http, rodrigo["id"], valor=2500, pago_em="2026-10-28").json()
    assert depois["parcelas_pagas"] == 1 and depois["pago"] == 5500 and depois["restante"] == 3500
    # A cobranca segue no dia pra onde o botao a empurrou: o pedaco pago nao anda o mes.
    assert len(depois["pagamentos"]) == 1 and depois["proximo_pagamento"] == "2026-10-30"


def test_pedaco_da_parcela_nao_anda_o_contador_nem_quita_a_divida(db):
    """"Mandei 3000 pro Rodrigo" numa parcela de 10.000 nao e uma parcela
    paga: antes andava a casa inteira, e tres pedacos quitavam a divida com
    21.000 faltando."""
    http = cliente_http(db)
    rodrigo = divida(http, valor_total=30000, parcelas_total=3, valor_parcela=10000)
    for dia in ("2026-09-10", "2026-09-20", "2026-09-30"):
        assert pagar(http, rodrigo["id"], valor=3000, pago_em=dia).status_code == 200

    atual = http.get("/financeiro/dividas").json()[0]
    assert atual["parcelas_pagas"] == 0
    assert atual["quitada"] is False
    assert atual["pago"] == 9000 and atual["restante"] == 21000


def test_pagamento_que_fecha_mais_de_uma_parcela_anda_as_duas(db):
    http = cliente_http(db)
    rodrigo = divida(http)
    depois = pagar(http, rodrigo["id"], valor=6000, pago_em="2026-09-30").json()

    assert depois["parcelas_pagas"] == 2 and depois["pago"] == 6000 and depois["restante"] == 3000
    assert depois["proximo_pagamento"] == "2026-11-30"
    http.delete(f"/financeiro/dividas/pagamentos/{depois['pagamentos'][0]['id']}")
    voltou = http.get("/financeiro/dividas").json()[0]
    assert voltou["parcelas_pagas"] == 0 and voltou["restante"] == 9000 and voltou["proximo_pagamento"] == "2026-09-30"


def test_pagamento_recusado_quando_a_divida_esta_congelada_ou_nao_existe(db):
    http = cliente_http(db)
    congelada = divida(http, congelada=True)
    recusado = pagar(http, congelada["id"], valor=500, pago_em="2026-09-12")
    assert recusado.status_code == 400 and "Reative" in recusado.json()["detail"]
    assert pagar(http, 9999, valor=500, pago_em="2026-09-12").status_code == 404
    assert http.delete("/financeiro/dividas/pagamentos/9999").status_code == 400
    assert pagar(http, congelada["id"], valor=0, pago_em="2026-09-12").status_code == 422


def test_excluir_divida_respeita_o_que_ja_saiu_do_banco(db):
    nu = conta(db)
    http = cliente_http(db)
    no_banco = divida(http)
    pagar(http, no_banco["id"], valor=3000, pago_em="2026-09-12", conta_id=nu.id)
    barrado = http.delete(f"/financeiro/dividas/{no_banco['id']}")
    assert barrado.status_code == 400 and "Caixa" in barrado.json()["detail"]
    assert db.query(LancamentoCaixa).count() == 1

    em_dinheiro = divida(http, credor="Hugo")
    pagar(http, em_dinheiro["id"], valor=1000, pago_em="2026-09-12")
    assert http.delete(f"/financeiro/dividas/{em_dinheiro['id']}").status_code == 200
    assert db.query(DividaPagamento).filter(DividaPagamento.divida_id == em_dinheiro["id"]).count() == 0
