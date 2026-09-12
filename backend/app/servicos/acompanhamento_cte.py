"""Acompanha o CT-e depois de criado: virou autorizado? ficou rascunho?

Emitir era o fim da linha: ninguem olhava se a SEFAZ autorizou. O Bsoft
expoe o registro do CT-e, e o que ele diz e o que este modulo le, de
tempos em tempos, pra cada operacao ainda em aberto.

O que o resumo do Bsoft mostra (lido em documentos reais):

    rascunho     nro = "Rascunho", sem chaveAcesso
    autorizado   nro numerico, chaveAcesso com 44 digitos,
                 protocoloAverbacao, statusAverbacao = "S"
    em aberto    nro numerico, sem chaveAcesso

O resumo NAO traz o motivo de rejeicao da SEFAZ. Entao "em aberto" por
muito tempo e o sinal que existe: a operacao fica marcada pra alguem
conferir no Bsoft, em vez de fingir que sabe o que aconteceu.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import NotaFiscalRecebida, OperacaoFiscal
from . import bsoft_fiscal
from .bsoft_client import BsoftError

logger = logging.getLogger(__name__)

# Status que ainda merecem consulta. Autorizado, rejeitado e cancelado
# nao mudam mais sozinhos.
STATUS_EM_ABERTO = ("CTE_CRIADO", "CTE_PROCESSANDO", "ENVIANDO_CTE")

# Sem chave depois disso, e hora de alguem olhar no Bsoft.
DEMORA_SUSPEITA = timedelta(minutes=30)


def interpretar_resumo(dados: dict) -> dict:
    """Traduz o registro do Bsoft no que a operacao precisa saber. Puro."""
    nro = str(dados.get("nro") or "").strip()
    chave = re.sub(r"\D", "", str(dados.get("chaveAcesso") or ""))
    if nro.lower() == "rascunho":
        situacao = "rascunho"
    elif len(chave) == 44:
        situacao = "autorizado"
    elif nro:
        situacao = "em_aberto"
    else:
        situacao = "desconhecido"
    return {
        "situacao": situacao,
        "numero": nro if situacao != "rascunho" else "",
        "chave": chave if len(chave) == 44 else "",
        "protocolo": str(dados.get("protocoloAverbacao") or ""),
        "averbado": str(dados.get("statusAverbacao") or "").upper() == "S",
    }


def _aplicar(db: Session, operacao: OperacaoFiscal, lido: dict) -> str:
    """Grava o que foi lido e devolve o status novo."""
    antes = operacao.status
    if lido["numero"]:
        operacao.cte_numero = lido["numero"]
    if lido["chave"]:
        operacao.cte_chave = lido["chave"]
    if lido["protocolo"]:
        operacao.cte_protocolo = lido["protocolo"]

    if lido["situacao"] == "autorizado":
        operacao.status = "CTE_AUTORIZADO"
        operacao.erro = ""
        # A nota sai da fila com o numero definitivo.
        nota = db.query(NotaFiscalRecebida).filter(NotaFiscalRecebida.chave == operacao.chave_nfe).one_or_none()
        if nota is not None:
            nota.tem_cte = True
            nota.cte_numero = lido["numero"] or nota.cte_numero
    elif lido["situacao"] == "em_aberto":
        operacao.status = "CTE_PROCESSANDO"
        idade = datetime.utcnow() - (operacao.updated_at or operacao.created_at or datetime.utcnow())
        if idade > DEMORA_SUSPEITA and not operacao.erro:
            operacao.erro = (
                f"CT-e {lido['numero']} sem autorizacao ha {int(idade.total_seconds() // 60)} min: "
                "confira no Bsoft se a SEFAZ rejeitou."
            )
    # rascunho: continua CTE_CRIADO ate alguem emitir no Bsoft.

    if operacao.status != antes:
        logger.info("operacao %s: %s -> %s", operacao.id, antes, operacao.status)
    return operacao.status


def acompanhar(db: Session, limite: int = 50) -> dict:
    """LEITURA no Bsoft, escrita so no nosso banco. Um ciclo."""
    abertas = (
        db.query(OperacaoFiscal)
        .filter(OperacaoFiscal.status.in_(STATUS_EM_ABERTO), OperacaoFiscal.cod_conhecimento_bsoft != "")
        .order_by(OperacaoFiscal.updated_at.asc())
        .limit(limite)
        .all()
    )
    resultado = {"consultadas": 0, "autorizadas": 0, "em_aberto": 0, "rascunhos": 0, "falhas": 0}
    for operacao in abertas:
        try:
            dados = bsoft_fiscal.obter_conhecimento(operacao.cod_conhecimento_bsoft)
        except BsoftError as exc:
            resultado["falhas"] += 1
            logger.warning("acompanhamento do CT-e %s falhou: %s", operacao.cod_conhecimento_bsoft, str(exc)[:150])
            continue
        lido = interpretar_resumo(dados)
        resultado["consultadas"] += 1
        status = _aplicar(db, operacao, lido)
        if status == "CTE_AUTORIZADO":
            resultado["autorizadas"] += 1
        elif lido["situacao"] == "rascunho":
            resultado["rascunhos"] += 1
        else:
            resultado["em_aberto"] += 1
    db.commit()
    return resultado
