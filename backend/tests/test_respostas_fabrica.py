"""Respostas da fabrica mudam o agendamento so quando confirmam.

Textos reais da Fertimaxi de 15 a 17/09/2026. Nenhum e-mail e lido de
verdade: as mensagens entram prontas, como a caixa devolveria.
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.apoio_documentos import banco_em_memoria, roteador_documentos  # noqa: E402

roteador_documentos()  # substitui o gerador de O.C. em HTML quando o WeasyPrint nao carrega

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import get_current_user  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models import Agendamento, AgendamentoEmail, AgendamentoItem, Pedido, RespostaFabrica  # noqa: E402
from app.routers import agendamentos as rotas_agendamentos  # noqa: E402
from app.servicos import email_inbox, respostas_fabrica  # noqa: E402

HOJE = date(2026, 9, 17)
RODAPE = "Informamos que a partir de 01/07, o valor para acesso ao pátio de triagem será de R$ 46,50.\nAtenciosamente,\nElisangela Santos"


def citando(enviado: str, assunto: str) -> str:
    return (
        f"\n{RODAPE}\n________________________________\n"
        "De: atlanticofertlog.comercial@gmail.com <atlanticofertlog.comercial@gmail.com>\n"
        f"Enviado: quinta-feira, 17 de setembro de 2026 {enviado}\n"
        "Para: Agendamento Fertimaxi <agendamento@fertimaxi.com.br>\n"
        f"Assunto: {assunto}\n\nPrezados,\nSolicitamos, por gentileza, o agendamento do pedido para dia 18.09."
    )


# --------------------------------------------------------------------------
# Classificacao
# --------------------------------------------------------------------------


@pytest.mark.parametrize("texto, tipo, data", [
    ("PEDIDO 41595 NÃO CONTÉM O PRODUTO UREIA PRILL", "problema", ""),
    ("Disponibilidade para 21/09, podemos confirmar?\n21-set\n32\n41594\nFOB", "aguardando", "21/09/2026"),
    ("Dois veículos agendados para o dia 22/09, confirma?\n22-set\n40\n72", "aguardando", "22/09/2026"),
    ("Agendado para o dia 17/09, aguardando os dados para a confirmação;", "aguardando", "17/09/2026"),
    ("O agendamento está previsto para o dia 21/09. Aguardamos o envio dos dados necessários.", "aguardando", "21/09/2026"),
    ("Está enviando o mesmo agendamento", "problema", ""),
    ("O sulfato será carregado no Armazém vitória.\nPara confirmar o agendamento preciso da planilha com todos os dados.", "problema", ""),
    ("Esse pedido consta um saldo de 28 tons, podemos prosseguir?", "problema", ""),
    ("Já temos 2 veículo agendados para esse pedido, dessa forma a placa encaminhada fica impossibilitada", "problema", ""),
    ("Informamos que as janelas para carregamento de sacaria desta semana já estão preenchidas.", "problema", ""),
    ("ok", "confirmado", ""),
    ("ok\n17-set\nQXO6H85\n40\nATLANTICO FERTLOG", "confirmado", "17/09/2026"),
    ("22/09\n22-set\n40\n72\n72\n0\n41595\nFOB", "confirmado", "22/09/2026"),
    ("Boa tarde, segue pedido com a placa inclusa.\n16-set\nNYN2G61", "confirmado", "16/09/2026"),
    ("Sacaria estaremos agendando partir de sexta-feira.", "outro", ""),
    ("Não confirmado agendamento, pedido bloqueado no fiananceiro.", "problema", ""),
])
def test_classifica_as_respostas_reais(texto, tipo, data):
    assert respostas_fabrica.classificar(texto, HOJE) == (tipo, data)


def test_data_de_janeiro_respondida_em_dezembro_e_do_ano_seguinte():
    assert respostas_fabrica.extrair_data("previsto para 05/01", date(2026, 12, 20)) == "05/01/2027"
    assert respostas_fabrica.extrair_data("previsto para 31/02", HOJE) == ""


def test_resposta_sem_citacao_nem_rodape():
    corpo = "Bom dia!\nO sulfato será carregado no armazém vitória.\n" + citando("11:55", "AUTORIZAÇÃO AGENDAMENTO: X - Nº 041595")
    assert respostas_fabrica.texto_da_resposta(corpo) == "Bom dia!\nO sulfato será carregado no armazém vitória."


def test_citacao_em_horario_de_brasilia_vira_utc():
    quando, assunto = respostas_fabrica.citacao("ok" + citando("10:41", "AUTORIZAÇÃO AGENDAMENTO: CARLOS LUCAS MENDES - Nº 041595"))
    assert quando == datetime(2026, 9, 17, 13, 41)
    assert assunto == "AUTORIZAÇÃO AGENDAMENTO: CARLOS LUCAS MENDES - Nº 041595"


# --------------------------------------------------------------------------
# Ligar e aplicar
# --------------------------------------------------------------------------


def agendamento(id, criado, itens, status="Aguardando Agendamento", ids=""):
    a = Agendamento(id=id, supplier="Fertimaxi", status=status, loading_date="18/09/2026", created_at=criado, email_message_ids=ids)
    a.itens = [AgendamentoItem(pedido=p, cliente="CARLOS LUCAS MENDES", produto=produto, toneladas=t) for p, produto, t in itens]
    return a


@pytest.fixture
def db():
    sessao = banco_em_memoria(Pedido, Agendamento, AgendamentoItem, AgendamentoEmail, RespostaFabrica)
    sessao.add_all([
        agendamento(136, datetime(2026, 9, 17, 13, 41, 22), [("041595", "UREIA", 40)]),
        agendamento(137, datetime(2026, 9, 17, 13, 43, 45), [("038864", "UREIA", 8), ("041594", "SUPER SIMPLES", 32)]),
        agendamento(138, datetime(2026, 9, 17, 14, 17, 20), [("041595", "CLORETO", 40)]),
        agendamento(139, datetime(2026, 9, 17, 14, 18, 6), [("041595", "CLORETO", 32)]),
        agendamento(150, datetime(2026, 9, 18, 9, 0), [("042000", "MAP", 32)], ids="<autorizacao-150@atlanticofertlog.com.br>"),
        agendamento(151, datetime(2026, 9, 18, 9, 5), [("042001", "MAP", 32)], status="Cancelado", ids="<autorizacao-151@atlanticofertlog.com.br>"),
    ])
    sessao.commit()
    yield sessao
    sessao.close()


def mensagem(id, recebido, texto, conversa="", in_reply_to=""):
    # O assunto da resposta e o do e-mail citado com "RE:" na frente.
    _, citado = respostas_fabrica.citacao(texto)
    return {"message_id": f"<{id}@fertimaxi>", "recebido_em": recebido, "texto": texto, "conversa": conversa,
            "in_reply_to": in_reply_to, "references": "", "remetente": "agendamento@fertimaxi.com.br",
            "assunto": f"RE: {citado or 'AUTORIZAÇÃO AGENDAMENTO'}"}


DO_DIA_17 = [
    mensagem("8851", datetime(2026, 9, 17, 13, 59), "PEDIDO 41595 NÃO CONTÉM O PRODUTO UREIA PRILL"
             + citando("10:41", "AUTORIZAÇÃO AGENDAMENTO: CARLOS LUCAS MENDES - Nº 041595"), conversa="t-41595"),
    mensagem("8852", datetime(2026, 9, 17, 14, 0), "Disponibilidade para 21/09, podemos confirmar?\n21-set\n32"
             + citando("10:43", "AUTORIZAÇÃO AGENDAMENTO: CARLOS LUCAS MENDES - Nº 041594"), conversa="t-41594"),
    mensagem("8856", datetime(2026, 9, 17, 14, 37), "Dois veículos agendados para o dia 22/09, confirma?"
             + citando("11:17", "AUTORIZAÇÃO AGENDAMENTO: CARLOS LUCAS MENDES - Nº 041595"), conversa="t-41595"),
    # Resposta a uma resposta nossa ("Re:"), noutra conversa do Gmail e sem a
    # lista de e-mails anteriores: vale a ultima resposta com o mesmo assunto.
    mensagem("8858", datetime(2026, 9, 17, 14, 52), "ok"
             + citando("11:41", "Re: AUTORIZAÇÃO AGENDAMENTO: CARLOS LUCAS MENDES - Nº 041594"), conversa="t-8858"),
]


def respostas(db, agendamento_id):
    return [(r.tipo, r.data, r.aplicada) for r in db.query(RespostaFabrica).filter_by(agendamento_id=agendamento_id).order_by(RespostaFabrica.recebido_em)]


def test_dia_17_so_o_ok_confirma(db):
    respostas_fabrica.processar(db, DO_DIA_17)
    db.commit()

    # Problema e pergunta nao mexem no agendamento.
    assert respostas(db, 136) == [("problema", "", False)]
    assert db.get(Agendamento, 136).status == "Aguardando Agendamento"
    assert respostas(db, 138) == [("aguardando", "22/09/2026", False)]
    assert db.get(Agendamento, 138).data_agendada == ""
    assert respostas(db, 139) == []

    # "ok" depois do "podemos confirmar?": vale a data proposta.
    assert respostas(db, 137) == [("aguardando", "21/09/2026", False), ("confirmado", "21/09/2026", True)]
    confirmado = db.get(Agendamento, 137)
    assert confirmado.status == "Agendado"
    assert confirmado.data_agendada == "21/09/2026"
    assert confirmado.agendamento_confirmado_por == respostas_fabrica.CONFIRMADO_POR
    assert confirmado.agendamento_confirmado_em == datetime(2026, 9, 17, 14, 52)


def test_mesma_resposta_nao_e_lida_duas_vezes(db):
    respostas_fabrica.processar(db, DO_DIA_17)
    respostas_fabrica.processar(db, DO_DIA_17)
    db.commit()
    assert db.query(RespostaFabrica).count() == 4


def test_ligacao_pelo_message_id_do_e_mail_que_saiu(db):
    resumo = respostas_fabrica.processar(db, [mensagem(
        "9001", datetime(2026, 9, 18, 12, 0), "Agendamento confirmado para 25/09.",
        in_reply_to="<autorizacao-150@atlanticofertlog.com.br>",
    )])
    db.commit()
    assert resumo[0]["como_ligou"] == "resposta"
    assert db.get(Agendamento, 150).status == "Agendado"
    assert db.get(Agendamento, 150).data_agendada == "25/09/2026"


def test_cancelado_nao_volta_a_agendado(db):
    respostas_fabrica.processar(db, [mensagem(
        "9002", datetime(2026, 9, 18, 12, 0), "ok, agendado 22/09", in_reply_to="<autorizacao-151@atlanticofertlog.com.br>",
    )])
    db.commit()
    assert db.get(Agendamento, 151).status == "Cancelado"
    assert respostas(db, 151) == [("confirmado", "22/09/2026", False)]


def test_confirmacao_feita_depois_na_tela_nao_e_desfeita(db):
    manual = db.get(Agendamento, 150)
    manual.data_agendada, manual.agendamento_confirmado_em = "30/09/2026", datetime(2026, 9, 18, 15, 0)
    db.commit()
    respostas_fabrica.processar(db, [mensagem(
        "9003", datetime(2026, 9, 18, 12, 0), "Agendado para 25/09", in_reply_to="<autorizacao-150@atlanticofertlog.com.br>",
    )])
    db.commit()
    assert db.get(Agendamento, 150).data_agendada == "30/09/2026"


def test_resposta_sem_ligacao_fica_gravada_sem_agendamento(db):
    respostas_fabrica.processar(db, [mensagem("9004", datetime(2026, 9, 18, 12, 0), "ok 22/09")])
    db.commit()
    gravada = db.query(RespostaFabrica).one()
    assert gravada.agendamento_id is None


def test_previa_nao_grava_nada(db, monkeypatch):
    monkeypatch.setattr(email_inbox, "mensagens_para_ler", lambda busca, ja_lidas, limite=60: DO_DIA_17)
    previa = respostas_fabrica.ler_da_caixa(db, aplicar=False)
    assert previa["lidas"] == 4 and previa["aplicadas"] == 1
    assert db.query(RespostaFabrica).count() == 0
    assert db.get(Agendamento, 137).status == "Aguardando Agendamento"

    feito = respostas_fabrica.ler_da_caixa(db, aplicar=True)
    assert feito["aplicadas"] == 1
    assert db.get(Agendamento, 137).status == "Agendado"


# --------------------------------------------------------------------------
# O Message-ID de quem sai fica no agendamento
# --------------------------------------------------------------------------


def test_novo_agendamento_guarda_o_message_id_das_autorizacoes(db, monkeypatch):
    enviados = iter(["<saiu-1@atlanticofertlog.com.br>", "<saiu-2@atlanticofertlog.com.br>"])
    monkeypatch.setattr(rotas_agendamentos, "send_email_message", lambda *args, **kwargs: next(enviados))
    monkeypatch.setattr(rotas_agendamentos, "_gerar_anexos_oc", lambda agendamento: [])
    app = FastAPI()
    app.include_router(rotas_agendamentos.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: None
    resposta = TestClient(app).post("/agendamentos", json={
        "supplier": "Fertimaxi", "loading_date": "20/09/2026",
        "itens": [
            {"pedido": "042000", "cliente": "CLIENTE A", "produto": "MAP", "toneladas": 20},
            {"pedido": "042001", "cliente": "CLIENTE B", "produto": "MAP", "toneladas": 12},
        ],
    })
    assert resposta.status_code == 200, resposta.text
    novo = db.get(Agendamento, resposta.json()["id"])
    assert novo.email_message_ids.split() == ["<saiu-1@atlanticofertlog.com.br>", "<saiu-2@atlanticofertlog.com.br>"]
    assert resposta.json()["respostas_fabrica"] == []


def test_registrar_envio_ignora_vazio_e_repetido():
    a = Agendamento(email_message_ids="")
    respostas_fabrica.registrar_envio(a, "<a@x>")
    respostas_fabrica.registrar_envio(a, "<a@x>")
    respostas_fabrica.registrar_envio(a, None)
    respostas_fabrica.registrar_envio(a, True)
    assert a.email_message_ids == "<a@x>"


def test_ok_ligado_pela_lista_de_e_mails_anteriores(db):
    """Com References, o "ok" cai no agendamento da resposta que respondemos,
    mesmo com dois agendamentos no mesmo assunto."""
    pergunta = mensagem("9101", datetime(2026, 9, 18, 12, 0), "Disponibilidade para 23/09, podemos confirmar?",
                        in_reply_to="<autorizacao-150@atlanticofertlog.com.br>")
    ok = mensagem("9102", datetime(2026, 9, 18, 13, 0), "ok" + citando("09:30", "Re: RE: AUTORIZAÇÃO AGENDAMENTO: X - Nº 042000"),
                  conversa="outra")
    ok["references"] = "<autorizacao-150@nao-guardado> <9101@fertimaxi> <nossa-resposta@gmail.com>"
    respostas_fabrica.processar(db, [pergunta, ok])
    db.commit()
    assert respostas(db, 150) == [("aguardando", "23/09/2026", False), ("confirmado", "23/09/2026", True)]
    assert db.get(Agendamento, 150).status == "Agendado"
