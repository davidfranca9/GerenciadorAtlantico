"""A barra do pedido acompanha os agendamentos, venha o item de onde vier.

Os casos sao os achados em producao em 16/09/2026: 12 pedidos com a barra
abaixo do agendado (o 040947 com 152 t agendadas e barra em zero) porque a
autorizacao da tela de Contratos e o "Salvar e regerar" gravavam itens sem
o id do pedido - e agendamento apagado sem devolver o saldo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.apoio_documentos import banco_em_memoria, roteador_documentos  # noqa: E402

roteador_documentos()  # substitui o gerador de O.C. em HTML quando o WeasyPrint nao carrega

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import get_current_user  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models import Agendamento, AgendamentoEmail, AgendamentoItem, Pedido  # noqa: E402
from app.routers import agendamentos as rotas_agendamentos  # noqa: E402
from app.routers import documentos as rotas_documentos  # noqa: E402
from app.routers import pedidos as rotas_pedidos  # noqa: E402
from app.servicos import saldo_pedidos  # noqa: E402

SUPER = "SUPER SIMPLES GR 19% P2O5 10% S 16% CA"
UREIA = "UREIA PRILL MICROGRANULADA 46% N"


@pytest.fixture
def db():
    sessao = banco_em_memoria(Pedido, Agendamento, AgendamentoItem, AgendamentoEmail)
    sessao.add_all([
        Pedido(id=1, contrato="040947", cliente="ACACIO TORATTI", produto=SUPER, embalagem="BIG BAG",
               cidade="Ibiai-MG", toneladas_total=180, toneladas_usadas=0),
        # O 041556 UREIA real foi importado duas vezes: duas linhas iguais.
        Pedido(id=4, contrato="041556", cliente="WAGMAR", produto=UREIA, toneladas_total=32, toneladas_usadas=0),
        Pedido(id=23, contrato="041556", cliente="WAGMAR", produto=UREIA, toneladas_total=32, toneladas_usadas=0),
    ])
    sessao.commit()
    yield sessao
    sessao.close()


def barra(db, pedido_id):
    db.expire_all()
    return db.get(Pedido, pedido_id).toneladas_usadas


def item(toneladas, pedido="040947", produto=SUPER, pedido_id=None):
    return {"pedido": pedido, "cliente": "X", "produto": produto, "cidade": "", "embalagem": "BIG BAG",
            "toneladas": toneladas, "pedido_id": pedido_id}


def agendar(db, itens, status="Aguardando Agendamento"):
    agendamento = Agendamento(status=status, supplier="Heringer")
    db.add(agendamento)
    saldo_pedidos.gravar_itens(db, agendamento, itens)
    db.commit()
    return agendamento


# --------------------------------------------------------------------------
# Criar
# --------------------------------------------------------------------------


def test_com_o_id_do_pedido_a_barra_anda(db):
    agendar(db, [item(30, pedido_id=1)])
    assert barra(db, 1) == 30


def test_sem_o_id_acha_o_pedido_pelo_numero_e_produto(db):
    # O caso do 040947: agendado sem o id, barra parada em zero.
    agendamento = agendar(db, [item(32, pedido="40947", produto=SUPER.lower().replace(" ", "  "))])
    assert barra(db, 1) == 32
    assert agendamento.itens[0].pedido_ref_id == 1


def test_linha_duplicada_usa_a_que_tem_saldo(db):
    agendar(db, [item(32, pedido="041556", produto=UREIA)])
    agendar(db, [item(32, pedido="041556", produto=UREIA)])
    assert (barra(db, 4), barra(db, 23)) == (32, 32)


def test_nao_passa_do_total_do_pedido(db):
    agendar(db, [item(500, pedido_id=1)])
    assert barra(db, 1) == 180


def test_pedido_que_nao_esta_no_sistema_fica_sem_vinculo(db):
    agendamento = agendar(db, [item(10, pedido="99999")])
    assert agendamento.itens[0].pedido_ref_id is None
    assert barra(db, 1) == 0


# --------------------------------------------------------------------------
# Editar e regerar
# --------------------------------------------------------------------------


def test_regerar_os_mesmos_itens_nao_desconta_de_novo(db):
    # Gerar a O.C. e a autorizacao em sequencia grava o agendamento duas vezes.
    agendamento = agendar(db, [item(30, pedido_id=1)])
    saldo_pedidos.gravar_itens(db, agendamento, [item(30)])  # sem id: herda o vinculo
    db.commit()
    assert barra(db, 1) == 30


def test_editar_a_tonelada_ajusta_a_barra(db):
    agendamento = agendar(db, [item(30, pedido_id=1)])
    saldo_pedidos.gravar_itens(db, agendamento, [item(20)])
    db.commit()
    assert barra(db, 1) == 20


def test_trocar_o_pedido_do_item_move_o_saldo(db):
    agendamento = agendar(db, [item(32, pedido="041556", produto=UREIA)])
    saldo_pedidos.gravar_itens(db, agendamento, [item(10)])
    db.commit()
    assert (barra(db, 4), barra(db, 1)) == (0, 10)


# --------------------------------------------------------------------------
# Cancelar e excluir
# --------------------------------------------------------------------------


def test_cancelar_devolve_e_reabrir_desconta_de_novo(db):
    agendamento = agendar(db, [item(30, pedido_id=1)])
    saldo_pedidos.mudar_status(db, agendamento, "Cancelado")
    db.commit()
    assert barra(db, 1) == 0
    saldo_pedidos.mudar_status(db, agendamento, "Agendado")
    db.commit()
    assert barra(db, 1) == 30


def test_excluir_devolve(db):
    agendamento = agendar(db, [item(30, pedido_id=1)])
    saldo_pedidos.liberar(db, agendamento)
    db.commit()
    assert barra(db, 1) == 0


# --------------------------------------------------------------------------
# Conciliacao das barras que ja estao erradas
# --------------------------------------------------------------------------


def _dados_antigos(db):
    """Como estava em producao: item sem vinculo e barra que nao bate."""
    antigo = Agendamento(status="Agendado", supplier="Fertimaxi")
    antigo.itens = [AgendamentoItem(pedido="040947", produto=SUPER, toneladas=32)]
    cancelado = Agendamento(status="Cancelado", supplier="Fertimaxi")
    cancelado.itens = [AgendamentoItem(pedido="040947", produto=SUPER, toneladas=50)]
    db.add_all([antigo, cancelado])
    db.get(Pedido, 23).toneladas_usadas = 32  # descontado por agendamento que nao existe mais
    db.commit()
    return antigo


def test_conciliacao_so_mostra_sem_gravar(db):
    antigo = _dados_antigos(db)
    resultado = saldo_pedidos.conciliar(db, aplicar=False)
    mudancas = {m["pedido_id"]: (m["barra_atual"], m["barra_correta"]) for m in resultado["mudancas"]}
    assert mudancas == {1: (0, 32), 23: (32, 0)}  # o cancelado nao conta
    assert barra(db, 1) == 0 and barra(db, 23) == 32
    assert antigo.itens[0].pedido_ref_id is None


def test_conciliacao_aplicada_acerta_e_liga_os_itens(db):
    antigo = _dados_antigos(db)
    resultado = saldo_pedidos.conciliar(db, aplicar=True)
    assert resultado["aplicado"] is True
    assert (barra(db, 1), barra(db, 23)) == (32, 0)
    db.refresh(antigo)
    assert antigo.itens[0].pedido_ref_id == 1
    assert saldo_pedidos.conciliar(db, aplicar=False)["mudancas"] == []


# --------------------------------------------------------------------------
# Pelas rotas, do jeito que as telas chamam
# --------------------------------------------------------------------------


@pytest.fixture
def cliente(db, monkeypatch):
    monkeypatch.setattr(rotas_agendamentos, "_enviar_autorizacoes_agendamento_fertimaxi", lambda agendamento, **kw: None)
    app = FastAPI()
    for rota in (rotas_agendamentos.router, rotas_documentos.router, rotas_pedidos.router):
        app.include_router(rota)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: None
    return TestClient(app)


def test_rota_novo_agendamento_sem_id_enche_a_barra_e_devolve_o_vinculo(cliente, db):
    resposta = cliente.post("/agendamentos", json={
        "supplier": "Heringer", "itens": [{"pedido": "040947", "produto": SUPER, "toneladas": 32}],
    })
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["itens"][0]["pedido_id"] == 1
    assert barra(db, 1) == 32


def test_rota_cancelar_e_excluir_devolvem(cliente, db):
    criado = cliente.post("/agendamentos", json={"supplier": "Heringer", "itens": [item(40, pedido_id=1)]}).json()
    assert barra(db, 1) == 40
    assert cliente.patch(f"/agendamentos/{criado['id']}/status", json={"status": "Cancelado"}).status_code == 200
    assert barra(db, 1) == 0
    assert cliente.patch(f"/agendamentos/{criado['id']}/status", json={"status": "Agendado"}).status_code == 200
    assert barra(db, 1) == 40
    assert cliente.delete(f"/agendamentos/{criado['id']}").status_code == 200
    assert barra(db, 1) == 0


def test_rota_autorizacao_da_tela_de_contratos_sem_motorista_enche_a_barra(cliente, db):
    # O caminho do #132: autorizacao gerada em Contratos, sem motorista e sem id.
    corpo = {"template": "AFL", "data_carregamento": "16/09/2026", "produtos": [
        {"contrato": "040947", "produto": SUPER, "embalagem": "BIG BAG", "toneladas": "32", "cliente": "ACACIO TORATTI"},
    ]}
    primeira = cliente.post("/ordens-coleta/gerar-autorizacao", json=corpo)
    assert primeira.status_code == 200, primeira.text
    assert barra(db, 1) == 32

    agendamento_id = int(primeira.headers["x-agendamento-id"])
    # Regerar (O.C. e autorizacao em sequencia) nao desconta de novo...
    assert cliente.post("/ordens-coleta/gerar-autorizacao", json={**corpo, "agendamento_id": agendamento_id}).status_code == 200
    assert barra(db, 1) == 32
    # ...e mudar a tonelada na edicao ajusta.
    corpo["produtos"][0]["toneladas"] = "20"
    assert cliente.post("/ordens-coleta/gerar-autorizacao", json={**corpo, "agendamento_id": agendamento_id}).status_code == 200
    assert barra(db, 1) == 20


def test_rota_modelo_do_veiculo_fica_gravado_no_agendamento(cliente, db):
    corpo = {"template": "AFL", "data_carregamento": "16/09/2026", "nome": "MOTORISTA", "modelo_veiculo": "GRADE BAIXA",
             "produtos": [{"contrato": "040947", "produto": SUPER, "toneladas": "10", "cliente": "ACACIO TORATTI"}]}
    resposta = cliente.post("/ordens-coleta/gerar-autorizacao", json=corpo)
    assert resposta.status_code == 200, resposta.text
    agendamento = cliente.get(f"/agendamentos/{resposta.headers['x-agendamento-id']}").json()
    assert agendamento["modelo_veiculo"] == "GRADE BAIXA"


def test_rota_conciliacao_mostra_e_aplica(cliente, db):
    _dados_antigos(db)
    vista = cliente.get("/pedidos/conciliacao").json()
    assert vista["aplicado"] is False and len(vista["mudancas"]) == 2
    assert barra(db, 1) == 0
    aplicada = cliente.post("/pedidos/conciliacao").json()
    assert aplicada["aplicado"] is True
    assert barra(db, 1) == 32
