"""Correção do valor da autorização de abastecimento.

O posto já recebeu o valor antigo, então duas coisas têm que acontecer: a
correção fica registrada (quando e por quê) e o acerto sai NA MESMA CONVERSA
do e-mail original, pra quem recebeu ler logo abaixo da autorização errada.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.apoio_documentos import banco_em_memoria  # noqa: E402

from app.models import CartaFreteCorrecao, CartaFreteEnviada, ListaEmail  # noqa: E402
from app.servicos import carta_frete  # noqa: E402

DADOS = {
    "DATA": "02/10/2026", "CONDUTOR": "TALISSON JUNIOR GUIMARAES RIBEIRO", "CPF": "121.597.816-22",
    "PLACA_CAVALO": "PFJ-2I64", "VALOR_FRETE": "1.200,00", "AUTORIZACAO_NUM": "2400",
}


class Correio:
    """Guarda o que saiu, inclusive a conversa que a mensagem responde."""

    def __init__(self, falhar=False):
        self.enviados, self.falhar = [], falhar

    def __call__(self, destinatarios, assunto, corpo, anexos, responder_a="", **kwargs):
        if self.falhar:
            raise RuntimeError("SMTP fora do ar")
        self.enviados.append({
            "para": destinatarios, "assunto": assunto, "corpo": corpo,
            "responder_a": responder_a, "anexos": anexos,
        })
        return f"<msg-{len(self.enviados)}@atlanticofertlog.com.br>"


@pytest.fixture
def db():
    sessao = banco_em_memoria(CartaFreteEnviada, CartaFreteCorrecao, ListaEmail)
    yield sessao
    sessao.close()


@pytest.fixture
def etapas(tmp_path):
    """Não gera documento de verdade: o docx/pdf não é o assunto daqui."""
    arquivo = tmp_path / "autorizacao.docx"
    arquivo.write_text("x", encoding="utf-8")
    return {"gerar": lambda dados: str(arquivo), "converter": lambda caminho: caminho[:-5] + ".pdf"}


def enviada(db, correio, etapas) -> CartaFreteEnviada:
    return carta_frete.enviar_agora(db, dict(DADOS), enviar=correio, **etapas)


def test_correcao_sai_na_mesma_conversa_da_autorizacao(db, etapas):
    correio = Correio()
    registro = enviada(db, correio, etapas)
    original = correio.enviados[0]
    assert registro.email_message_id == "<msg-1@atlanticofertlog.com.br>"

    carta_frete.corrigir_valor(db, registro.id, "1.500,00", motivo="frete acertado com o posto",
                               usuario="david@atlanticofertlog.com.br", enviar=correio, **etapas)

    correcao = correio.enviados[1]
    # É isso que faz o e-mail cair embaixo do primeiro, e não em conversa solta.
    assert correcao["responder_a"] == registro.email_message_id
    assert correcao["assunto"] == original["assunto"]
    assert "1.200,00" in correcao["corpo"] and "1.500,00" in correcao["corpo"]
    # O motivo e anotacao interna: o posto nao recebe a nossa justificativa.
    assert "frete acertado com o posto" not in correcao["corpo"]
    assert correcao["para"] == original["para"]


def test_correcao_fica_registrada_com_hora_motivo_e_quem_fez(db, etapas):
    correio = Correio()
    registro = enviada(db, correio, etapas)
    antes = datetime.utcnow()

    atualizado = carta_frete.corrigir_valor(db, registro.id, "1.500,00", motivo="valor errado na emissão",
                                            usuario="david@atlanticofertlog.com.br", enviar=correio, **etapas)

    assert atualizado.valor_frete == "1.500,00"
    correcao = atualizado.correcoes[0]
    assert (correcao.valor_anterior, correcao.valor_novo) == ("1.200,00", "1.500,00")
    assert correcao.motivo == "valor errado na emissão"
    assert correcao.criado_por == "david@atlanticofertlog.com.br"
    assert correcao.criado_em >= antes
    assert correcao.email_message_id == "<msg-2@atlanticofertlog.com.br>"


def test_motivo_e_opcional(db, etapas):
    correio = Correio()
    registro = enviada(db, correio, etapas)

    atualizado = carta_frete.corrigir_valor(db, registro.id, "900,00", enviar=correio, **etapas)

    assert atualizado.correcoes[0].motivo == ""


def test_o_documento_anexado_na_correcao_leva_o_valor_novo(db, etapas):
    """O anexo e o que o posto guarda: tem que sair com o valor corrigido."""
    correio = Correio()
    registro = enviada(db, correio, etapas)
    vistos = []

    def gerar(dados):
        vistos.append(dados["VALOR_FRETE"])
        return etapas["gerar"](dados)

    carta_frete.corrigir_valor(db, registro.id, "1.500,00", enviar=correio,
                               gerar=gerar, converter=etapas["converter"])

    assert vistos == ["1.500,00"]


def test_duas_correcoes_ficam_as_duas_na_lista(db, etapas):
    correio = Correio()
    registro = enviada(db, correio, etapas)

    carta_frete.corrigir_valor(db, registro.id, "1.500,00", enviar=correio, **etapas)
    atualizado = carta_frete.corrigir_valor(db, registro.id, "1.350,00", motivo="desconto", enviar=correio, **etapas)

    assert [(c.valor_anterior, c.valor_novo) for c in atualizado.correcoes] == [
        ("1.200,00", "1.500,00"), ("1.500,00", "1.350,00"),
    ]
    # A segunda correção também responde o e-mail original, não a primeira:
    # é a autorização que todo mundo tem na caixa de entrada.
    assert correio.enviados[2]["responder_a"] == registro.email_message_id


def test_valor_igual_e_autorizacao_nao_enviada_sao_recusados(db, etapas):
    correio = Correio()
    registro = enviada(db, correio, etapas)

    with pytest.raises(carta_frete.CartaFreteInvalida):
        carta_frete.corrigir_valor(db, registro.id, "1.200,00", enviar=correio, **etapas)
    with pytest.raises(carta_frete.CartaFreteInvalida):
        carta_frete.corrigir_valor(db, registro.id, "   ", enviar=correio, **etapas)

    agendada = carta_frete.agendar(db, dict(DADOS), datetime(2030, 1, 1))
    with pytest.raises(carta_frete.CartaFreteInvalida):
        carta_frete.corrigir_valor(db, agendada.id, "1.500,00", enviar=correio, **etapas)
    assert len(correio.enviados) == 1


def test_email_que_nao_sai_guarda_o_erro_e_nao_troca_o_valor(db, etapas):
    registro = enviada(db, Correio(), etapas)

    with pytest.raises(RuntimeError):
        carta_frete.corrigir_valor(db, registro.id, "1.500,00", enviar=Correio(falhar=True), **etapas)

    db.refresh(registro)
    # O valor so muda quando o posto fica sabendo: senao a tela diria uma
    # coisa e a caixa de entrada dele outra.
    assert registro.valor_frete == "1.200,00"
    assert registro.correcoes[0].erro == "SMTP fora do ar"


def test_autorizacao_antiga_sem_message_id_ainda_manda_a_correcao(db, etapas):
    """Autorização de antes deste registro: melhor a correção chegar fora da
    conversa do que não chegar."""
    correio = Correio()
    registro = enviada(db, correio, etapas)
    registro.email_message_id = ""
    db.commit()

    carta_frete.corrigir_valor(db, registro.id, "1.500,00", enviar=correio, **etapas)

    assert correio.enviados[1]["responder_a"] == ""


def test_envio_de_teste_vai_so_pro_endereco_de_teste(db, etapas):
    """Experimentar o fluxo nao pode cair na caixa do posto."""
    from app.config import settings

    correio = Correio()
    registro = carta_frete.enviar_agora(db, dict(DADOS), teste=True, enviar=correio, **etapas)

    assert correio.enviados[0]["para"] == [settings.email_teste_fabrica]
    assert correio.enviados[0]["assunto"].startswith("[TESTE] ")

    # A correcao de uma autorizacao de teste continua no teste, e na mesma conversa.
    carta_frete.corrigir_valor(db, registro.id, "1.500,00", motivo="conferindo", enviar=correio, **etapas)
    correcao = correio.enviados[1]
    assert correcao["para"] == [settings.email_teste_fabrica]
    assert correcao["assunto"] == correio.enviados[0]["assunto"]
    assert correcao["responder_a"] == registro.email_message_id


def test_envio_de_teste_nao_vira_fatura_a_pagar(db, etapas):
    """O teste fica na lista pra conferir que saiu, mas nao e dinheiro: se
    entrasse na previsao, a fatura do posto viria com valor inventado."""
    from datetime import date

    from app.models import CarregamentoFinanceiro, ContaBancaria, PagamentoFaturaAbastecimento
    from app.servicos import financeiro as fin

    sessao = banco_em_memoria(
        CartaFreteEnviada, CartaFreteCorrecao, ListaEmail,
        CarregamentoFinanceiro, ContaBancaria, PagamentoFaturaAbastecimento,
    )
    correio = Correio()
    carta_frete.enviar_agora(sessao, dict(DADOS), teste=True, enviar=correio, **etapas)
    carta_frete.enviar_agora(sessao, {**DADOS, "CONDUTOR": "DE VERDADE"}, enviar=correio, **etapas)

    previsao = fin.previsao_faturas_abastecimento(sessao, "2026-10", hoje=date(2026, 10, 22))

    assert [i["motorista"] for i in previsao["itens"]] == ["DE VERDADE"]
    sessao.close()
