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
import logging
import os
import re
import time
from functools import lru_cache

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from ..config import settings
from .bsoft_lookup import BSOFT_CATEGORIAS_VEICULO, BSOFT_SIMPLE_BRANDS_LIST, BSOFT_TIPOS_CARROCERIA_NOMES

# Em ordem de preferencia. O Google aposenta modelo (o 2.0-flash saiu em
# 08/2026): se um nao existir mais ou estiver sem cota, vai pro proximo em
# vez de cair direto no OCR local, que erra muito mais.
MODELOS = ("gemini-3.6-flash", "gemini-flash-latest", "gemini-2.5-flash")
MODELO = MODELOS[0]
# Ler documento nao pede raciocinio longo. No padrao do modelo um CRLV de
# 80 KB levava ~29 s e uma foto de CNH ~16 s - quase tudo "pensando".
NIVEL_RACIOCINIO = types.ThinkingLevel.LOW
# Chamada presa nao segura a tela: desiste e cai no OCR local, com aviso.
TEMPO_LIMITE_MS = 45_000

logger = logging.getLogger(__name__)

CATEGORIAS_CNH = ["A", "B", "C", "D", "E", "AB", "AC", "AD", "AE"]

CNH_SCHEMA = {
    "type": "object",
    "properties": {
        "nome": {"type": "string"},
        "cpf": {"type": "string", "description": "formato 000.000.000-00"},
        "numero": {"type": "string", "description": "numero de registro da CNH"},
        "seguro": {"type": "string", "description": "numero do seguro / cedula de identidade do condutor"},
        "categoria": {"type": "string", "enum": CATEGORIAS_CNH, "description": "campo '9 CAT. HAB.'"},
        "protocolo": {"type": "string", "description": "numero do espelho, impresso na vertical na margem"},
        "dtValidade": {"type": "string", "description": "data no formato dd/mm/aaaa"},
        "dtExpedicao": {"type": "string", "description": "data de emissao no formato dd/mm/aaaa"},
        "dtPrimeiraExpedicao": {"type": "string", "description": "data da 1a habilitacao no formato dd/mm/aaaa"},
        "dtNascimento": {"type": "string", "description": "data de nascimento no formato dd/mm/aaaa"},
    },
    # Campo com lista de opcoes fica fora do "required": sem ele legivel, a IA
    # deixa de fora (a API do Gemini recusa opcao vazia na lista).
    "required": ["nome", "cpf", "numero", "seguro", "protocolo", "dtValidade", "dtExpedicao", "dtPrimeiraExpedicao", "dtNascimento"],
}

CRLV_SCHEMA = {
    "type": "object",
    "properties": {
        "placa": {"type": "string", "description": "formato ABC-1D23"},
        "renavam": {"type": "string"},
        "modelo": {"type": "string", "description": "modelo do veiculo, sem a marca"},
        "eixos": {"type": "string", "description": "quantidade de eixos"},
        "categoria_veiculo": {"type": "string", "enum": sorted(BSOFT_CATEGORIAS_VEICULO.keys())},
        "marca": {"type": "string", "enum": sorted(set(BSOFT_SIMPLE_BRANDS_LIST))},
        "tipo_carroceria": {"type": "string", "enum": sorted(set(BSOFT_TIPOS_CARROCERIA_NOMES.values()))},
        "estado": {"type": "string", "description": "sigla da UF, 2 letras"},
        "cidade": {"type": "string"},
    },
    "required": ["placa", "renavam", "modelo", "eixos", "categoria_veiculo", "estado", "cidade"],
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


@lru_cache(maxsize=1)
def _cliente_para(chave: str) -> genai.Client:
    return genai.Client(api_key=chave, http_options=types.HttpOptions(timeout=TEMPO_LIMITE_MS))


def _client() -> genai.Client:
    if not settings.gemini_api_key:
        raise GeminiIndisponivel("GEMINI_API_KEY nao configurada")
    # Um cliente por processo: criar um por chamada refazia a conexao a
    # cada documento.
    return _cliente_para(settings.gemini_api_key)


def _extrair_com_schema(caminho_arquivo: str, prompt: str, schema: dict) -> dict:
    client = _client()

    extensao = os.path.splitext(caminho_arquivo)[1].lower()
    mime_type = _MIME_POR_EXTENSAO.get(extensao, "image/jpeg")

    with open(caminho_arquivo, "rb") as f:
        dados_arquivo = f.read()
    conteudo = [types.Part.from_bytes(data=dados_arquivo, mime_type=mime_type), prompt]
    schema = schema_aceito(schema)
    candidatos = [m for m in MODELOS if m not in _modelos_inexistentes] or list(MODELOS)
    ultimo_erro: Exception | None = None
    for modelo in candidatos:
        for tentativa in (1, 2):
            try:
                resposta = _gerar(client, modelo, conteudo, schema)
                if not resposta.text:
                    raise RespostaVazia(f"{modelo} nao devolveu texto")
                return json.loads(resposta.text)
            except genai_errors.APIError as exc:
                ultimo_erro = exc
                logger.warning("Gemini %s: erro %s (%s)", modelo, exc.code, str(exc)[:200])
                if exc.code == 404:
                    _modelos_inexistentes.add(modelo)
                    break
                # Limite de uso ou servidor ocupado: uma nova tentativa rapida
                # no mesmo modelo, depois o proximo.
                if tentativa == 1 and (exc.code == 429 or (exc.code or 0) >= 500):
                    time.sleep(1.5)
                    continue
                break
            except (RespostaVazia, json.JSONDecodeError) as exc:
                ultimo_erro = exc
                logger.warning("Gemini %s: resposta sem JSON valido (%s)", modelo, type(exc).__name__)
                break
    raise ultimo_erro or RespostaVazia("nenhum modelo respondeu")


class RespostaVazia(Exception):
    pass


def schema_aceito(schema):
    """Tira opcao vazia de toda lista (enum). Foi uma opcao "" na marca e na
    carroceria do CRLV que fez a API recusar TODA leitura com
    INVALID_ARGUMENT - e tudo caia no OCR local, lento e errado."""
    if isinstance(schema, dict):
        limpo = {chave: schema_aceito(valor) for chave, valor in schema.items()}
        if isinstance(limpo.get("enum"), list):
            limpo["enum"] = [opcao for opcao in limpo["enum"] if str(opcao).strip()]
        return limpo
    if isinstance(schema, list):
        return [schema_aceito(item) for item in schema]
    return schema


_modelos_inexistentes: set[str] = set()
_sem_nivel_raciocinio: set[str] = set()


def _gerar(client: genai.Client, modelo: str, conteudo: list, schema: dict):
    base = {"response_mime_type": "application/json", "response_schema": schema}
    if modelo not in _sem_nivel_raciocinio:
        try:
            return client.models.generate_content(
                model=modelo,
                contents=conteudo,
                config=types.GenerateContentConfig(
                    **base, thinking_config=types.ThinkingConfig(thinking_level=NIVEL_RACIOCINIO)
                ),
            )
        except genai_errors.ClientError as exc:
            # Modelo que nao aceita nivel de raciocinio: segue sem, e nao
            # tenta mais nesse processo.
            if exc.code != 400 or "think" not in str(exc).lower():
                raise
            _sem_nivel_raciocinio.add(modelo)
            logger.warning("Gemini: %s nao aceita thinking_level, seguindo sem", modelo)
    return client.models.generate_content(model=modelo, contents=conteudo, config=types.GenerateContentConfig(**base))


PROMPT_CNH = (
        "Esta imagem/PDF e uma CNH (Carteira Nacional de Habilitacao) brasileira: papel, foto do "
        "cartao ou CNH digital. Extraia os dados exatamente como aparecem, campo a campo:\n"
        "- nome: so o conteudo do campo '2 e 1 NOME E SOBRENOME' (ou 'NOME'), sem rotulo, numero "
        "ou letras soltas antes do nome.\n"
        "- cpf: campo '4d CPF'.\n"
        "- numero: campo '5 N REGISTRO' (11 digitos, geralmente em vermelho).\n"
        "- categoria: campo '9 CAT. HAB.'. Nao confunda com a letra ao lado do campo ACC.\n"
        "- seguro: numero de seguranca de 11 digitos perto de 'ASSINATURA DO EMISSOR', logo acima "
        "do codigo que comeca com a UF (ex.: RS258235683).\n"
        "- protocolo: numero do espelho, impresso na VERTICAL na margem esquerda. NAO e o "
        "documento de identidade do campo '4c'.\n"
        "- dtValidade: campo '4b VALIDADE'. dtExpedicao: campo '4a DATA EMISSAO'. "
        "dtPrimeiraExpedicao: campo '1a HABILITACAO'. dtNascimento: a data do campo "
        "'3 DATA, LOCAL E UF DE NASCIMENTO'.\n"
        "Datas em dd/mm/aaaa. Se um campo nao existir ou nao estiver legivel, devolva string vazia para ele."
)

PROMPT_CRLV = (
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


def _so_digitos(valor) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def limpar_cnh(dados: dict) -> dict:
    """Confere o que a IA devolveu antes de ir pra tela: campo fora do
    formato vira vazio (melhor em branco que errado)."""
    d = dict(dados or {})
    # "OL RE FABIO GIOVANI SEBEN" -> "FABIO GIOVANI SEBEN": pedaco de rotulo
    # lido junto com o nome. Nome brasileiro nao comeca com 1 ou 2 letras.
    partes = re.sub(r"[^A-Za-zÀ-ÿ' ]", " ", str(d.get("nome") or "")).split()
    while len(partes) > 1 and (len(partes[0]) <= 2 or partes[0].upper() in ("NOME", "SOBRENOME")):
        partes.pop(0)
    d["nome"] = " ".join(partes)

    categoria = re.sub(r"\s", "", str(d.get("categoria") or "")).upper()
    d["categoria"] = categoria if categoria in CATEGORIAS_CNH else ""

    cpf = _so_digitos(d.get("cpf"))
    d["cpf"] = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}" if len(cpf) == 11 else ""
    for campo in ("numero", "seguro", "protocolo"):
        d[campo] = _so_digitos(d.get(campo))

    for campo in ("dtValidade", "dtExpedicao", "dtPrimeiraExpedicao", "dtNascimento"):
        achou = re.search(r"(\d{2})[/.-](\d{2})[/.-](\d{4})", str(d.get(campo) or ""))
        d[campo] = f"{achou.group(1)}/{achou.group(2)}/{achou.group(3)}" if achou else ""
    return d


def extrair_dados_cnh_com_gemini(caminho_arquivo: str) -> dict:
    return limpar_cnh(_extrair_com_schema(caminho_arquivo, PROMPT_CNH, CNH_SCHEMA))


def limpar_crlv(dados: dict) -> dict:
    """Campo que a IA deixou de fora (marca, carroceria) volta vazio."""
    return {campo: str((dados or {}).get(campo) or "") for campo in CRLV_SCHEMA["properties"]}


def extrair_dados_crlv_com_gemini(caminho_arquivo: str) -> dict:
    return limpar_crlv(_extrair_com_schema(caminho_arquivo, PROMPT_CRLV, CRLV_SCHEMA))


def ler_documento_com_gemini(caminho_arquivo: str) -> dict:
    """Descobre o tipo E le os campos numa chamada so.

    O caminho antigo (classificar_e_extrair_documento_com_gemini) fazia duas
    chamadas por arquivo - uma so pra saber o tipo, outra pros campos -
    mandando o documento inteiro nas duas. Tres documentos viravam seis
    chamadas, e a importacao demorava. As instrucoes de cada tipo sao as
    mesmas das funcoes especificas.
    """
    schema = {
        "type": "object",
        "properties": {
            "tipo": {"type": "string", "enum": ["CNH", "CRLV", "RNTRC", "DESCONHECIDO"]},
            "cnh": CNH_SCHEMA,
            "crlv": CRLV_SCHEMA,
            "rntrc": {"type": "string"},
        },
        "required": ["tipo"],
    }
    prompt = (
        "Classifique este documento brasileiro como CNH (Carteira Nacional de Habilitacao), CRLV "
        "(Certificado de Registro e Licenciamento de Veiculo), RNTRC (Registro Nacional de "
        "Transportadores Rodoviarios de Cargas) ou DESCONHECIDO, e preencha SO o bloco do tipo encontrado.\n\n"
        "Se for CNH, preencha o bloco 'cnh'. " + PROMPT_CNH + "\n\n"
        "Se for CRLV, preencha o bloco 'crlv'. " + PROMPT_CRLV + "\n\n"
        "Se for RNTRC, preencha 'rntrc' com o numero do RNTRC (string vazia se nao encontrar)."
    )
    resposta = _extrair_com_schema(caminho_arquivo, prompt, schema)
    tipo = resposta.get("tipo") or "DESCONHECIDO"
    if tipo == "CNH":
        return {"tipo": tipo, "dados": limpar_cnh(resposta.get("cnh") or {})}
    if tipo == "CRLV":
        return {"tipo": tipo, "dados": limpar_crlv(resposta.get("crlv") or {})}
    if tipo == "RNTRC":
        return {"tipo": tipo, "dados": {"rntrc": resposta.get("rntrc") or ""}}
    return {"tipo": "DESCONHECIDO", "dados": {}}


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
