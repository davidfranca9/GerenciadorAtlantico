"""Busca as NF-e sozinho, de tempos em tempos.

Duas fontes, cadencias diferentes, pelo motivo de cada uma:

    e-mail  - em tempo real, por IMAP IDLE: o servidor avisa quando a
              mensagem chega, em vez de a gente perguntar. Uma varredura
              a cada 10 minutos fica de rede de seguranca, caso a escuta
              caia sem avisar.
    SEFAZ   - a cada hora. E o limite que a Receita impoe: consultar a
              esteira sem novidade responde "consumo indevido" e bloqueia
              por uma hora. Cobre justamente as fabricas que nao enviam.

Falha aqui nunca derruba o processo: a coleta e conveniencia, e a emissao
continua funcionando com o XML enviado a mao.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta

from ..config import settings
from ..database import SessionLocal
from ..models import EstadoSefaz
from . import notas_recebidas

logger = logging.getLogger(__name__)

# A varredura periodica e so rede de seguranca da escuta em tempo real.
INTERVALO_EMAIL_SEGUNDOS = 600
INTERVALO_SEFAZ_SEGUNDOS = 3600
# Depois de criado, o CT-e e consultado ate a SEFAZ responder.
INTERVALO_ACOMPANHAMENTO_SEGUNDOS = 300
# Carta frete agendada: confere a cada minuto se alguma chegou na hora.
INTERVALO_CARTAS_SEGUNDOS = 60
# Carregamentos do financeiro: CT-es novos do Bsoft entram sozinhos.
INTERVALO_CARREGAMENTOS_SEGUNDOS = 3600


async def _coletar_do_email() -> int:
    from . import email_inbox

    xmls = await asyncio.to_thread(email_inbox.anexos_xml_recentes, 3)
    with SessionLocal() as db:
        guardadas = [n for n in (notas_recebidas.guardar(db, x, "email") for x in xmls) if n]
    return len(guardadas)


async def _ler_respostas_da_fabrica() -> int:
    """Respostas da fabrica aos e-mails de agendamento: confirmacao vira
    Agendado; pergunta e problema so aparecem na tela."""
    from . import respostas_fabrica

    def ler() -> int:
        with SessionLocal() as db:
            return respostas_fabrica.ler_da_caixa(db, dias=3, aplicar=True)["lidas"]

    return await asyncio.to_thread(ler)


async def _casar_notas_soltas() -> int:
    """Tenta de novo o casamento das notas ainda sem agendamento.

    O agendamento pode ser criado depois da nota chegar - e o casamento
    feito na hora nao vale mais. Roda junto da varredura de e-mail.
    """
    from . import casamento

    with SessionLocal() as db:
        return await asyncio.to_thread(casamento.casar_pendentes, db)


async def _coletar_da_sefaz() -> int:
    from . import sefaz_nfe

    with SessionLocal() as db:
        estado = (
            db.query(EstadoSefaz)
            .filter(EstadoSefaz.cnpj == settings.certificado_cnpj)
            .one_or_none()
        )
        if estado is None:
            estado = EstadoSefaz(cnpj=settings.certificado_cnpj, ultimo_nsu="0")
            db.add(estado)
            db.commit()
        ponteiro = estado.ultimo_nsu

    resultado = await asyncio.to_thread(sefaz_nfe.sincronizar, ponteiro)

    with SessionLocal() as db:
        estado = (
            db.query(EstadoSefaz)
            .filter(EstadoSefaz.cnpj == settings.certificado_cnpj)
            .one_or_none()
        )
        if estado is not None:
            if resultado.get("ultimo_nsu"):
                estado.ultimo_nsu = resultado["ultimo_nsu"]
            if resultado.get("maximo_nsu"):
                estado.maximo_nsu = resultado["maximo_nsu"]
            estado.ultima_consulta = datetime.utcnow()
            estado.ultimo_status = f"{resultado.get('status')} {resultado.get('motivo')}"[:200]
            db.commit()

        guardadas = [
            n for n in (notas_recebidas.guardar(db, c["xml"], "sefaz")
                        for c in resultado["completas"]) if n
        ]
    return len(guardadas)


async def _preparar_rascunhos() -> int:
    """Nota casada + tarifa da cotacao -> rascunho no Bsoft, sem clique."""
    from . import rascunho_automatico

    with SessionLocal() as db:
        return await asyncio.to_thread(rascunho_automatico.preparar_pendentes, db)


async def _enviar_cartas_agendadas() -> int:
    """Manda as autorizacoes de abastecimento cujo horario agendado ja chegou."""
    from . import carta_frete

    with SessionLocal() as db:
        return await asyncio.to_thread(carta_frete.enviar_agendadas, db)


async def _acompanhar_ctes() -> int:
    """Pergunta ao Bsoft o que houve com cada CT-e ainda em aberto."""
    from . import acompanhamento_cte

    with SessionLocal() as db:
        resultado = await asyncio.to_thread(acompanhamento_cte.acompanhar, db)
    if resultado["consultadas"]:
        logger.info("acompanhamento de CT-e: %s", resultado)
    return resultado["autorizadas"]


async def _puxar_carregamentos() -> int:
    """Traz do Bsoft as cargas novas do mes (e do anterior nos primeiros dias,
    pro CT-e emitido na virada). So cria e atualiza carga que veio do Bsoft;
    nunca troca valor digitado ou da planilha."""
    from . import financeiro, financeiro_bsoft

    hoje = datetime.now().date()
    meses = [financeiro.competencia_de(hoje)]
    if hoje.day <= 5:
        meses.append(financeiro.competencia_de(hoje.replace(day=1) - timedelta(days=1)))
    novas = 0
    for competencia in meses:
        with SessionLocal() as db:
            resultado = await asyncio.to_thread(financeiro_bsoft.sincronizar, db, competencia, aplicar=True)
        novas += len(resultado["novos"])
        if resultado["novos"] or resultado["atualizados"]:
            logger.info("carregamentos %s: %s nova(s), %s atualizada(s)", competencia, len(resultado["novos"]), len(resultado["atualizados"]))
    return novas


async def _repetir(nome: str, tarefa, intervalo: int) -> None:
    """Roda a tarefa em intervalos, sem deixar erro parar o ciclo."""
    while True:
        try:
            quantidade = await tarefa()
            if quantidade:
                logger.info("coleta %s: %s nota(s) nova(s)", nome, quantidade)
        except Exception as exc:
            logger.warning("coleta %s falhou: %s", nome, str(exc)[:200])
        await asyncio.sleep(intervalo)


def _escutar_email_em_tempo_real() -> None:
    """Roda a escuta IDLE numa thread, fora do laco do servidor.

    A conexao em IDLE fica bloqueada esperando o aviso, entao nao pode
    dividir thread com o resto da aplicacao.
    """
    from . import email_inbox

    def ao_chegar():
        # A escuta so avisa QUE chegou algo; quem le os anexos e a coleta.
        try:
            asyncio.run(_coletar_do_email())
        except Exception as exc:
            logger.warning("coleta apos aviso de e-mail falhou: %s", str(exc)[:150])
        try:
            asyncio.run(_ler_respostas_da_fabrica())
        except Exception as exc:
            logger.warning("respostas da fabrica apos aviso de e-mail falharam: %s", str(exc)[:150])

    email_inbox.escutar_novas_mensagens(ao_chegar)


def iniciar() -> None:
    """Liga as coletas. So a da SEFAZ depende do certificado."""
    threading.Thread(target=_escutar_email_em_tempo_real, daemon=True).start()
    asyncio.create_task(_repetir("e-mail", _coletar_do_email, INTERVALO_EMAIL_SEGUNDOS))
    asyncio.create_task(_repetir("casamento", _casar_notas_soltas, INTERVALO_EMAIL_SEGUNDOS))
    asyncio.create_task(_repetir("respostas da fabrica", _ler_respostas_da_fabrica, INTERVALO_ACOMPANHAMENTO_SEGUNDOS))
    asyncio.create_task(_repetir("CT-e", _acompanhar_ctes, INTERVALO_ACOMPANHAMENTO_SEGUNDOS))
    asyncio.create_task(_repetir("autorizacoes de abastecimento", _enviar_cartas_agendadas, INTERVALO_CARTAS_SEGUNDOS))
    asyncio.create_task(_repetir("carregamentos do Bsoft", _puxar_carregamentos, INTERVALO_CARREGAMENTOS_SEGUNDOS))
    if settings.rascunho_automatico:
        asyncio.create_task(_repetir("rascunho", _preparar_rascunhos, INTERVALO_ACOMPANHAMENTO_SEGUNDOS))
    else:
        logger.info("rascunho automatico desligado (RASCUNHO_AUTOMATICO=false)")
    if settings.certificado_pfx_path:
        asyncio.create_task(_repetir("SEFAZ", _coletar_da_sefaz, INTERVALO_SEFAZ_SEGUNDOS))
    else:
        logger.info("coleta SEFAZ desligada: certificado nao configurado")
