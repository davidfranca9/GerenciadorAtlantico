"""Autorizacao de abastecimento (antiga carta frete): baixar, enviar agora e
agendar - e o agendado sai uma vez so.

Nenhum e-mail sai daqui: o correio, a geracao do .docx e a conversao pra PDF
entram simulados. O banco e SQLite em memoria com a tabela real.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import CartaFreteEnviada  # noqa: E402
from app.servicos import carta_frete  # noqa: E402
from tests.apoio_documentos import banco_em_memoria, cliente_http  # noqa: E402

AGORA = datetime(2026, 9, 14, 12, 0)
DADOS = {
    "DATA": "14/09/2026", "CONDUTOR": "TALISSON JUNIOR GUIMARAES RIBEIRO", "CPF": "121.597.816-22",
    "PLACA_CAVALO": "PFJ-2I64", "VALOR_FRETE": "1.500,00", "AUTORIZACAO_NUM": "123",
}


class Correio:
    def __init__(self, falhar=False):
        self.enviados, self.falhar = [], falhar

    def __call__(self, destinatarios, assunto, corpo, anexos, **kwargs):
        if self.falhar:
            raise RuntimeError("SMTP fora do ar")
        self.enviados.append({"destinatarios": destinatarios, "assunto": assunto, "anexos": anexos})


def etapas(correio):
    return {"gerar": lambda dados: "carta.docx", "converter": lambda caminho: "carta.pdf", "enviar": correio}


@pytest.fixture
def db():
    sessao = banco_em_memoria(CartaFreteEnviada)
    yield sessao
    sessao.close()


@pytest.fixture(autouse=True)
def modelo_presente(monkeypatch, tmp_path):
    modelo = tmp_path / "carta.docx"
    modelo.write_bytes(b"modelo")
    monkeypatch.setattr(carta_frete, "TEMPLATE_CF", modelo)


# --------------------------------------------------------------------------
# Agendar
# --------------------------------------------------------------------------


def test_agendar_guarda_os_dados_e_o_horario(db):
    carta = carta_frete.agendar(db, DADOS, AGORA + timedelta(hours=2), agora=AGORA)
    assert carta.status == "agendada"
    assert carta.agendada_para == AGORA + timedelta(hours=2)
    assert json.loads(carta.dados)["CONDUTOR"] == "TALISSON JUNIOR GUIMARAES RIBEIRO"
    assert carta.enviada_em is None


def test_nao_agenda_no_passado(db):
    with pytest.raises(carta_frete.CartaFreteInvalida, match="futuro"):
        carta_frete.agendar(db, DADOS, AGORA - timedelta(minutes=1), agora=AGORA)


def test_nao_agenda_sem_condutor(db):
    with pytest.raises(carta_frete.CartaFreteInvalida, match="condutor"):
        carta_frete.agendar(db, {**DADOS, "CONDUTOR": "  "}, AGORA + timedelta(hours=1), agora=AGORA)


# --------------------------------------------------------------------------
# A tarefa periodica
# --------------------------------------------------------------------------


def test_manda_so_o_que_ja_passou_da_hora(db):
    carta_frete.agendar(db, DADOS, AGORA + timedelta(hours=1), agora=AGORA)
    depois = carta_frete.agendar(db, {**DADOS, "CONDUTOR": "OUTRO"}, AGORA + timedelta(hours=3), agora=AGORA)
    correio = Correio()

    assert carta_frete.enviar_agendadas(db, agora=AGORA + timedelta(hours=2), **etapas(correio)) == 1

    assert len(correio.enviados) == 1
    assert correio.enviados[0]["assunto"] == "AUTORIZAÇÃO ABASTECIMENTO: TALISSON JUNIOR GUIMARAES RIBEIRO - PFJ-2I64"
    assert correio.enviados[0]["anexos"] == ["carta.pdf"]
    assert correio.enviados[0]["destinatarios"] == carta_frete.DESTINATARIOS
    db.refresh(depois)
    assert depois.status == "agendada"
    enviada = db.query(CartaFreteEnviada).filter(CartaFreteEnviada.status == "enviada").one()
    assert enviada.enviada_em is not None


def test_agendada_sai_uma_vez_so(db):
    carta_frete.agendar(db, DADOS, AGORA + timedelta(hours=1), agora=AGORA)
    correio = Correio()
    for _ in range(3):
        carta_frete.enviar_agendadas(db, agora=AGORA + timedelta(hours=2), **etapas(correio))
    assert len(correio.enviados) == 1


def test_carta_reservada_por_outro_processo_nao_sai_de_novo(db):
    # Dois processos rodando a tarefa: quem chegou primeiro ja marcou
    # "enviando". O segundo nao pode mandar tambem.
    carta = carta_frete.agendar(db, DADOS, AGORA + timedelta(hours=1), agora=AGORA)
    carta.status = "enviando"
    db.commit()
    correio = Correio()
    assert carta_frete.enviar_agendadas(db, agora=AGORA + timedelta(hours=2), **etapas(correio)) == 0
    assert correio.enviados == []


def test_falha_no_envio_marca_erro_e_nao_repete_sozinho(db):
    carta = carta_frete.agendar(db, DADOS, AGORA + timedelta(hours=1), agora=AGORA)
    carta_frete.enviar_agendadas(db, agora=AGORA + timedelta(hours=2), **etapas(Correio(falhar=True)))
    db.refresh(carta)
    assert carta.status == "erro"
    assert "SMTP" in carta.erro

    correio = Correio()
    carta_frete.enviar_agendadas(db, agora=AGORA + timedelta(hours=3), **etapas(correio))
    assert correio.enviados == []


# --------------------------------------------------------------------------
# Cancelar
# --------------------------------------------------------------------------


def test_cancelada_nao_sai(db):
    carta = carta_frete.agendar(db, DADOS, AGORA + timedelta(hours=1), agora=AGORA)
    assert carta_frete.cancelar(db, carta.id).status == "cancelada"
    correio = Correio()
    carta_frete.enviar_agendadas(db, agora=AGORA + timedelta(hours=2), **etapas(correio))
    assert correio.enviados == []


def test_nao_cancela_o_que_ja_saiu(db):
    carta = carta_frete.agendar(db, DADOS, AGORA + timedelta(hours=1), agora=AGORA)
    carta_frete.enviar_agendadas(db, agora=AGORA + timedelta(hours=2), **etapas(Correio()))
    with pytest.raises(carta_frete.CartaFreteInvalida, match="enviada"):
        carta_frete.cancelar(db, carta.id)


def test_cancelar_carta_que_nao_existe(db):
    with pytest.raises(LookupError):
        carta_frete.cancelar(db, 999)


# --------------------------------------------------------------------------
# Enviar agora
# --------------------------------------------------------------------------


def test_enviar_agora_registra_enviada(db):
    correio = Correio()
    carta = carta_frete.enviar_agora(db, DADOS, **etapas(correio))
    assert carta.status == "enviada" and carta.enviada_em is not None
    assert len(correio.enviados) == 1


def test_enviar_agora_que_falha_fica_na_lista_como_erro(db):
    with pytest.raises(RuntimeError):
        carta_frete.enviar_agora(db, DADOS, **etapas(Correio(falhar=True)))
    carta = db.query(CartaFreteEnviada).one()
    assert carta.status == "erro" and "SMTP" in carta.erro


# --------------------------------------------------------------------------
# As rotas, pela API
# --------------------------------------------------------------------------


def test_rota_agendar_converte_o_horario_da_tela_para_utc(db):
    cliente, _ = cliente_http(db)
    # A tela manda o horario local com fuso: 14h em Brasilia sao 17h UTC.
    resposta = cliente.post("/cartas-frete/agendar", json={**DADOS, "enviar_em": "2030-09-20T14:00:00-03:00"})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["status"] == "agendada"
    carta = db.query(CartaFreteEnviada).one()
    assert carta.agendada_para == datetime(2030, 9, 20, 17, 0)


def test_rota_agendar_no_passado_explica(db):
    cliente, _ = cliente_http(db)
    resposta = cliente.post("/cartas-frete/agendar", json={**DADOS, "enviar_em": "2020-01-01T10:00:00Z"})
    assert resposta.status_code == 400
    assert "futuro" in resposta.json()["detail"]


def test_rota_cancelar_e_a_lista_mostram_o_agendamento(db):
    cliente, _ = cliente_http(db)
    criada = cliente.post("/cartas-frete/agendar", json={**DADOS, "enviar_em": "2030-09-20T17:00:00Z"}).json()

    assert cliente.post(f"/cartas-frete/{criada['id']}/cancelar").json()["status"] == "cancelada"
    assert cliente.post(f"/cartas-frete/{criada['id']}/cancelar").status_code == 409
    assert cliente.post("/cartas-frete/999/cancelar").status_code == 404

    lista = cliente.get("/cartas-frete").json()
    assert lista[0]["status"] == "cancelada"
    assert lista[0]["agendada_para"].startswith("2030-09-20T17:00")


# --------------------------------------------------------------------------
# Nome do arquivo
# --------------------------------------------------------------------------


def test_anexo_do_email_sai_no_padrao_e_nao_como_carta_frete(monkeypatch, tmp_path):
    from docx import Document

    modelo = tmp_path / "modelo_real.docx"
    doc = Document()
    doc.add_paragraph("Nome do Condutor: {{CONDUTOR}}")
    doc.save(str(modelo))
    monkeypatch.setattr(carta_frete, "TEMPLATE_CF", modelo)
    correio = Correio()

    carta_frete._mandar(DADOS, converter=lambda caminho: caminho[:-5] + ".pdf", enviar=correio)

    anexo = Path(correio.enviados[0]["anexos"][0]).name
    assert anexo == "Autorizacao Abastecimento_TALISSON JUNIOR GUIMARAES RIBEIRO.pdf"


def test_nome_do_arquivo_sem_caractere_proibido_e_sem_condutor():
    assert carta_frete.nome_do_arquivo({"CONDUTOR": ' JOSE/DA "SILVA"? '}) == "Autorizacao Abastecimento_JOSEDA SILVA"
    assert carta_frete.nome_do_arquivo({"CONDUTOR": ""}) == "Autorizacao Abastecimento_Motorista"
