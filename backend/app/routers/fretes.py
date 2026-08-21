from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import CotacaoFrete

router = APIRouter(prefix="/cotacoes-frete", tags=["analise-fretes"], dependencies=[Depends(get_current_user)])


class CotacaoIn(BaseModel):
    data_cotacao: str
    destino: str
    valor_tonelada: float
    cliente_id: Optional[int] = None
    cliente_nome: str = ""
    observacoes: str = ""


def _to_dict(c: CotacaoFrete) -> dict:
    return {
        "id": c.id,
        "data_cotacao": c.data_cotacao,
        "destino": c.destino,
        "valor_tonelada": c.valor_tonelada,
        "cliente_id": c.cliente_id,
        "cliente_nome": c.cliente_nome,
        "observacoes": c.observacoes,
        "created_at": c.created_at,
    }


@router.get("")
def listar_cotacoes(destino: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(CotacaoFrete)
    if destino:
        query = query.filter(CotacaoFrete.destino.ilike(f"%{destino}%"))
    cotacoes = query.order_by(CotacaoFrete.data_cotacao.desc()).all()
    return [_to_dict(c) for c in cotacoes]


@router.post("")
def cadastrar_cotacao(payload: CotacaoIn, db: Session = Depends(get_db)):
    cotacao = CotacaoFrete(**payload.model_dump(), created_at=datetime.utcnow())
    db.add(cotacao)
    db.commit()
    db.refresh(cotacao)
    return _to_dict(cotacao)


@router.get("/ultima")
def ultima_cotacao(destino: str, db: Session = Depends(get_db)):
    cotacao = (
        db.query(CotacaoFrete)
        .filter(CotacaoFrete.destino.ilike(f"%{destino}%"))
        .order_by(CotacaoFrete.data_cotacao.desc())
        .first()
    )
    return _to_dict(cotacao) if cotacao else None
