"""Cliente HTTP central da API Bsoft TMS.

Todas as chamadas ao Bsoft passam por aqui, pra garantir em um lugar so:
timeout, tratamento uniforme de erro, log sanitizado (nunca senha, XML ou
dado bancario) e retry apenas onde e seguro repetir.

Regra importante: **nao existe retry automatico em POST/PUT/PATCH**. Repetir
uma criacao fiscal depois de um timeout pode gerar documento duplicado - o
protocolo correto e consultar se o documento foi criado antes de tentar de
novo, e isso e responsabilidade de quem chama.
"""
from __future__ import annotations

import json
import logging
import time

import requests

from ..config import settings

logger = logging.getLogger(__name__)

METODOS_SEGUROS_PARA_RETRY = {"GET"}
MAX_TENTATIVAS_LEITURA = 3

# Campos que nunca podem aparecer no log.
CAMPOS_SENSIVEIS = {
    "arquivo", "ctesZip", "xml", "senha", "password", "hashed_password",
    "conta", "agencia_bancaria", "numeroCartao", "cpf_motorista", "documento_contratado",
}


class BsoftError(Exception):
    """Erro de comunicacao ou de negocio vindo da API do Bsoft."""

    def __init__(self, mensagem: str, status: int | None = None, corpo: str | None = None):
        super().__init__(mensagem)
        self.status = status
        self.corpo = corpo


class BsoftEmissaoBloqueada(BsoftError):
    """Operacao de escrita tentada com a trava de emissao desligada."""


def _base_url() -> str:
    url = (settings.bsoft_api_base_url or "").rstrip("/")
    if not url:
        raise BsoftError("BSOFT_API_BASE_URL nao configurada")
    return url


def _auth() -> tuple[str, str]:
    if not settings.bsoft_api_user or not settings.bsoft_api_password:
        raise BsoftError("Credenciais do Bsoft nao configuradas")
    return (settings.bsoft_api_user, settings.bsoft_api_password)


def sanitizar(dado):
    """Devolve uma copia do payload sem os campos sensiveis, pra log."""
    if isinstance(dado, dict):
        return {
            chave: ("<omitido>" if chave in CAMPOS_SENSIVEIS else sanitizar(valor))
            for chave, valor in dado.items()
        }
    if isinstance(dado, list):
        return [sanitizar(item) for item in dado[:5]]
    if isinstance(dado, str) and len(dado) > 200:
        return f"<string de {len(dado)} caracteres>"
    return dado


def _resumo_resposta(resp: requests.Response) -> str:
    texto = (resp.text or "").strip()
    return texto[:300] if texto else "(sem corpo)"


def chamar(
    metodo: str,
    caminho: str,
    *,
    params: dict | None = None,
    json_body: dict | None = None,
    operacao_de_escrita: bool = False,
) -> tuple[int, object]:
    """Executa uma chamada no Bsoft e devolve (status_http, corpo_json).

    Corpo vazio (204) volta como None. Erros de negocio/HTTP viram BsoftError.
    Quando operacao_de_escrita=True, respeita a trava settings.bsoft_emissao_habilitada.
    """
    metodo = metodo.upper()
    if operacao_de_escrita and not settings.bsoft_emissao_habilitada:
        raise BsoftEmissaoBloqueada(
            "Emissao no Bsoft esta desligada (BSOFT_EMISSAO_HABILITADA=false). "
            "Nenhuma chamada de escrita foi enviada."
        )

    url = f"{_base_url()}{caminho}"
    tentativas = MAX_TENTATIVAS_LEITURA if metodo in METODOS_SEGUROS_PARA_RETRY else 1
    ultimo_erro: Exception | None = None

    for tentativa in range(1, tentativas + 1):
        try:
            resp = requests.request(
                metodo,
                url,
                params=params,
                json=json_body,
                auth=_auth(),
                timeout=settings.bsoft_timeout_segundos,
            )
        except requests.exceptions.RequestException as exc:
            ultimo_erro = exc
            logger.warning(
                "Bsoft %s %s falhou na rede (tentativa %s/%s): %s",
                metodo, caminho, tentativa, tentativas, type(exc).__name__,
            )
            if tentativa < tentativas:
                time.sleep(min(2 ** tentativa, 8))
                continue
            raise BsoftError(f"Falha de rede ao chamar {caminho}: {exc}") from exc

        logger.info(
            "Bsoft %s %s -> %s | params=%s body=%s",
            metodo, caminho, resp.status_code, sanitizar(params or {}), sanitizar(json_body or {}),
        )

        if resp.status_code == 204 or not (resp.text or "").strip():
            return resp.status_code, None
        if resp.status_code >= 400:
            raise BsoftError(
                f"{resp.status_code} em {caminho}: {_resumo_resposta(resp)}",
                status=resp.status_code,
                corpo=_resumo_resposta(resp),
            )
        try:
            return resp.status_code, resp.json()
        except json.JSONDecodeError as exc:
            raise BsoftError(f"Resposta nao-JSON em {caminho}: {_resumo_resposta(resp)}") from exc

    raise BsoftError(f"Falha ao chamar {caminho}: {ultimo_erro}")


def listar(caminho: str, params: dict | None = None) -> list:
    """GET de listagem. O Bsoft exige paginacao (`fim`, maximo 100) e devolve
    204 sem corpo quando o cadastro esta vazio."""
    consulta = {"inicio": 0, "fim": 100}
    consulta.update(params or {})
    _, dados = chamar("GET", caminho, params=consulta)
    if dados is None:
        return []
    return dados if isinstance(dados, list) else [dados]
