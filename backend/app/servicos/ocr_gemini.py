"""OCR de CNH/CRLV via Gemini (Google AI, tier gratuito).

Le a imagem/PDF do documento e pede pro modelo devolver os campos ja
estruturados em JSON, em vez de extrair texto cru e quebrar em pedacos
com regex (abordagem antiga, em ocr.py, que ficava fragil contra
variacoes de OCR ruidoso). Mantem exatamente os mesmos nomes de campo
que o pipeline antigo usava, para nao precisar mudar nada no resto do
sistema (frontend, importar-documentos do Bsoft etc.).
"""
from __future__ import annotations

import json
import os

from google import genai
from google.genai import types

from ..config import settings
from .bsoft_lookup import BSOFT_CATEGORIAS_VEICULO, BSOFT_SIMPLE_BRANDS_LIST, BSOFT_TIPOS_CARROCERIA_NOMES

MODELO = "gemini-3.6-flash"

CNH_SCHEMA = {
    "type": "object",
    "properties": {
        "nome": {"type": "string"},
        "cpf": {"type": "string", "description": "formato 000.000.000-00"},
        "numero": {"type": "string", "description": "numero de registro da CNH"},
        "seguro": {"type": "string", "description": "numero do seguro / cedula de identidade do condutor"},
        "categoria": {"type": "string", "description": "categoria da CNH, ex: A, B, AB, C, D, E, AE"},
        "protocolo": {"type": "string", "description": "numero do espelho/protocolo"},
        "dtValidade": {"type": "string", "description": "data no formato dd/mm/aaaa"},
        "dtExpedicao": {"type": "string", "description": "data de emissao no formato dd/mm/aaaa"},
        "dtPrimeiraExpedicao": {"type": "string", "description": "data da 1a habilitacao no formato dd/mm/aaaa"},
        "dtNascimento": {"type": "string", "description": "data de nascimento no formato dd/mm/aaaa"},
    },
    "required": ["nome", "cpf", "numero", "seguro", "categoria", "protocolo", "dtValidade", "dtExpedicao", "dtPrimeiraExpedicao", "dtNascimento"],
}

CRLV_SCHEMA = {
    "type": "object",
    "properties": {
        "placa": {"type": "string", "description": "formato ABC-1D23"},
        "renavam": {"type": "string"},
        "modelo": {"type": "string", "description": "modelo do veiculo, sem a marca"},
        "eixos": {"type": "string", "description": "quantidade de eixos"},
        "categoria_veiculo": {"type": "string", "enum": sorted(BSOFT_CATEGORIAS_VEICULO.keys())},
        "marca": {"type": "string", "enum": sorted(set(BSOFT_SIMPLE_BRANDS_LIST) | {""})},
        "tipo_carroceria": {"type": "string", "enum": sorted(set(BSOFT_TIPOS_CARROCERIA_NOMES.values()) | {""})},
        "estado": {"type": "string", "description": "sigla da UF, 2 letras"},
        "cidade": {"type": "string"},
    },
    "required": ["placa", "renavam", "modelo", "eixos", "categoria_veiculo", "marca", "tipo_carroceria", "estado", "cidade"],
}

_MIME_POR_EXTENSAO = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
}


class GeminiIndisponivel(Exception):
    pass


def _client() -> genai.Client:
    if not settings.gemini_api_key:
        raise GeminiIndisponivel("GEMINI_API_KEY nao configurada")
    return genai.Client(api_key=settings.gemini_api_key)


def _extrair_com_schema(caminho_arquivo: str, prompt: str, schema: dict) -> dict:
    client = _client()

    extensao = os.path.splitext(caminho_arquivo)[1].lower()
    mime_type = _MIME_POR_EXTENSAO.get(extensao, "image/jpeg")

    with open(caminho_arquivo, "rb") as f:
        dados_arquivo = f.read()
    resposta = client.models.generate_content(
        model=MODELO,
        contents=[
            types.Part.from_bytes(data=dados_arquivo, mime_type=mime_type),
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )
    return json.loads(resposta.text)


def extrair_dados_cnh_com_gemini(caminho_arquivo: str) -> dict:
    prompt = (
        "Esta imagem/PDF e uma CNH (Carteira Nacional de Habilitacao) brasileira. "
        "Extraia os dados exatamente como aparecem no documento. "
        "Se um campo nao existir ou nao estiver legivel, devolva string vazia para ele."
    )
    return _extrair_com_schema(caminho_arquivo, prompt, CNH_SCHEMA)


def extrair_dados_crlv_com_gemini(caminho_arquivo: str) -> dict:
    prompt = (
        "Esta imagem/PDF e um CRLV (Certificado de Registro e Licenciamento de Veiculo) brasileiro. "
        "Extraia os dados exatamente como aparecem no documento. "
        "Para categoria_veiculo, classifique o veiculo em uma das opcoes do enum combinando o campo "
        "'ESPECIE/TIPO' com a quantidade de eixos (campo 'eixos' do documento) - as duas informacoes "
        "juntas sao necessarias, uma sozinha nao basta: "
        "Se TIPO for 'CAMINHAO TRATOR' (unidade tratora articulada, puxa semi-reboque): "
        "2 eixos = CAVALO, 3 eixos = 'CAVALO TRUCADO 3 EIXOS', 4 ou mais eixos = 'CAVALO 4 EIXOS'. "
        "Se TIPO for 'CAMINHAO' (caminhao de carga rigido, sem semi-reboque, especie CARGA): "
        "2 eixos = TOCO, 3 eixos = TRUCK, 4 ou mais eixos = BITRUCK. "
        "Se TIPO for 'SEMI-REBOQUE' ou 'REBOQUE' = 'SEMI-REBOQUE 1'. Se TIPO for 'DOLLY' = DOLLY. "
        "Se TIPO for 'CAMIONETA' ou 'CAMINHONETE' de carga leve = '3/4'. Se for utilitario/furgao = VAN. "
        "Se for automovel de passeio = AUTOMÓVEIS. "
        "Para marca, use o valor mais proximo dentre as opcoes do enum (ignore "
        "prefixos como 'SR/' antes da marca). Para tipo_carroceria, use o valor do campo CARROCERIA "
        "do documento mapeado para uma das opcoes do enum. "
        "Se um campo nao existir ou nao estiver legivel, devolva string vazia para ele."
    )
    return _extrair_com_schema(caminho_arquivo, prompt, CRLV_SCHEMA)


def classificar_e_extrair_documento_com_gemini(caminho_arquivo: str) -> dict:
    """Usado pelo fluxo de 'Importar Documentos' do Bsoft, que recebe varios
    arquivos misturados (CNH, CRLV, RNTRC) e precisa descobrir o tipo de
    cada um antes de extrair os campos certos."""
    schema = {
        "type": "object",
        "properties": {
            "tipo": {"type": "string", "enum": ["CNH", "CRLV", "RNTRC", "DESCONHECIDO"]},
        },
        "required": ["tipo"],
    }
    prompt = (
        "Classifique este documento brasileiro como um dos tipos: CNH (Carteira Nacional de "
        "Habilitacao), CRLV (Certificado de Registro e Licenciamento de Veiculo), RNTRC (Registro "
        "Nacional de Transportadores Rodoviarios de Cargas) ou DESCONHECIDO."
    )
    tipo = _extrair_com_schema(caminho_arquivo, prompt, schema).get("tipo", "DESCONHECIDO")

    if tipo == "CNH":
        return {"tipo": tipo, "dados": extrair_dados_cnh_com_gemini(caminho_arquivo)}
    if tipo == "CRLV":
        return {"tipo": tipo, "dados": extrair_dados_crlv_com_gemini(caminho_arquivo)}
    if tipo == "RNTRC":
        schema_rntrc = {"type": "object", "properties": {"rntrc": {"type": "string"}}, "required": ["rntrc"]}
        prompt_rntrc = "Extraia o numero do RNTRC deste documento. Se nao encontrar, devolva string vazia."
        return {"tipo": tipo, "dados": _extrair_com_schema(caminho_arquivo, prompt_rntrc, schema_rntrc)}
    return {"tipo": tipo, "dados": {}}
