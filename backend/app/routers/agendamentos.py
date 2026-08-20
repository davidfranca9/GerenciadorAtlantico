from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import STATUS_AGENDAMENTO, Agendamento, AgendamentoItem

router = APIRouter(prefix="/agendamentos", tags=["agendamentos"], dependencies=[Depends(get_current_user)])


class AgendamentoItemIn(BaseModel):
    pedido: str = ""
    cliente: str = ""
    produto: str = ""
    cidade: str = ""
    embalagem: str = ""
    toneladas: float = 0


class AgendamentoIn(BaseModel):
    status: str = STATUS_AGENDAMENTO[0]
    supplier: str = ""
    loading_date: str = ""
    driver_name: str = ""
    driver_cpf: str = ""
    driver_phone: str = ""
    cnh: str = ""
    plate_cavalo: str = ""
    plate_carreta1: str = ""
    plate_carreta2: str = ""
    roteiro: str = ""
    localizador: str = ""
    contato_cliente: str = ""
    observacoes: str = ""
    itens: list[AgendamentoItemIn] = []


class AgendamentoStatusIn(BaseModel):
    status: str


def _to_dict(a: Agendamento) -> dict:
    return {
        "id": a.id,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
        "status": a.status,
        "supplier": a.supplier,
        "loading_date": a.loading_date,
        "driver_name": a.driver_name,
        "driver_cpf": a.driver_cpf,
        "driver_phone": a.driver_phone,
        "cnh": a.cnh,
        "plate_cavalo": a.plate_cavalo,
        "plate_carreta1": a.plate_carreta1,
        "plate_carreta2": a.plate_carreta2,
        "total_items": a.total_items,
        "total_tons": a.total_tons,
        "roteiro": a.roteiro,
        "localizador": a.localizador,
        "contato_cliente": a.contato_cliente,
        "observacoes": a.observacoes,
        "itens": [
            {
                "id": it.id,
                "pedido": it.pedido,
                "cliente": it.cliente,
                "produto": it.produto,
                "cidade": it.cidade,
                "embalagem": it.embalagem,
                "toneladas": it.toneladas,
            }
            for it in a.itens
        ],
    }


@router.get("")
def listar_agendamentos(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Agendamento)
    if status:
        query = query.filter(Agendamento.status == status)
    agendamentos = query.order_by(Agendamento.created_at.desc()).all()
    return [_to_dict(a) for a in agendamentos]


@router.post("")
def criar_agendamento(payload: AgendamentoIn, db: Session = Depends(get_db)):
    itens = payload.itens
    agendamento = Agendamento(
        **payload.model_dump(exclude={"itens"}),
        total_items=len(itens),
        total_tons=sum(i.toneladas for i in itens),
    )
    agendamento.itens = [AgendamentoItem(**i.model_dump()) for i in itens]
    db.add(agendamento)
    db.commit()
    db.refresh(agendamento)
    return _to_dict(agendamento)


@router.get("/{agendamento_id}")
def obter_agendamento(agendamento_id: int, db: Session = Depends(get_db)):
    agendamento = db.get(Agendamento, agendamento_id)
    if agendamento is None:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado")
    return _to_dict(agendamento)


@router.patch("/{agendamento_id}/status")
def atualizar_status(agendamento_id: int, payload: AgendamentoStatusIn, db: Session = Depends(get_db)):
    agendamento = db.get(Agendamento, agendamento_id)
    if agendamento is None:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado")
    if payload.status not in STATUS_AGENDAMENTO:
        raise HTTPException(status_code=400, detail=f"Status invalido. Use um de: {STATUS_AGENDAMENTO}")
    agendamento.status = payload.status
    agendamento.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(agendamento)
    return _to_dict(agendamento)
