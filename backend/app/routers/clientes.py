from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Cliente

router = APIRouter(prefix="/clientes", tags=["clientes"], dependencies=[Depends(get_current_user)])


class ClienteIn(BaseModel):
    nome: str
    cnpj_cpf: str = ""
    cidade: str = ""
    uf: str = ""
    contato: str = ""
    email: str = ""
    telefone: str = ""
    observacoes: str = ""


def _to_dict(c: Cliente) -> dict:
    return {
        "id": c.id,
        "nome": c.nome,
        "cnpj_cpf": c.cnpj_cpf,
        "cidade": c.cidade,
        "uf": c.uf,
        "contato": c.contato,
        "email": c.email,
        "telefone": c.telefone,
        "observacoes": c.observacoes,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


@router.get("")
def listar_clientes(busca: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Cliente)
    if busca:
        query = query.filter(Cliente.nome.ilike(f"%{busca}%"))
    clientes = query.order_by(Cliente.nome.asc()).all()
    return [_to_dict(c) for c in clientes]


@router.post("")
def criar_cliente(payload: ClienteIn, db: Session = Depends(get_db)):
    cliente = Cliente(**payload.model_dump())
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return _to_dict(cliente)


@router.get("/{cliente_id}")
def obter_cliente(cliente_id: int, db: Session = Depends(get_db)):
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    return _to_dict(cliente)


@router.put("/{cliente_id}")
def atualizar_cliente(cliente_id: int, payload: ClienteIn, db: Session = Depends(get_db)):
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    for field, value in payload.model_dump().items():
        setattr(cliente, field, value)
    db.commit()
    db.refresh(cliente)
    return _to_dict(cliente)


@router.delete("/{cliente_id}")
def remover_cliente(cliente_id: int, db: Session = Depends(get_db)):
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    db.delete(cliente)
    db.commit()
    return {"ok": True}
