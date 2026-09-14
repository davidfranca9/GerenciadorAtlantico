"""Carta frete (Autorizacao de Abastecimento): baixar, enviar agora ou agendar.

Tres caminhos pro mesmo documento:

    baixar   - gera o arquivo e devolve, sem mandar nada
    enviar   - gera e manda por e-mail na hora
    agendar  - guarda os dados e manda sozinho na hora marcada

O agendado guarda os DADOS, nao o arquivo: o documento e gerado no momento
do envio, entao sai com o modelo que estiver valendo naquele dia.

Duas regras do envio agendado:

  * sai uma vez so. Antes de mandar, a carta e reservada com um UPDATE
    condicional (so passa de "agendada" pra "enviando" quem ainda estiver
    "agendada"); com mais de um processo rodando a tarefa, so um ganha.
  * falha nao e repetida sozinha. O e-mail pode ter saido antes do erro,
    e mandar duas vezes uma autorizacao de abastecimento e pior do que
    avisar. A carta fica "erro" e a tela mostra.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from docx import Document
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models import CartaFreteEnviada
from .comunicacao import send_email_message
from .documentos import fill_carta_frete_docx
from .pdf_convert import docx_to_pdf

logger = logging.getLogger(__name__)

DADOS_DIR = Path(__file__).resolve().parents[2] / "dados"
TEMPLATE_CF = DADOS_DIR / "CARTA FRETE atlantico (1).docx"

DESTINATARIOS = [
    "davilucassouzaribeiro@gmail.com",
    "marvidacaixa503@gmail.com",
    "crispinianocrys@gmail.com",
]

CAMPOS = ("DATA", "CONDUTOR", "CPF", "PLACA_CAVALO", "VALOR_FRETE", "AUTORIZACAO_NUM")

CORPO = """
    <p>Prezados,</p>
    <p>Segue em anexo a Autorização de Abastecimento emitida.</p>
    <p>⚠️ <b>Lembrete importante:</b> Autorizar o abastecimento após recebimento da ordem encaminhada via e-mail.</p>
    <p>Por favor, confirme o recebimento. Em caso de dúvidas, estamos à disposição.</p>
"""


class CartaFreteInvalida(Exception):
    """Dados que impedem gerar ou agendar a carta. A mensagem vai pra tela."""


def dados_de(payload: dict) -> dict:
    """So os campos do documento, sem espaco sobrando."""
    return {campo: str(payload.get(campo) or "").strip() for campo in CAMPOS}


def assunto(dados: dict) -> str:
    return f"AUTORIZAÇÃO ABASTECIMENTO: {dados['CONDUTOR']} - {dados['PLACA_CAVALO']}"


def _conferir_modelo() -> None:
    if not Path(TEMPLATE_CF).exists():
        raise CartaFreteInvalida("Template de Carta Frete nao encontrado")


def _validar_envio(dados: dict) -> None:
    _conferir_modelo()
    if not dados["CONDUTOR"]:
        raise CartaFreteInvalida("Nome do condutor e obrigatorio")


def gerar_docx(dados: dict) -> str:
    """Preenche o modelo e devolve o caminho do .docx."""
    _conferir_modelo()
    doc = Document(str(TEMPLATE_CF))
    fill_carta_frete_docx(doc, dados)
    caminho = os.path.join(tempfile.mkdtemp(), "carta_frete.docx")
    doc.save(caminho)
    return caminho


def _mandar(dados: dict, *, gerar=None, converter=None, enviar=None) -> None:
    """Gera o PDF e manda. As tres etapas entram por parametro pra teste."""
    gerar = gerar or gerar_docx
    converter = converter or docx_to_pdf
    enviar = enviar or send_email_message
    pdf = converter(gerar(dados))
    enviar(DESTINATARIOS, assunto(dados), CORPO, [pdf])


def _novo_registro(dados: dict, status: str) -> CartaFreteEnviada:
    return CartaFreteEnviada(
        data=dados["DATA"],
        condutor=dados["CONDUTOR"],
        cpf=dados["CPF"],
        placa_cavalo=dados["PLACA_CAVALO"],
        valor_frete=dados["VALOR_FRETE"],
        autorizacao_num=dados["AUTORIZACAO_NUM"],
        destinatarios=", ".join(DESTINATARIOS),
        status=status,
        dados=json.dumps(dados, ensure_ascii=False),
    )


def enviar_agora(db: Session, payload: dict, **etapas) -> CartaFreteEnviada:
    """Manda na hora. O registro fica na lista mesmo quando o envio falha."""
    dados = dados_de(payload)
    _validar_envio(dados)
    registro = _novo_registro(dados, "enviando")
    db.add(registro)
    db.commit()
    try:
        _mandar(dados, **etapas)
    except Exception as exc:
        registro.status = "erro"
        registro.erro = str(exc)[:500]
        db.commit()
        raise
    registro.status = "enviada"
    registro.enviada_em = datetime.utcnow()
    db.commit()
    db.refresh(registro)
    return registro


def agendar(db: Session, payload: dict, quando: datetime, agora: datetime | None = None) -> CartaFreteEnviada:
    """Guarda a carta pra sair sozinha em `quando` (UTC, sem fuso)."""
    dados = dados_de(payload)
    _validar_envio(dados)
    if quando <= (agora or datetime.utcnow()):
        raise CartaFreteInvalida("Escolha um horario no futuro para agendar o envio.")
    registro = _novo_registro(dados, "agendada")
    registro.agendada_para = quando
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def cancelar(db: Session, carta_id: int) -> CartaFreteEnviada:
    """Cancela um envio agendado - so enquanto ele ainda nao saiu."""
    mudou = db.execute(
        update(CartaFreteEnviada)
        .where(CartaFreteEnviada.id == carta_id, CartaFreteEnviada.status == "agendada")
        .values(status="cancelada")
    ).rowcount
    db.commit()
    registro = db.get(CartaFreteEnviada, carta_id)
    if registro is None:
        raise LookupError(carta_id)
    db.refresh(registro)
    if not mudou:
        raise CartaFreteInvalida(f"Essa carta nao esta mais agendada (situacao: {registro.status}).")
    return registro


def enviar_agendadas(db: Session, agora: datetime | None = None, **etapas) -> int:
    """Um ciclo da tarefa periodica: manda o que ja passou da hora."""
    agora = agora or datetime.utcnow()
    vencidas = [
        carta_id for (carta_id,) in db.query(CartaFreteEnviada.id)
        .filter(CartaFreteEnviada.status == "agendada", CartaFreteEnviada.agendada_para <= agora)
        .order_by(CartaFreteEnviada.agendada_para.asc())
        .all()
    ]
    enviadas = 0
    for carta_id in vencidas:
        reservou = db.execute(
            update(CartaFreteEnviada)
            .where(CartaFreteEnviada.id == carta_id, CartaFreteEnviada.status == "agendada")
            .values(status="enviando")
        ).rowcount
        db.commit()
        if not reservou:
            continue  # outro processo pegou, ou cancelaram no meio do caminho

        registro = db.get(CartaFreteEnviada, carta_id)
        db.refresh(registro)
        try:
            _mandar(json.loads(registro.dados or "{}"), **etapas)
        except Exception as exc:
            registro.status = "erro"
            registro.erro = str(exc)[:500]
            logger.warning("carta frete agendada %s nao foi enviada: %s", carta_id, str(exc)[:150])
        else:
            registro.status = "enviada"
            registro.enviada_em = datetime.utcnow()
            enviadas += 1
        db.commit()
    return enviadas
