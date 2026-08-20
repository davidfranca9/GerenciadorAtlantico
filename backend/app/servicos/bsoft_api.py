"""Cliente da API Bsoft TMS.

Portado de gerenciador_atlantico/servicos/bsoft_api.py sem a dependencia de
tkinter: erros agora levantam BsoftApiError em vez de abrir messagebox.
"""
from __future__ import annotations

import json

import requests

from ..config import settings

BASE_URL = "https://atlanticofertlog.bsoft.app/services/index.php"


class BsoftApiError(Exception):
    pass


def _auth():
    return (settings.bsoft_api_user, settings.bsoft_api_password)


def _clean(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if v is not None and v != ""}


def cadastrar_veiculo_bsoft(dados_veiculo: dict) -> dict:
    endpoint_url = f"{BASE_URL}/transporte/v1/veiculos"
    temp_payload = {
        "placa": dados_veiculo.get("placa"),
        "renavam": dados_veiculo.get("renavam"),
        "rntrc": dados_veiculo.get("rntrc"),
        "tara": dados_veiculo.get("tara"),
        "capacidadeCarga": dados_veiculo.get("capacidadeCarga"),
        "capM3": dados_veiculo.get("capM3"),
        "modeloVeiculo": dados_veiculo.get("modeloVeiculo"),
        "quantidadeEixos": dados_veiculo.get("quantidadeEixos"),
        "marcaVeiculo": dados_veiculo.get("marcaVeiculo"),
        "categoriaVeiculo": dados_veiculo.get("categoriaVeiculo"),
        "grupoVeiculo": dados_veiculo.get("grupoVeiculo"),
        "tipoRodado": dados_veiculo.get("tipoRodado"),
        "tipoCarroceria": dados_veiculo.get("tipoCarroceria"),
        "tipoEquipamento": dados_veiculo.get("tipoEquipamento"),
        "motoristaEhProprietario": "S" if dados_veiculo.get("motoristaEhProprietario") else "N",
        "estado": dados_veiculo.get("estado"),
        "cidade": dados_veiculo.get("cidade"),
        "proprietarioId": dados_veiculo.get("proprietario_id"),
        "motoristaId": dados_veiculo.get("motoristaId"),
        "arrendatarioId": dados_veiculo.get("arrendatarioId"),
    }
    if not dados_veiculo.get("motoristaEhProprietario"):
        temp_payload["motorista"] = dados_veiculo.get("motorista_documento")

    resp = requests.post(endpoint_url, json=_clean(temp_payload), auth=_auth(), timeout=30)
    if resp.status_code in (200, 201):
        return resp.json()
    raise BsoftApiError(f"Falha ao cadastrar veiculo (status {resp.status_code}): {resp.text}")


def cadastrar_endereco_bsoft(cod_pessoa, dados_endereco: dict) -> dict | None:
    if not cod_pessoa or not dados_endereco.get("logradouro"):
        return None
    endpoint_url = f"{BASE_URL}/pessoas/v1/pessoas/{cod_pessoa}/enderecos"
    payload = dict(dados_endereco)
    payload["codPessoa"] = str(cod_pessoa)
    resp = requests.post(endpoint_url, json=_clean(payload), auth=_auth(), timeout=20)
    if resp.status_code in (200, 201):
        return resp.json()
    raise BsoftApiError(f"Falha ao cadastrar endereco (status {resp.status_code}): {resp.text}")


def _payload_pessoa_fisica(dados_motorista: dict, cpf_override=None) -> dict:
    partes_nome = dados_motorista.get("nome", "").split(" ", 1)
    return {
        "dependentesIRRF": 0,
        "cpf": cpf_override or dados_motorista.get("cpf"),
        "nome": partes_nome[0],
        "sobrenome": partes_nome[1] if len(partes_nome) > 1 else "",
        "dtNascimento": dados_motorista.get("dtNascimento"),
        "tipoTransportadora": "T",
        "RNTRC": dados_motorista.get("rntrc"),
        "celular": dados_motorista.get("fone"),
        "grupos": ["motoristas", "proprietariosVeiculos"] if dados_motorista.get("is_owner") else ["motoristas"],
        "cnh": {k: v for k, v in dados_motorista.get("cnh", {}).items() if v},
    }


def cadastrar_pessoa_fisica_bsoft(dados_motorista: dict) -> dict:
    endpoint_url = f"{BASE_URL}/pessoas/v1/pessoas/fisicas"
    resp = requests.post(endpoint_url, json=_payload_pessoa_fisica(dados_motorista), auth=_auth(), timeout=20)
    if resp.status_code in (200, 201):
        return resp.json()
    raise BsoftApiError(f"Falha ao cadastrar motorista (status {resp.status_code}): {resp.text}")


def atualizar_pessoa_fisica_bsoft(cpf: str, dados_motorista: dict) -> dict:
    endpoint_url = f"{BASE_URL}/pessoas/v1/pessoas/fisicas/{cpf}"
    resp = requests.put(endpoint_url, json=_payload_pessoa_fisica(dados_motorista, cpf_override=cpf), auth=_auth(), timeout=20)
    if resp.status_code == 200:
        return resp.json()
    raise BsoftApiError(f"Falha ao atualizar motorista (status {resp.status_code}): {resp.text}")


def _payload_pessoa_juridica(cnpj, dados_empresa: dict) -> dict:
    return _clean(
        {
            "cnpj": cnpj,
            "razaoSocial": dados_empresa.get("razao_social"),
            "nomeFantasia": dados_empresa.get("razao_social"),
            "tipoTransportadora": dados_empresa.get("tipoTransportadora"),
            "RNTRC": dados_empresa.get("rntrc"),
            "inscricaoEstadual": dados_empresa.get("inscricao_estadual"),
            "grupos": ["proprietariosVeiculos"],
        }
    )


def cadastrar_pessoa_juridica_bsoft(dados_empresa: dict) -> dict:
    endpoint_url = f"{BASE_URL}/pessoas/v1/pessoas/juridicas"
    resp = requests.post(endpoint_url, json=_payload_pessoa_juridica(dados_empresa.get("cnpj"), dados_empresa), auth=_auth(), timeout=20)
    if resp.status_code in (200, 201):
        return resp.json()
    raise BsoftApiError(f"Falha ao cadastrar proprietario PJ (status {resp.status_code}): {resp.text}")


def atualizar_pessoa_juridica_bsoft(cnpj: str, dados_empresa: dict) -> dict:
    endpoint_url = f"{BASE_URL}/pessoas/v1/pessoas/juridicas/{cnpj}"
    resp = requests.put(endpoint_url, json=_payload_pessoa_juridica(cnpj, dados_empresa), auth=_auth(), timeout=20)
    if resp.status_code == 200:
        return resp.json()
    raise BsoftApiError(f"Falha ao atualizar proprietario PJ (status {resp.status_code}): {resp.text}")


def buscar_pessoa_fisica_por_cpf(cpf: str) -> str | None:
    if not cpf:
        return None
    url = f"{BASE_URL}/pessoas/v1/pessoas/fisicas/{cpf}"
    try:
        resp = requests.get(url, auth=_auth(), timeout=20)
        if resp.status_code == 200 and resp.text and resp.json():
            return resp.json()[0].get("id")
    except requests.exceptions.RequestException:
        return None
    return None


def buscar_pessoa_juridica_por_cnpj(cnpj: str) -> str | None:
    if not cnpj:
        return None
    url = f"{BASE_URL}/pessoas/v1/pessoas/juridicas/{cnpj}"
    try:
        resp = requests.get(url, auth=_auth(), timeout=20)
        if resp.status_code == 200 and resp.text and resp.json():
            return resp.json()[0].get("id")
    except requests.exceptions.RequestException:
        return None
    return None


def consultar_cep(cep: str) -> dict:
    resp = requests.get(f"https://brasilapi.com.br/api/cep/v1/{cep}", timeout=10)
    if resp.status_code == 404:
        raise BsoftApiError(f"O CEP '{cep}' nao foi encontrado.")
    resp.raise_for_status()
    return resp.json()


def consultar_cnpj(cnpj: str) -> dict:
    resp = requests.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}", timeout=15)
    if resp.status_code == 404:
        raise BsoftApiError(f"O CNPJ '{cnpj}' nao foi encontrado.")
    resp.raise_for_status()
    return resp.json()
