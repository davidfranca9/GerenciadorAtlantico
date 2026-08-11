"""Integracao com a Buonny (seguro/checagem de carga).

Portado de gerenciador_atlantico/mixins/buonny.py. Apenas o login e os
mapas de tipo/valor de carga eram funcionalidade real no app legado; a
consulta em si nunca foi implementada la (metodos ausentes no codigo
original). Aqui o endpoint de consulta segue o mesmo padrao de URL visto
nos headers da sessao original — pode precisar de ajuste caso a Buonny
mude o endpoint real usado pelo formulario web deles.
"""
from __future__ import annotations

import uuid

import requests

LOGIN_URL = "https://informacoes.buonny.com.br/informacoes2/usuarios/login"
CONSULTA_URL = "https://informacoes.buonny.com.br/informacoes2/consulta/consultar"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://informacoes.buonny.com.br",
    "Referer": CONSULTA_URL,
}

CARGA_TIPO_MAP = {
    "AÇO": "32", "AÇUCAR": "18", "AÇÚCAR": "102", "ALGODÃO": "44", "ALGODÃO EM PLUMA": "20", "ALUMÍNIO": "4",
    "AMIDO": "65", "ARROZ": "8", "AUTOPEÇAS": "45", "AVEIA": "70", "BACIAS": "63", "BEBIDAS": "5",
    "BICABORNATO DE SÓDIO": "29", "BOBINAS": "19", "BOBINAS DE AÇO": "11", "CAFÉ": "14", "CALCÁRIO": "73",
    "CALCÍTICO": "72", "CANOLA": "64", "CARGA FRACIONADA": "41", "CARGAS DIVERSAS": "67", "CEVADA": "76",
    "CHAPAS DE AÇO": "22", "CHAPAS DE MDF": "37", "CIGARROS": "12", "CIMENTO": "39", "COBRE": "7",
    "CONCENTRADO APATÍTICO ÚMIDO": "103", "COPOLÍMERO": "52", "COURO": "43", "DEFENSIVOS AGRÍCOLAS": "71",
    "DIVERSOS": "3", "DORMENTE": "53", "DTI DIÓXIDO DE TITANIO": "54", "ELETRO\\ELETRÔNICOS": "6",
    "FARELO": "62", "FERRO": "33", "FERTILIZANTE UREIA": "97", "FERTILIZANTES CLORETO DE POTÁSSIO": "100",
    "FERTILIZANTES E ADUBOS": "77", "FERTILIZANTES PREMIUM YARA": "95", "FERTILIZANTES TIPO MAP": "98",
    "FERTILIZANTES TIPO TSP\\SUPERFOSFATO\\FOSFATO": "99", "FOSFATO": "74", "GESSO AGRÍCOLA": "106",
    "LAMINADOS": "38", "LEITE": "21", "MAGNETITA": "107", "MÁQUINAS EM GERAL": "28", "MEDICAMENTOS": "13",
    "MILHO": "75", "NIQUEL": "55", "ÓLEO DE SOJA": "24", "OUTROS": "42", "PAPEL": "10",
    "PLACAS FOTOVOLTAICAS": "60", "PNEUS": "46", "POLIETILENO": "26", "POLIPROPILENO": "56",
}

CARGA_VALOR_MAP = {
    "De R$ 0,01 a R$ 100.000,00": "1",
    "De R$ 100.001,00 a R$ 200.000,00": "2",
    "De R$ 200.001,00 a R$ 300.000,00": "3",
    "De R$ 300.001,00 a R$ 400.000,00": "4",
    "De R$ 400.001,00 a R$ 500.000,00": "5",
    "De R$ 500.001,00 a R$ 800.000,00": "6",
    "De R$ 800.001,00 a R$ 1.000.000,00": "7",
    "De R$ 1.000.001,00 a R$ 3.000.000,00": "8",
    "De R$ 3.000.001,00 a R$ 1.000.000.000,00": "9",
}

# sessoes ativas em memoria: session_id -> requests.Session autenticada
_SESSIONS: dict[str, requests.Session] = {}


class BuonnyError(Exception):
    pass


def login(username: str, password: str) -> str:
    session = requests.Session()
    session.headers.update(HEADERS)
    payload = {"data[Usuario][apelido]": username, "data[Usuario][senha]": password}
    try:
        resp = session.post(LOGIN_URL, data=payload, timeout=15)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise BuonnyError(f"Erro de conexao: {exc}")

    texto = resp.text.lower()
    if "login" in texto or "usuário ou senha" in texto or "usuario ou senha" in texto:
        raise BuonnyError("Usuario ou senha invalidos")

    session_id = str(uuid.uuid4())
    _SESSIONS[session_id] = session
    return session_id


def _get_session(session_id: str) -> requests.Session:
    session = _SESSIONS.get(session_id)
    if session is None:
        raise BuonnyError("Sessao Buonny expirada ou invalida, faca login novamente")
    return session


def consultar(session_id: str, dados: dict) -> dict:
    session = _get_session(session_id)
    tipo_id = CARGA_TIPO_MAP.get(dados.get("carga_tipo", ""))
    valor_id = CARGA_VALOR_MAP.get(dados.get("carga_valor", ""))
    payload = {
        "data[Ficha][codigo_produto]": "2",
        "data[cliente][codigo]": dados.get("codigo", ""),
        "data[Ficha][codigo_cliente_transportador]": dados.get("codigo", ""),
        "data[Profissional][codigo_documento]": dados.get("cpf", ""),
        "data[profissional][nome]": dados.get("nome", ""),
        "data[veiculo][placa]": dados.get("placa_veiculo", ""),
        "data[carreta][placa]": dados.get("placa_carreta", ""),
        "data[Consulta][codigo_carga_tipo]": tipo_id,
        "data[Consulta][codigo_carga_valor]": valor_id,
        "data[Consulta][descricao_endereco_cidade_carga_origem]": dados.get("origem_cidade", ""),
        "data[Consulta][abreviacao_endereco_estado_carga_origem]": dados.get("origem_estado", ""),
        "data[Consulta][descricao_endereco_cidade_carga_destino]": dados.get("destino_cidade", ""),
        "data[Consulta][abreviacao_endereco_estado_carga_destino]": dados.get("destino_estado", ""),
    }
    try:
        resp = session.post(CONSULTA_URL, data=payload, timeout=20)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise BuonnyError(f"Erro de conexao na consulta: {exc}")

    try:
        return resp.json()
    except ValueError:
        return {"raw_response": resp.text}
