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
import re
import tempfile
from datetime import datetime
from pathlib import Path

from docx import Document
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..config import settings
from ..models import CartaFreteCorrecao, CartaFreteEnviada
from . import listas_email
from .comunicacao import send_email_message
from .documentos import fill_carta_frete_docx
from .pdf_convert import docx_to_pdf

logger = logging.getLogger(__name__)

DADOS_DIR = Path(__file__).resolve().parents[2] / "dados"
TEMPLATE_CF = DADOS_DIR / "CARTA FRETE atlantico (1).docx"

# Padrao: quem recebe de fato e a lista salva em Configuracoes (listas_email).
DESTINATARIOS = listas_email.LISTAS["abastecimento"]["padrao"]

CAMPOS = ("DATA", "CONDUTOR", "CPF", "PLACA_CAVALO", "VALOR_FRETE", "AUTORIZACAO_NUM")

CORPO = """
    <p>Prezados,</p>
    <p>Segue em anexo a Autorização de Abastecimento emitida.</p>
    <p>⚠️ <b>Lembrete importante:</b> Autorizar o abastecimento após recebimento da ordem encaminhada via e-mail.</p>
    <p>Por favor, confirme o recebimento. Em caso de dúvidas, estamos à disposição.</p>
"""


class CartaFreteInvalida(Exception):
    """Dados que impedem gerar ou agendar a autorizacao de abastecimento. A
    mensagem vai pra tela."""


def dados_de(payload: dict) -> dict:
    """So os campos do documento, sem espaco sobrando."""
    return {campo: str(payload.get(campo) or "").strip() for campo in CAMPOS}


def assunto(dados: dict) -> str:
    return f"AUTORIZAÇÃO ABASTECIMENTO: {dados['CONDUTOR']} - {dados['PLACA_CAVALO']}"


def nome_do_arquivo(dados: dict) -> str:
    """Nome do documento, sem extensao: o mesmo no download e no anexo do
    e-mail, no padrao que o sistema antigo usava. Antes o anexo do e-mail
    saia "carta_frete.pdf"."""
    condutor = re.sub(r'[\\/*?:"<>|]', "", str(dados.get("CONDUTOR") or "")).strip()
    return f"Autorizacao Abastecimento_{condutor or 'Motorista'}"


def _conferir_modelo() -> None:
    if not Path(TEMPLATE_CF).exists():
        raise CartaFreteInvalida("Modelo da Autorização de Abastecimento não encontrado")


def _validar_envio(dados: dict) -> None:
    _conferir_modelo()
    if not dados["CONDUTOR"]:
        raise CartaFreteInvalida("Nome do condutor é obrigatório")


def gerar_docx(dados: dict) -> str:
    """Preenche o modelo e devolve o caminho do .docx."""
    _conferir_modelo()
    doc = Document(str(TEMPLATE_CF))
    fill_carta_frete_docx(doc, dados)
    # O PDF herda este nome na conversao, e e ele que vai anexado no e-mail.
    caminho = os.path.join(tempfile.mkdtemp(), f"{nome_do_arquivo(dados)}.docx")
    doc.save(caminho)
    return caminho


def _assunto_teste(dados: dict, teste: bool) -> str:
    """[TESTE] no titulo, como nos outros e-mails da casa: quem recebe tem que
    saber na lista que aquilo nao e pra valer."""
    return f"[TESTE] {assunto(dados)}" if teste else assunto(dados)


def _mandar(dados: dict, destinatarios: list[str] | None = None, *, gerar=None, converter=None,
            enviar=None, corpo: str | None = None, responder_a: str = "",
            assunto_do_email: str | None = None) -> str:
    """Gera o PDF e manda; devolve o Message-ID. As tres etapas entram por
    parametro pra teste.

    `responder_a` faz a mensagem cair na mesma conversa de um envio anterior -
    e assim que a correcao chega embaixo da autorizacao que ela corrige."""
    gerar = gerar or gerar_docx
    converter = converter or docx_to_pdf
    enviar = enviar or send_email_message
    pdf = converter(gerar(dados))
    return enviar(destinatarios or DESTINATARIOS, assunto_do_email or assunto(dados), corpo or CORPO, [pdf],
                  responder_a=responder_a) or ""


def _destinatarios(db: Session, teste: bool = False) -> list[str]:
    """Em teste vai so pro endereco de teste: experimentar o fluxo nao pode
    cair na caixa do posto. O registro guarda pra quem foi, entao a correcao
    de uma autorizacao de teste tambem fica no teste."""
    if teste:
        return [settings.email_teste_fabrica]
    return listas_email.destinatarios(db, "abastecimento")


def _novo_registro(dados: dict, status: str, destinatarios: list[str] | None = None,
                   teste: bool = False) -> CartaFreteEnviada:
    return CartaFreteEnviada(
        data=dados["DATA"],
        condutor=dados["CONDUTOR"],
        cpf=dados["CPF"],
        placa_cavalo=dados["PLACA_CAVALO"],
        valor_frete=dados["VALOR_FRETE"],
        autorizacao_num=dados["AUTORIZACAO_NUM"],
        destinatarios=", ".join(destinatarios or DESTINATARIOS),
        status=status,
        teste=teste,
        dados=json.dumps(dados, ensure_ascii=False),
    )


def enviar_agora(db: Session, payload: dict, teste: bool = False, **etapas) -> CartaFreteEnviada:
    """Manda na hora. O registro fica na lista mesmo quando o envio falha."""
    dados = dados_de(payload)
    _validar_envio(dados)
    para = _destinatarios(db, teste)
    registro = _novo_registro(dados, "enviando", para, teste=teste)
    db.add(registro)
    db.commit()
    try:
        registro.email_message_id = _mandar(
            dados, para, assunto_do_email=_assunto_teste(dados, teste), **etapas
        )
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
    registro = _novo_registro(dados, "agendada", _destinatarios(db))
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
        raise CartaFreteInvalida(f"Essa autorização não está mais agendada (situação: {registro.status}).")
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
        # Vale a lista da hora do envio: se mudou depois de agendar, vai pra nova.
        para = _destinatarios(db)
        registro.destinatarios = ", ".join(para)
        try:
            _mandar(json.loads(registro.dados or "{}"), para, **etapas)
        except Exception as exc:
            registro.status = "erro"
            registro.erro = str(exc)[:500]
            logger.warning("autorizacao de abastecimento agendada %s nao foi enviada: %s", carta_id, str(exc)[:150])
        else:
            registro.status = "enviada"
            registro.enviada_em = datetime.utcnow()
            enviadas += 1
        db.commit()
    return enviadas


def _foi_teste(registro: CartaFreteEnviada) -> bool:
    """Autorizacao que saiu como teste tem a correcao tambem como teste. O
    endereco entra na conta pelos envios feitos antes da coluna existir."""
    return bool(getattr(registro, "teste", False)) or settings.email_teste_fabrica in (registro.destinatarios or "")


# O motivo NAO entra aqui: e anotacao interna, pra quem olha a tela depois
# saber por que o valor mudou. O posto precisa do valor novo, nao da nossa
# justificativa.
CORPO_CORRECAO = """
    <p>Prezados,</p>
    <p><b>Correção da autorização de abastecimento acima.</b></p>
    <p>O valor do frete passa de <b>{anterior}</b> para <b>{novo}</b>. Vale o documento em anexo,
    que substitui o anterior.</p>
    <p>Por favor, confirme o recebimento. Em caso de dúvidas, estamos à disposição.</p>
"""


def corrigir_valor(db: Session, carta_id: int, valor: str, motivo: str = "", usuario: str = "",
                   avisar: bool = True, **etapas) -> CartaFreteEnviada:
    """Troca o valor do frete de uma autorizacao ja enviada.

    O posto ja recebeu o valor antigo, entao duas coisas acontecem juntas: a
    correcao fica registrada (quem, quando e por que) e um e-mail novo sai NA
    MESMA CONVERSA do primeiro, pra quem recebeu ler o acerto logo abaixo da
    autorizacao errada - e nao num e-mail solto que ninguem liga ao outro.

    `avisar=False` corrige so o nosso registro, sem e-mail: as vezes o numero
    saiu errado aqui e o posto sempre teve o certo - nesse caso o aviso so
    confundiria quem recebe. A correcao fica registrada do mesmo jeito.
    """
    registro = db.get(CartaFreteEnviada, carta_id)
    if registro is None:
        raise LookupError(carta_id)
    if registro.status != "enviada":
        raise CartaFreteInvalida(
            f"So da pra corrigir autorizacao que ja foi enviada (situacao: {registro.status})."
        )
    novo = str(valor or "").strip()
    if not novo:
        raise CartaFreteInvalida("Informe o novo valor do frete.")
    anterior = registro.valor_frete or ""
    if novo == anterior:
        raise CartaFreteInvalida("O valor informado e o mesmo que ja esta na autorizacao.")

    try:
        dados = json.loads(registro.dados or "{}")
    except ValueError:
        dados = {}
    dados = {**dados, **{campo: getattr(registro, atributo) for campo, atributo in (
        ("DATA", "data"), ("CONDUTOR", "condutor"), ("CPF", "cpf"),
        ("PLACA_CAVALO", "placa_cavalo"), ("AUTORIZACAO_NUM", "autorizacao_num"),
    ) if not dados.get(campo)}}
    dados["VALOR_FRETE"] = novo

    motivo = (motivo or "").strip()[:300]
    correcao = CartaFreteCorrecao(
        carta_id=registro.id, valor_anterior=anterior, valor_novo=novo,
        motivo=motivo, criado_por=usuario or "",
    )
    db.add(correcao)
    corpo = CORPO_CORRECAO.format(anterior=anterior or "—", novo=novo)
    if not avisar:
        # So o nosso registro muda. A correcao fica guardada sem Message-ID,
        # que e como a tela sabe que ninguem foi avisado.
        registro.valor_frete = novo
        registro.dados = json.dumps(dados, ensure_ascii=False)
        db.commit()
        db.refresh(registro)
        return registro

    para = [d.strip() for d in (registro.destinatarios or "").split(",") if d.strip()] or _destinatarios(db)
    try:
        # Sem o Message-ID do original (autorizacao antiga, de antes deste
        # registro) o e-mail sai assim mesmo, em conversa propria: melhor
        # chegar fora da conversa do que nao chegar.
        correcao.email_message_id = _mandar(
            dados, para, corpo=corpo, responder_a=registro.email_message_id or "",
            assunto_do_email=_assunto_teste(dados, _foi_teste(registro)), **etapas
        )
    except Exception as exc:
        correcao.erro = str(exc)[:500]
        db.commit()
        raise

    registro.valor_frete = novo
    registro.dados = json.dumps(dados, ensure_ascii=False)
    db.commit()
    db.refresh(registro)
    return registro
