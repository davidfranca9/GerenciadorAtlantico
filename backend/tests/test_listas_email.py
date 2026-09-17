"""Listas de e-mail editaveis em Configuracoes.

O luan.santos deixou de existir na Fertimaxi e tirar ele da lista pedia mexer
no codigo. Nenhum e-mail sai daqui: o envio e simulado.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import get_current_user  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models import CartaFreteEnviada, ListaEmail  # noqa: E402
from app.routers import configuracoes  # noqa: E402
from app.servicos import carta_frete, emails_agendamento, listas_email  # noqa: E402
from tests.apoio_documentos import banco_em_memoria  # noqa: E402


@pytest.fixture
def db():
    sessao = banco_em_memoria(ListaEmail, CartaFreteEnviada)
    yield sessao
    sessao.close()


def cliente(db, papel="admin"):
    app = FastAPI()
    app.include_router(configuracoes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=papel, email="dono@atlantico.com")
    return TestClient(app)


def test_sem_mexer_vale_o_padrao(db):
    listas = {l["chave"]: l for l in cliente(db).get("/configuracoes/listas-email").json()}
    assert set(listas) == {"fertimaxi", "fertimaxi_novo_agendamento", "heringer", "abastecimento"}
    assert listas["fertimaxi"]["emails"] == ["agendamento@fertimaxi.com.br", "paulo.moura@fertimaxi.com.br"]
    assert listas["fertimaxi"]["personalizada"] is False


def test_incluir_e_remover_vale_no_proximo_envio(db):
    resposta = cliente(db).put("/configuracoes/listas-email/fertimaxi", json={"emails": [
        "agendamento@fertimaxi.com.br", " Novo.Contato@Fertimaxi.com.br ", "agendamento@fertimaxi.com.br",
    ]})
    assert resposta.status_code == 200, resposta.text
    salva = resposta.json()
    # Minusculo, sem espaco e sem repetir.
    assert salva["emails"] == ["agendamento@fertimaxi.com.br", "novo.contato@fertimaxi.com.br"]
    assert salva["personalizada"] is True and salva["atualizado_por"] == "dono@atlantico.com"
    assert emails_agendamento.destinatarios_da_fabrica("Fertimaxi", db) == salva["emails"]
    # A de Heringer continua a padrao.
    assert emails_agendamento.destinatarios_da_fabrica("Heringer", db) == listas_email.LISTAS["heringer"]["padrao"]


def test_email_invalido_ou_lista_vazia_nao_salva(db):
    http = cliente(db)
    invalido = http.put("/configuracoes/listas-email/heringer", json={"emails": ["expedicao.candeias@heringer.com.br", "fulano@"]})
    assert invalido.status_code == 400
    assert "fulano@" in invalido.json()["detail"]
    assert http.put("/configuracoes/listas-email/heringer", json={"emails": ["  "]}).status_code == 400
    assert db.get(ListaEmail, "heringer") is None


def test_voltar_ao_padrao(db):
    http = cliente(db)
    http.put("/configuracoes/listas-email/abastecimento", json={"emails": ["so.eu@gmail.com"]})
    voltou = http.delete("/configuracoes/listas-email/abastecimento").json()
    assert voltou["emails"] == listas_email.LISTAS["abastecimento"]["padrao"]
    assert voltou["personalizada"] is False


def test_lista_que_nao_existe(db):
    assert cliente(db).put("/configuracoes/listas-email/nao-existe", json={"emails": ["a@b.com"]}).status_code == 404


def test_so_administrador_mexe(db):
    assert cliente(db, papel="user").get("/configuracoes/listas-email").status_code == 403
    assert cliente(db, papel="user").put("/configuracoes/listas-email/fertimaxi", json={"emails": ["a@b.com"]}).status_code == 403


def test_autorizacao_de_abastecimento_vai_pra_lista_salva(db, monkeypatch, tmp_path):
    modelo = tmp_path / "modelo.docx"
    modelo.write_bytes(b"modelo")
    monkeypatch.setattr(carta_frete, "TEMPLATE_CF", modelo)
    listas_email.salvar(db, "abastecimento", ["financeiro@atlantico.com"])
    enviados = []
    carta_frete.enviar_agora(
        db, {"DATA": "17/09/2026", "CONDUTOR": "JOSE", "PLACA_CAVALO": "ABC-1D23"},
        gerar=lambda dados: "a.docx", converter=lambda caminho: "a.pdf",
        enviar=lambda para, assunto, corpo, anexos: enviados.append(para),
    )
    assert enviados == [["financeiro@atlantico.com"]]
    assert db.query(CartaFreteEnviada).one().destinatarios == "financeiro@atlantico.com"
