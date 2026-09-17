from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..servicos import listas_email

router = APIRouter(prefix="/configuracoes", tags=["configuracoes"], dependencies=[Depends(require_admin)])


class ListaEmailIn(BaseModel):
    emails: list[str]


@router.get("/listas-email")
def listar_listas_email(db: Session = Depends(get_db)):
    """Pra quem vai cada e-mail do sistema."""
    return listas_email.listar(db)


@router.put("/listas-email/{chave}")
def salvar_lista_email(chave: str, payload: ListaEmailIn, db: Session = Depends(get_db), usuario=Depends(require_admin)):
    try:
        return listas_email.salvar(db, chave, payload.emails, getattr(usuario, "email", "") or "")
    except KeyError:
        raise HTTPException(status_code=404, detail="Lista de e-mail nao encontrada")
    except listas_email.ListaInvalida as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/listas-email/{chave}")
def restaurar_lista_email(chave: str, db: Session = Depends(get_db)):
    """Volta a lista pro padrao do sistema."""
    try:
        return listas_email.restaurar(db, chave)
    except KeyError:
        raise HTTPException(status_code=404, detail="Lista de e-mail nao encontrada")
