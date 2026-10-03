from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import exigir_tela
from ..servicos import buonny

# A consulta Buonny (checagem do motorista e da carga) nao tem aba propria no
# menu: /buonny e uma tela de apoio aberta pelo endereco, no meio do cadastro
# do motorista e da emissao dos documentos da carga. Por isso vale pelas abas
# desse trabalho - fechar pra uma so tiraria a consulta de quem usa.
router = APIRouter(
    prefix="/buonny",
    tags=["buonny"],
    dependencies=[Depends(exigir_tela("/bsoft", "/ordem-coleta", "/agendamentos", "/contrato"))],
)


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
