from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..auth import hash_password, require_admin
from ..database import get_db
from ..models import User

router = APIRouter(prefix="/admin/usuarios", tags=["admin"], dependencies=[Depends(require_admin)])


class UsuarioIn(BaseModel):
    email: EmailStr
    password: str
    name: str = ""
    role: str = "user"


class UsuarioUpdateIn(BaseModel):
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    paginas_bloqueadas: str | None = None


def _to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "role": u.role,
        "is_active": u.is_active,
        "paginas_bloqueadas": u.paginas_bloqueadas,
        "created_at": u.created_at,
    }


@router.get("")
def listar_usuarios(db: Session = Depends(get_db)):
    return [_to_dict(u) for u in db.query(User).order_by(User.email.asc()).all()]


@router.post("")
def criar_usuario(payload: UsuarioIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Ja existe um usuario com esse email")
    if payload.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Papel invalido, use 'user' ou 'admin'")
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="A senha deve ter ao menos 8 caracteres")
    user = User(
        email=payload.email,
        name=payload.name or payload.email,
        role=payload.role,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_dict(user)


@router.patch("/{user_id}")
def atualizar_usuario(user_id: int, payload: UsuarioUpdateIn, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    updates = payload.model_dump(exclude_unset=True)
    if "role" in updates and updates["role"] not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Papel invalido, use 'user' ou 'admin'")
    for field, value in updates.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return _to_dict(user)
