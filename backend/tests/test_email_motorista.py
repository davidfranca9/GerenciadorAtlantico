"""Inclusao e substituicao de motorista: grava, junta pedidos e manda e-mail novo.

Nenhum e-mail sai daqui: o envio e simulado. O banco e SQLite em memoria.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.apoio_documentos import banco_em_memoria, roteador_documentos  # noqa: E402

roteador_documentos()

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import get_current_user  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models import Agendamento, AgendamentoEmail, AgendamentoItem, Pedido  # noqa: E402
from app.routers import agendamentos as rotas_agendamentos  # noqa: E402
from app.routers import documentos as rotas_documentos  # noqa: E402

SUPER = "SUPER SIMPLES GR 19% P2O5 10% S 16% CA"
UREIA = "UREIA PRILL MICROGRANULADA 46% N"
MOTORISTA = {
    "driver_name": "TALISSON JUNIOR GUIMARAES RIBEIRO", "driver_cpf": "12159781622", "driver_phone": "(38) 99999-0000",
    "cnh": "123456", "plate_cavalo": "PFJ2I64", "plate_carreta1": "NZB4H89", "modelo_veiculo": "SIDER",
}


class Correio:
    def __init__(self, falhar=False):
        self.enviados, self.falhar = [], falhar

    def __call__(self, para, assunto, corpo, anexos=None, imagens_inline=None):
        if self.falhar:
            raise RuntimeError("SMTP fora do ar")
        self.enviados.append({"para": list(para), "assunto": assunto, "corpo": corpo, "anexos": [Path(a).name for a in anexos or []]})


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setattr(settings, "emails_motorista_em_teste", True)
    monkeypatch.setattr(settings, "email_teste_fabrica", "teste@exemplo.com")
    monkeypatch.setattr(settings, "gmail_sender_email", "sistema@exemplo.com")


@pytest.fixture
def db():
    sessao = banco_em_memoria(Pedido, Agendamento, AgendamentoItem, AgendamentoEmail)
    sessao.add_all([
        Pedido(id=1, contrato="040947", cliente="ACACIO TORATTI", produto=SUPER, embalagem="BIG BAG",
               cidade="Ibiai-MG", toneladas_total=120, toneladas_usadas=32),
        Pedido(id=2, contrato="041556", cliente="WAGMAR JOSE DE OLIVEIRA", produto=UREIA, embalagem="SACARIA",
               cidade="Águas Vermelhas-MG", toneladas_total=32, toneladas_usadas=0),
    ])
    sem_motorista = Agendamento(id=10, supplier="Fertimaxi", status="Aguardando Agendamento", loading_date="20/09/2026")
    sem_motorista.itens = [AgendamentoItem(pedido="040947", cliente="ACACIO TORATTI", produto=SUPER, embalagem="BIG BAG",
                                           cidade="Ibiai-MG", toneladas=32, pedido_ref_id=1)]
    com_motorista = Agendamento(id=11, supplier="Fertimaxi", status="Agendado", loading_date="20/09/2026",
                                driver_name="JOAO ANTIGO", driver_cpf="11122233344", plate_cavalo="ABC1D23")
    com_motorista.itens = [AgendamentoItem(pedido="040947", cliente="ACACIO TORATTI", produto=SUPER, toneladas=10)]
    heringer = Agendamento(id=12, supplier="Heringer", status="Aguardando Agendamento", loading_date="20/09/2026")
    heringer.itens = [AgendamentoItem(pedido="777", cliente="CLIENTE H", produto="NPK", toneladas=5)]
    sessao.add_all([sem_motorista, com_motorista, heringer])
    sessao.commit()
    yield sessao
    sessao.close()


@pytest.fixture
def correio(monkeypatch):
    correio = Correio()
    monkeypatch.setattr(rotas_agendamentos, "send_email_message", correio)
    monkeypatch.setattr(rotas_documentos, "send_email_message", correio)
    return correio


@pytest.fixture
def http(db, correio):
    app = FastAPI()
    app.include_router(rotas_agendamentos.router)
    app.include_router(rotas_documentos.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"email": "operador@exemplo.com"})()
    return TestClient(app)


def barra(db, pedido_id):
    db.expire_all()
    return db.get(Pedido, pedido_id).toneladas_usadas


def enviar(http, agendamento_id, tipo, **extra):
    return http.post(f"/agendamentos/{agendamento_id}/email-motorista", json={"tipo": tipo, **MOTORISTA, **extra})


# --------------------------------------------------------------------------
# Inclusao
# --------------------------------------------------------------------------


def test_inclusao_grava_junta_pedido_e_manda_email_de_teste(http, db, correio):
    resposta = enviar(http, 10, "inclusao", mensagem="Prezados,\n\nSegue a inclusão.", novos_itens=[
        {"pedido_id": 2, "pedido": "041556", "produto": UREIA, "cliente": "WAGMAR JOSE DE OLIVEIRA",
         "embalagem": "SACARIA", "cidade": "Águas Vermelhas-MG", "toneladas": 10},
    ])
    assert resposta.status_code == 200, resposta.text
    agendamento = resposta.json()["agendamento"]
    assert agendamento["driver_name"] == MOTORISTA["driver_name"]
    assert agendamento["modelo_veiculo"] == "SIDER"
    assert len(agendamento["itens"]) == 2
    # O pedido que entrou junto desconta; o que ja estava, nao.
    assert (barra(db, 1), barra(db, 2)) == (32, 10)

    [email] = correio.enviados
    assert email["para"] == ["teste@exemplo.com", "sistema@exemplo.com"]
    assert email["assunto"] == "[TESTE] INCLUSÃO DE PLACAS: TALISSON JUNIOR GUIMARAES RIBEIRO - Nº 040947 / 041556"
    corpo = email["corpo"]
    for trecho in ("Segue a inclusão.", "121.597.816-22", "PFJ-2I64", "NZB-4H89", "SIDER", "041556",
                   "Motorista a incluir", "agendamento@fertimaxi.com.br", "E-mail de teste"):
        assert trecho in corpo, trecho
    assert email["anexos"] == ["Autorizacao de carregamento_TALISSON JUNIOR GUIMARAES RIBEIRO.xlsx"]

    historico = agendamento["emails"]
    assert len(historico) == 1 and historico[0]["tipo"] == "inclusao" and historico[0]["teste"] is True
    assert historico[0]["enviado_por"] == "operador@exemplo.com"


def test_texto_e_assunto_prontos_quando_nao_escritos(http, correio):
    assert enviar(http, 10, "inclusao").status_code == 200
    corpo = correio.enviados[0]["corpo"]
    assert "Solicitamos, por gentileza, a inclusão das placas" in corpo
    assert "carregamento previsto para 20/09/2026" in corpo


def test_assunto_escrito_pela_pessoa_e_respeitado(http, correio):
    assert enviar(http, 10, "inclusao", assunto="INCLUSÃO URGENTE").status_code == 200
    assert correio.enviados[0]["assunto"] == "[TESTE] INCLUSÃO URGENTE"


def test_inclusao_em_agendamento_que_ja_tem_motorista_e_recusada(http, correio):
    resposta = enviar(http, 11, "inclusao")
    assert resposta.status_code == 409 and "substituicao" in resposta.json()["detail"]
    assert correio.enviados == []


@pytest.mark.parametrize("campos, trecho", [
    ({"driver_name": ""}, "nome do motorista"),
    ({"plate_cavalo": ""}, "placa do cavalo"),
    ({"tipo": "troca"}, "Tipo de e-mail"),
])
def test_dados_minimos(http, correio, campos, trecho):
    resposta = http.post("/agendamentos/10/email-motorista", json={"tipo": "inclusao", **MOTORISTA, **campos})
    assert resposta.status_code == 400 and trecho in resposta.json()["detail"]
    assert correio.enviados == []


# --------------------------------------------------------------------------
# Substituicao
# --------------------------------------------------------------------------


def test_substituicao_diz_quem_sai_e_quem_entra(http, db, correio):
    resposta = enviar(http, 11, "substituicao")
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["agendamento"]["driver_name"] == MOTORISTA["driver_name"]
    corpo = correio.enviados[0]["corpo"]
    assert "Motorista que sai" in corpo and "JOAO ANTIGO" in corpo and "ABC-1D23" in corpo and "111.222.333-44" in corpo
    assert "sai JOAO ANTIGO e entra o motorista abaixo" in corpo
    assert correio.enviados[0]["assunto"].startswith("[TESTE] SUBSTITUIÇÃO DE MOTORISTA: TALISSON")
    assert resposta.json()["agendamento"]["emails"][0]["motorista_anterior"] == "JOAO ANTIGO"


def test_substituicao_sem_motorista_e_recusada(http, correio):
    resposta = enviar(http, 10, "substituicao")
    assert resposta.status_code == 409 and "inclusao" in resposta.json()["detail"]


# --------------------------------------------------------------------------
# Se o e-mail nao sai, nada muda
# --------------------------------------------------------------------------


def test_email_que_falha_nao_grava_nada(http, db, correio):
    correio.falhar = True
    resposta = enviar(http, 10, "inclusao", novos_itens=[{"pedido_id": 2, "pedido": "041556", "produto": UREIA, "toneladas": 10}])
    assert resposta.status_code == 502 and "Nada foi alterado" in resposta.json()["detail"]
    db.expire_all()
    assert db.get(Agendamento, 10).driver_name in ("", None)
    assert len(db.get(Agendamento, 10).itens) == 1
    assert barra(db, 2) == 0
    assert db.query(AgendamentoEmail).count() == 0


# --------------------------------------------------------------------------
# Destino: teste x fabrica
# --------------------------------------------------------------------------


def test_fora_do_modo_teste_vai_pra_fabrica(http, correio, monkeypatch):
    monkeypatch.setattr(settings, "emails_motorista_em_teste", False)
    assert enviar(http, 10, "inclusao").status_code == 200
    email = correio.enviados[0]
    assert email["para"] == rotas_documentos.RECIPIENTS_FERTIMAX + ["sistema@exemplo.com"]
    assert not email["assunto"].startswith("[TESTE]")
    assert "E-mail de teste" not in email["corpo"]


def test_heringer_vai_pra_heringer(http, correio, monkeypatch):
    monkeypatch.setattr(settings, "emails_motorista_em_teste", False)
    assert enviar(http, 12, "inclusao").status_code == 200
    assert "expedicao.candeias@heringer.com.br" in correio.enviados[0]["para"]


def test_config_diz_se_esta_em_teste(http):
    config = http.get("/agendamentos/email-motorista/config").json()
    assert config["em_teste"] is True and config["email_teste"] == "teste@exemplo.com"
    assert "agendamento@fertimaxi.com.br" in config["destinatarios"]["Fertimaxi"]
    assert "{pedidos}" in config["modelos"]["inclusao"]


# --------------------------------------------------------------------------
# Contratos: enviar sem motorista registra o agendamento
# --------------------------------------------------------------------------


def test_contratos_enviar_sem_motorista_registra_o_agendamento(http, db, correio):
    corpo = {"template": "AFL", "data_carregamento": "20/09/2026", "teste": True, "produtos": [
        {"contrato": "040947", "produto": SUPER, "embalagem": "BIG BAG", "toneladas": "10", "cliente": "ACACIO TORATTI"},
    ]}
    primeira = http.post("/ordens-coleta/enviar-autorizacao-email", json=corpo)
    assert primeira.status_code == 200, primeira.text
    agendamento_id = primeira.json()["agendamento_id"]
    assert correio.enviados[0]["para"] == ["teste@exemplo.com", "sistema@exemplo.com"]
    assert correio.enviados[0]["assunto"].startswith("[TESTE] AUTORIZAÇÃO AGENDAMENTO: ACACIO TORATTI")
    assert barra(db, 1) == 42

    # Enviar de novo pro mesmo agendamento atualiza, nao cria outro.
    segunda = http.post("/ordens-coleta/enviar-autorizacao-email", json={**corpo, "agendamento_id": agendamento_id})
    assert segunda.status_code == 200 and segunda.json()["agendamento_id"] == agendamento_id
    assert db.query(Agendamento).count() == 4
    assert barra(db, 1) == 42

    # E e nele que a inclusao do motorista acontece depois.
    assert enviar(http, agendamento_id, "inclusao").status_code == 200


def test_novo_agendamento_em_teste_manda_pro_endereco_de_teste(http, correio):
    resposta = http.post("/agendamentos", json={
        "supplier": "Fertimaxi", "loading_date": "20/09/2026", "teste": True,
        "itens": [{"pedido": "041556", "cliente": "WAGMAR JOSE DE OLIVEIRA", "produto": UREIA, "toneladas": 5}],
    })
    assert resposta.status_code == 200, resposta.text
    assert correio.enviados[0]["para"] == ["teste@exemplo.com", "sistema@exemplo.com"]
    assert correio.enviados[0]["assunto"].startswith("[TESTE] AUTORIZAÇÃO AGENDAMENTO")
