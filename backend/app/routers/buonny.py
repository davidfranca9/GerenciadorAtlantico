from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..servicos import buonny

router = APIRouter(prefix="/buonny", tags=["buonny"], dependencies=[Depends(get_current_user)])


class LoginIn(BaseModel):
    username: str
    password: str


class ConsultaIn(BaseModel):
    session_id: str
    codigo: str = ""
    cpf: str = ""
    nome: str = ""
    placa_veiculo: str = ""
    placa_carreta: str = ""
    carga_tipo: str = ""
    carga_valor: str = ""
    origem_cidade: str = ""
    origem_estado: str = ""
    destino_cidade: str = ""
    destino_estado: str = ""


@router.get("/lookups")
def lookups():
    return {"carga_tipo": buonny.CARGA_TIPO_MAP, "carga_valor": buonny.CARGA_VALOR_MAP}


@router.post("/login")
def login(payload: LoginIn):
    try:
        session_id = buonny.login(payload.username, payload.password)
    except buonny.BuonnyError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    return {"session_id": session_id}


@router.post("/consultar")
def consultar(payload: ConsultaIn):
    try:
        return buonny.consultar(payload.session_id, payload.model_dump(exclude={"session_id"}))
    except buonny.BuonnyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
