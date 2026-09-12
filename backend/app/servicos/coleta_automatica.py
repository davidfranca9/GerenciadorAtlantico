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
from datetime import datetime

from ..config import settings
from ..database import SessionLocal
from ..models import EstadoSefaz
from . import notas_recebidas

logger = logging.getLogger(__name__)

# A varredura periodica e so rede de seguranca da escuta em tempo real.
INTERVALO_EMAIL_SEGUNDOS = 600
INTERVALO_SEFAZ_SEGUNDOS = 3600


async def _coletar_do_email() -> int:
    from . import email_inbox

    xmls = await asyncio.to_thread(email_inbox.anexos_xml_recentes, 3)
    with SessionLocal() as db:
        guardadas = [n for n in (notas_recebidas.guardar(db, x, "email") for x in xmls) if n]
    return len(guardadas)


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

    email_inbox.escutar_novas_mensagens(ao_chegar)


def iniciar() -> None:
    """Liga as coletas. So a da SEFAZ depende do certificado."""
    threading.Thread(target=_escutar_email_em_tempo_real, daemon=True).start()
    asyncio.create_task(_repetir("e-mail", _coletar_do_email, INTERVALO_EMAIL_SEGUNDOS))
    asyncio.create_task(_repetir("casamento", _casar_notas_soltas, INTERVALO_EMAIL_SEGUNDOS))
    if settings.certificado_pfx_path:
        asyncio.create_task(_repetir("SEFAZ", _coletar_da_sefaz, INTERVALO_SEFAZ_SEGUNDOS))
    else:
        logger.info("coleta SEFAZ desligada: certificado nao configurado")
