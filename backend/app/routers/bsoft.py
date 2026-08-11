from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..servicos import bsoft_api
from ..servicos.bsoft_lookup import (
    BSOFT_CATEGORY_ID_TO_RODADO_ID_MAP,
    BSOFT_CATEGORIAS_VEICULO,
    BSOFT_CATEGORY_TO_EQUIPMENT_MAP,
    BSOFT_CATEGORY_TO_SIMPLE_BRANDS_MAP,
    BSOFT_GRUPOS_VEICULO,
    BSOFT_MARCA_ID_LOOKUP,
    BSOFT_SIMPLE_BRANDS_LIST,
    BSOFT_TIPOS_CARROCERIA_NOMES,
    BSOFT_TIPOS_EQUIPAMENTO,
    BSOFT_TIPOS_RODADO_NOMES,
)

router = APIRouter(prefix="/bsoft", tags=["bsoft"], dependencies=[Depends(get_current_user)])


@router.get("/lookups")
def obter_lookups():
    return {
        "categorias_veiculo": BSOFT_CATEGORIAS_VEICULO,
        "tipos_equipamento": BSOFT_TIPOS_EQUIPAMENTO,
        "grupos_veiculo": BSOFT_GRUPOS_VEICULO,
        "tipos_rodado": BSOFT_TIPOS_RODADO_NOMES,
        "tipos_carroceria": BSOFT_TIPOS_CARROCERIA_NOMES,
        "categoria_id_to_rodado_id": BSOFT_CATEGORY_ID_TO_RODADO_ID_MAP,
        "categoria_to_equipamento": BSOFT_CATEGORY_TO_EQUIPMENT_MAP,
        "categoria_to_marcas": BSOFT_CATEGORY_TO_SIMPLE_BRANDS_MAP,
        "marcas": BSOFT_SIMPLE_BRANDS_LIST,
        "marca_id_lookup": {f"{marca}|{categoria}": id_ for (marca, categoria), id_ in BSOFT_MARCA_ID_LOOKUP.items()},
    }


class VeiculoIn(BaseModel):
    placa: str = ""
    renavam: str = ""
    rntrc: str = ""
    tara: Optional[float] = None
    capacidadeCarga: Optional[float] = None
    capM3: Optional[float] = None
    modeloVeiculo: str = ""
    quantidadeEixos: Optional[int] = None
    marcaVeiculo: Optional[int] = None
    categoriaVeiculo: Optional[int] = None
    grupoVeiculo: Optional[int] = None
    tipoRodado: str = ""
    tipoCarroceria: str = ""
    tipoEquipamento: Optional[int] = None
    motoristaEhProprietario: bool = False
    estado: str = ""
    cidade: str = ""
    proprietario_id: Optional[str] = None
    motoristaId: Optional[str] = None
    arrendatarioId: Optional[str] = None
    motorista_documento: Optional[str] = None


class EnderecoIn(BaseModel):
    cod_pessoa: str
    logradouro: str = ""
    numero: str = ""
    bairro: str = ""
    cidade: str = ""
    estado: str = ""
    cep: str = ""


class PessoaFisicaIn(BaseModel):
    nome: str
    cpf: str
    dtNascimento: Optional[str] = None
    rntrc: Optional[str] = None
    fone: Optional[str] = None
    is_owner: bool = False
    cnh: dict = {}


class PessoaJuridicaIn(BaseModel):
    cnpj: str
    razao_social: str
    tipoTransportadora: Optional[str] = None
    rntrc: Optional[str] = None
    inscricao_estadual: Optional[str] = None


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except bsoft_api.BsoftApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/veiculos")
def cadastrar_veiculo(payload: VeiculoIn):
    return _wrap(bsoft_api.cadastrar_veiculo_bsoft, payload.model_dump())


@router.post("/enderecos")
def cadastrar_endereco(payload: EnderecoIn):
    dados = payload.model_dump(exclude={"cod_pessoa"})
    return _wrap(bsoft_api.cadastrar_endereco_bsoft, payload.cod_pessoa, dados)


@router.post("/pessoas/fisicas")
def cadastrar_pessoa_fisica(payload: PessoaFisicaIn):
    return _wrap(bsoft_api.cadastrar_pessoa_fisica_bsoft, payload.model_dump())


@router.put("/pessoas/fisicas/{cpf}")
def atualizar_pessoa_fisica(cpf: str, payload: PessoaFisicaIn):
    return _wrap(bsoft_api.atualizar_pessoa_fisica_bsoft, cpf, payload.model_dump())


@router.post("/pessoas/juridicas")
def cadastrar_pessoa_juridica(payload: PessoaJuridicaIn):
    return _wrap(bsoft_api.cadastrar_pessoa_juridica_bsoft, payload.model_dump())


@router.put("/pessoas/juridicas/{cnpj}")
def atualizar_pessoa_juridica(cnpj: str, payload: PessoaJuridicaIn):
    return _wrap(bsoft_api.atualizar_pessoa_juridica_bsoft, cnpj, payload.model_dump())
