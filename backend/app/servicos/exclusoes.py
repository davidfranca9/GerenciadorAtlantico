"""Registro do que foi apagado, pra ninguem ficar sem resposta depois."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models import RegistroExclusao

logger = logging.getLogger(__name__)


def _simples(valor):
    """Deixa o valor gravavel em JSON sem perder o que importa."""
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, bytes):
        return f"<{len(valor)} bytes>"
    return valor


def anotar(db: Session, objeto, *, descricao: str, usuario: str = "") -> Optional[RegistroExclusao]:
    """Guarda a linha inteira antes de ela ser apagada.

    Chame ANTES do db.delete: depois os campos ja foram embora.

    Falha aqui nao derruba a exclusao. O registro existe pra ajudar; se ele
    quebrar (tabela que ainda nao subiu, campo estranho), o pior cenario e
    ficar sem o rastro daquela linha - impedir todo mundo de apagar seria
    pior que o problema que ele resolve. A falha vai pro log.
    """
    try:
        campos = {
            coluna.name: _simples(getattr(objeto, coluna.name, None))
            for coluna in objeto.__table__.columns
        }
        registro = RegistroExclusao(
            tabela=objeto.__tablename__,
            registro_id=int(getattr(objeto, "id", 0) or 0),
            descricao=(descricao or "").strip()[:300],
            dados=json.dumps(campos, ensure_ascii=False, default=str),
            usuario=usuario or "",
        )
        db.add(registro)
        db.flush()
        return registro
    except Exception:
        logger.exception("Nao consegui registrar a exclusao de %s", getattr(objeto, "__tablename__", "?"))
        return None


def listar(db: Session, *, limite: int = 100, tabela: str = "") -> list[dict]:
    consulta = db.query(RegistroExclusao).order_by(RegistroExclusao.criado_em.desc())
    if tabela:
        consulta = consulta.filter(RegistroExclusao.tabela == tabela)
    return [
        {
            "id": r.id, "tabela": r.tabela, "registro_id": r.registro_id,
            "descricao": r.descricao, "usuario": r.usuario,
            "quando": r.criado_em.isoformat() if r.criado_em else None,
            "dados": r.dados,
        }
        for r in consulta.limit(max(1, min(limite, 500))).all()
    ]
