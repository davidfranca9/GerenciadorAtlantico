from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..auth import GRUPOS_TELAS, TELAS_LIBERAVEIS, hash_password, require_admin, telas_do_texto
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
    # Lista de permissao: as telas que esse usuario PODE ver, separadas por
    # virgula. A lista negra antiga (paginas_bloqueadas) saiu daqui de proposito
    # - duas formas de escrever a mesma permissao dao briga silenciosa.
    paginas_liberadas: str | None = None


class SenhaIn(BaseModel):
    password: str


def _telas_para_gravar(texto: str | None) -> str:
    """Aceita so rota que existe e que pode ser marcada (auth.GRUPOS_TELAS).

    Tela digitada errada, ou tela que e so de administrador, viram erro na cara
    do dono em vez de uma permissao que nao faz nada - ou que faz demais."""
    pedidas = [pedaco.strip() for pedaco in (texto or "").split(",") if pedaco.strip()]
    desconhecidas = [rota for rota in pedidas if rota not in TELAS_LIBERAVEIS]
    if desconhecidas:
        raise HTTPException(status_code=400, detail=f"Tela desconhecida: {', '.join(desconhecidas)}")
    return ",".join(telas_do_texto(texto))


def _to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "role": u.role,
        "is_active": u.is_active,
        "paginas_liberadas": u.paginas_liberadas or "",
        "created_at": u.created_at,
    }


@router.get("/telas")
def listar_telas():
    """As abas do sistema, nos grupos da barra lateral, pra tela de
    Administracao montar as caixinhas. Vem do backend porque e a MESMA lista
    que decide o acesso: aba nova aparece aqui sozinha."""
    return {"grupos": [{"titulo": g["titulo"], "telas": list(g["telas"])} for g in GRUPOS_TELAS]}


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


@router.post("/{user_id}/senha")
def trocar_senha(user_id: int, payload: SenhaIn, db: Session = Depends(get_db)):
    """Administrador define uma senha nova pra alguem que perdeu a dele.

    Nao pede a senha atual de proposito: quem esqueceu nao tem como informar,
    e era por isso que o usuario ficava de fora ate alguem mexer no banco. A
    senha nova nao e devolvida nem registrada em log - ela vai pra pessoa pelo
    canal que o administrador escolher.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="A senha deve ter ao menos 8 caracteres")
    user.hashed_password = hash_password(payload.password)
    db.commit()
    return {"ok": True, "email": user.email}


@router.patch("/{user_id}")
def atualizar_usuario(user_id: int, payload: UsuarioUpdateIn, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    updates = payload.model_dump(exclude_unset=True)
    if "role" in updates and updates["role"] not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Papel invalido, use 'user' ou 'admin'")
    if "paginas_liberadas" in updates:
        updates["paginas_liberadas"] = _telas_para_gravar(updates["paginas_liberadas"])
    for field, value in updates.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return _to_dict(user)
