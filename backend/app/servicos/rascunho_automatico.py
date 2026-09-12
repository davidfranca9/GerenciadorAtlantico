"""Prepara o CT-e sozinho quando a nota chega e ja tem agendamento.

E a soma das pecas anteriores: a nota foi coletada (e-mail ou SEFAZ),
casou com o agendamento, a tarifa veio da ultima cotacao e a embalagem
do pedido. Com tudo isso em maos, o sistema monta o CT-e inteiro,
confere, e - se nada faltar - cria o RASCUNHO no Bsoft. Nunca o
definitivo: documento fiscal autorizado pela SEFAZ e decisao de gente.

Duas regras de seguranca que nao mudam:

  * uma tentativa por nota. O resultado fica gravado na propria nota
    (rascunho_resultado) e a tela mostra; tentar de novo e clique da
    pessoa, nao do sistema.
  * nunca depois de erro do Bsoft. A operacao registrada com falha e
    respeitada: pode ter criado do outro lado.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Agendamento, NotaFiscalRecebida
from . import cte_montagem, emissao_cte

logger = logging.getLogger(__name__)

# Mesmos padroes da tela: quem opera ajusta la se for diferente.
ALIQUOTA_PADRAO = "12"
EMBALAGEM_PADRAO = "BIG BAG"


def decidir(nota: NotaFiscalRecebida, sugestao: dict, operacao_anterior=None) -> str:
    """Diz por que NAO tentar; string vazia significa "pode". Puro."""
    if not settings.rascunho_automatico:
        return "rascunho automatico desligado"
    if nota.tem_cte:
        return "nota ja tem CT-e"
    if not nota.agendamento_id:
        return "nota sem agendamento"
    if nota.rascunho_resultado:
        return "ja tentou"
    if not (nota.xml or "").strip():
        return "nota sem XML (so o resumo)"
    if not sugestao.get("tarifa"):
        return f"sem tarifa: nenhuma cotacao registrada para {sugestao.get('destino') or 'o destino'}"
    if operacao_anterior is not None and (operacao_anterior.cod_conhecimento_bsoft or operacao_anterior.erro):
        return f"ja existe operacao #{operacao_anterior.id} ({operacao_anterior.status})"
    return ""


def tentar(db: Session, nota: NotaFiscalRecebida) -> str:
    """Uma tentativa. Grava e devolve o resultado, em texto de gente."""
    from ..routers.fiscal import sugerir_para_agendamento  # evita import circular

    agendamento = db.get(Agendamento, nota.agendamento_id) if nota.agendamento_id else None
    sugestao = sugerir_para_agendamento(db, agendamento) if agendamento else {}
    anterior = emissao_cte.operacao_existente(db, nota.agendamento_id, nota.chave) if agendamento else None

    motivo = decidir(nota, sugestao, anterior)
    if motivo:
        # So os motivos que dependem de dado gravam: os outros mudam sozinhos
        # (a cotacao pode ser cadastrada amanha) e valem nova tentativa.
        if motivo.startswith("ja existe operacao"):
            nota.rascunho_resultado = motivo[:300]
            db.commit()
        return motivo

    try:
        espelho = cte_montagem.derivar(
            nota.xml.encode(),
            tarifa_por_tonelada=sugestao["tarifa"],
            embalagem=sugestao.get("embalagem") or EMBALAGEM_PADRAO,
        )
        montado = emissao_cte.montar(
            espelho, agendamento,
            aliquota_icms=ALIQUOTA_PADRAO,
            rascunho=True,
        )
    except emissao_cte.FalhaCadastros as exc:
        logger.warning("rascunho automatico da nota %s: %s", nota.chave, str(exc)[:150])
        return str(exc)  # transitorio: nao grava, tenta no proximo ciclo
    except Exception as exc:
        resultado = f"nao deu pra montar: {str(exc)[:200]}"
        nota.rascunho_resultado = resultado[:300]
        db.commit()
        return resultado

    pendencias = espelho.get("pendencias", []) + montado["pendencias"]
    if pendencias:
        resultado = "faltou: " + "; ".join(pendencias)
        nota.rascunho_resultado = resultado[:300]
        db.commit()
        return resultado

    try:
        operacao = emissao_cte.emitir(
            db,
            corpo=montado["corpo"],
            chave=nota.chave,
            agendamento_id=agendamento.id,
            solicitado_por="automatico",
            rascunho=True,
        )
    except emissao_cte.JaEmitido as exc:
        resultado = str(exc)
    except Exception as exc:
        resultado = f"o Bsoft recusou: {str(exc)[:200]}"
    else:
        resultado = (
            f"rascunho {operacao.cod_conhecimento_bsoft} criado no Bsoft "
            f"(tarifa R$ {sugestao['tarifa']}/t, {espelho['especie'].get('nome') or 'especie da embalagem'})"
        )
        logger.info("rascunho automatico: nota %s -> %s", nota.chave, operacao.cod_conhecimento_bsoft)

    nota.rascunho_resultado = resultado[:300]
    db.commit()
    return resultado


def preparar_pendentes(db: Session, limite: int = 10) -> int:
    """Um ciclo: as notas casadas que ainda nao passaram por aqui."""
    if not settings.rascunho_automatico:
        return 0
    notas = (
        db.query(NotaFiscalRecebida)
        .filter(
            NotaFiscalRecebida.tem_cte.is_(False),
            NotaFiscalRecebida.agendamento_id.isnot(None),
            NotaFiscalRecebida.rascunho_resultado == "",
        )
        .order_by(NotaFiscalRecebida.id.asc())
        .limit(limite)
        .all()
    )
    criados = 0
    for nota in notas:
        if tentar(db, nota).startswith("rascunho "):
            criados += 1
    return criados
