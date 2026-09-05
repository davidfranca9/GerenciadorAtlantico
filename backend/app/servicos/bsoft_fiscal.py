"""Operacoes fiscais no Bsoft (NF-e, CT-e, contrato de frete, CIOT, MDF-e).

Cada funcao diz explicitamente se e LEITURA ou ESCRITA. As de escrita passam
`operacao_de_escrita=True` pro cliente, que respeita a trava
`settings.bsoft_emissao_habilitada` - com ela desligada, nada e enviado.

Nao ha aqui nenhum endpoint inventado: todos vieram da documentacao oficial
(docs.bsoft.app). O que a documentacao nao cobre - gerar CIOT, transmitir
CT-e, criar MDF-e novo - esta em PERGUNTAS_SUPORTE_BSOFT.md, nao no codigo.
"""
from __future__ import annotations

import base64

from .bsoft_client import chamar, listar

# --------------------------------------------------------------------------
# NF-e
# --------------------------------------------------------------------------


def importar_nfe_por_xml(xml_bytes: bytes, buscar_motorista: bool = True) -> dict:
    """ESCRITA. Cadastra a NF-e da carga no Bsoft a partir do XML.
    Resposta documentada: {"codNFe": "4975"}."""
    _, corpo = chamar(
        "POST",
        "/transporte/v1/nfePreCadastrada/viaXML",
        json_body={
            "buscaMotorista": "S" if buscar_motorista else "N",
            "arquivo": base64.b64encode(xml_bytes).decode("ascii"),
        },
        operacao_de_escrita=True,
    )
    return corpo or {}


def listar_nfes_pre_cadastradas(params: dict | None = None) -> list:
    """LEITURA."""
    return listar("/transporte/v1/nfePreCadastrada", params)


# --------------------------------------------------------------------------
# CT-e
# --------------------------------------------------------------------------


def criar_cte_via_nfe(
    *,
    parametro_criacao_cte: str,
    ids_nfe: list[str] | None = None,
    chaves_nfe: list[str] | None = None,
    valores: dict | None = None,
) -> dict:
    """ESCRITA. Cria o CT-e a partir de NF-e ja cadastrada no Bsoft.

    Quando `chaves_nfe` e informado, o Bsoft ignora `ids_nfe`.
    Resposta documentada: {"codConhecimentos": "9"}.

    ATENCAO: a documentacao nao diz se este endpoint tambem transmite o CT-e
    a SEFAZ ou apenas cadastra no TMS - ver PERGUNTAS_SUPORTE_BSOFT.md.
    """
    if not chaves_nfe and not ids_nfe:
        raise ValueError("Informe ids_nfe ou chaves_nfe")

    corpo = {"parametroCriacaoCTe": str(parametro_criacao_cte)}
    if chaves_nfe:
        corpo["chavesNFe"] = list(chaves_nfe)
    else:
        corpo["ids"] = [str(i) for i in ids_nfe or []]
    corpo.update(valores or {})

    _, resposta = chamar(
        "POST", "/transporte/v1/conhecimentos/viaNFe", json_body=corpo, operacao_de_escrita=True
    )
    return resposta or {}


def consultar_conhecimentos(params: dict | None = None) -> list:
    """LEITURA. Filtros documentados: dataInicio, dataFim, chaveAcesso."""
    return listar("/transporte/v1/conhecimentos", params)


def obter_conhecimento(conhecimento_id: str) -> dict:
    """LEITURA. Registro individual, usado pra acompanhar status e chave."""
    _, corpo = chamar("GET", f"/transporte/v1/conhecimentos/{conhecimento_id}")
    if isinstance(corpo, list):
        return corpo[0] if corpo else {}
    return corpo or {}


def obter_dacte(conhecimento_id: str) -> dict:
    """LEITURA. PDF do DACTE. So faz sentido depois de autorizado."""
    _, corpo = chamar("GET", f"/transporte/v1/conhecimentos/{conhecimento_id}/obterDacte")
    return corpo if isinstance(corpo, dict) else {"conteudo": corpo}


def obter_xml_ctes_emitidos(chaves: list[str], incluir_eventos: bool = False) -> object:
    """LEITURA. XML autorizado dos CT-e. Maximo de 50 chaves por requisicao."""
    if len(chaves) > 50:
        raise ValueError("A consulta aceita no maximo 50 chaves por requisicao")
    _, corpo = chamar(
        "POST",
        "/eDoc/v1/XMLDocumentosFiscais/CTesEmitidos",
        json_body={"chaves": chaves, "obterXmlEventos": "S" if incluir_eventos else "N"},
    )
    return corpo


# --------------------------------------------------------------------------
# Contrato de frete / CIOT
# --------------------------------------------------------------------------


def criar_contrato_frete(dados: dict) -> dict:
    """ESCRITA. Cria o contrato de frete (base do CIOT quando o transporte e
    executado por terceiro).

    ATENCAO: o campo CIOT e de ENTRADA na documentacao. Nao ha, em toda a API
    publicada, endpoint de geracao de CIOT - entao nao esta confirmado que
    criar o contrato por aqui dispara a geracao na operadora. Enquanto o
    suporte nao confirmar, usar isto em producao pode gerar contrato sem
    CIOT. Ver PERGUNTAS_SUPORTE_BSOFT.md.
    """
    _, corpo = chamar(
        "POST", "/transporte/v1/contratosFrete", json_body=dados, operacao_de_escrita=True
    )
    return corpo or {}


def consultar_status_operadora(contrato_id: str | None = None) -> list:
    """LEITURA. Situacao do contrato junto a operadora (Efrete), incluindo o
    CIOT e o status da integracao."""
    return listar(
        "/transporte/v1/contratosFrete/operadorasCredito",
        {"id": contrato_id} if contrato_id else None,
    )


# --------------------------------------------------------------------------
# MDF-e (apenas o que a documentacao cobre)
# --------------------------------------------------------------------------


def consultar_manifestos(params: dict | None = None) -> list:
    """LEITURA."""
    return listar("/transporte/v1/manifestos", params)


def encerrar_manifesto(manifesto_id: str) -> dict:
    """ESCRITA. Encerra o MDF-e - obrigacao legal que costuma ser esquecida.

    Nao existe na API publicada um POST que crie e transmita um MDF-e novo;
    so importacao por XML e operacoes sobre manifestos existentes.
    """
    _, corpo = chamar(
        "PATCH", f"/transporte/v1/manifestos/{manifesto_id}/encerrar", operacao_de_escrita=True
    )
    return corpo or {}
