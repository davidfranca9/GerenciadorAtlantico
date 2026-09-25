from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import engine, get_db
from ..servicos import listas_email, monitor

router = APIRouter(prefix="/configuracoes", tags=["configuracoes"], dependencies=[Depends(require_admin)])


@router.get("/diagnostico")
def diagnostico():
    """Como o servidor esta agora: memoria, carga, conexoes de banco e
    quanto cada rotina automatica demorou na ultima volta."""
    dados = monitor.estado()
    try:
        dados["banco"] = engine.pool.status()
    except Exception as exc:
        dados["banco"] = f"indisponivel: {exc}"[:200]
    return dados


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
