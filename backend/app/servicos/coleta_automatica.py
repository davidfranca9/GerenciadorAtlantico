"""Busca as NF-e sozinho, de tempos em tempos.

Duas fontes, cadencias diferentes, pelo motivo de cada uma:

    e-mail  - a cada 10 minutos. Quando o fornecedor manda o anexo, a nota
              fica disponivel quase na hora.
    SEFAZ   - a cada hora. E o limite que a Receita impoe: consultar a
              esteira sem novidade responde "consumo indevido" e bloqueia
              por uma hora. Cobre justamente as fabricas que nao enviam.

Falha aqui nunca derruba o processo: a coleta e conveniencia, e a emissao
continua funcionando com o XML enviado a mao.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ..config import settings
from ..database import SessionLocal
from ..models import EstadoSefaz
from . import notas_recebidas

logger = logging.getLogger(__name__)

INTERVALO_EMAIL_SEGUNDOS = 600
INTERVALO_SEFAZ_SEGUNDOS = 3600


async def _coletar_do_email() -> int:
    from . import email_inbox

    xmls = await asyncio.to_thread(email_inbox.anexos_xml_recentes, 3)
    with SessionLocal() as db:
        guardadas = [n for n in (notas_recebidas.guardar(db, x, "email") for x in xmls) if n]
    return len(guardadas)


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


def iniciar() -> None:
    """Liga as duas coletas. So a da SEFAZ depende do certificado."""
    asyncio.create_task(_repetir("e-mail", _coletar_do_email, INTERVALO_EMAIL_SEGUNDOS))
    if settings.certificado_pfx_path:
        asyncio.create_task(_repetir("SEFAZ", _coletar_da_sefaz, INTERVALO_SEFAZ_SEGUNDOS))
    else:
        logger.info("coleta SEFAZ desligada: certificado nao configurado")
