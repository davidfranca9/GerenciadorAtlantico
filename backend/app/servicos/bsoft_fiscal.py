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
import time

from .bsoft_client import BsoftError, chamar, listar

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


def criar_conhecimento(corpo: dict) -> dict:
    """ESCRITA. Cria o CT-e pelo payload completo.

    E o caminho que reproduz a tela de emissao campo a campo, sem depender
    do paramCriaCteViaNFe (que esta vazio no tenant).

    O payload sai de cte_montagem.montar_payload_conhecimento, que por
    padrao marca rascunho = "S". Nao confirme rascunho = "N" enquanto a
    pergunta 1.5 do suporte nao estiver respondida: nao esta documentado se
    o rascunho realmente evita efeito fiscal.
    """
    if not corpo.get("mercadorias"):
        raise ValueError("Payload sem mercadorias: o CT-e precisa da NF-e transportada")

    _, resposta = chamar(
        "POST", "/transporte/v1/conhecimentos", json_body=corpo, operacao_de_escrita=True
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


# --------------------------------------------------------------------------
# Pessoas e enderecos
#
# O CT-e referencia remetente, destinatario e os enderecos deles por id do
# cadastro do Bsoft. A NF-e da o CNPJ/CPF e o codigo IBGE do municipio; e
# daqui que sai o id correspondente.
# --------------------------------------------------------------------------


def buscar_pessoa(documento: str) -> dict | None:
    """LEITURA. Busca a pessoa pelo CPF ou CNPJ.

    O endpoint muda conforme o documento: destinatario da carga pode ser
    produtor rural (CPF), como no CT-e 5053.
    """
    doc = "".join(filter(str.isdigit, documento or ""))
    if len(doc) == 11:
        caminho = f"/pessoas/v1/pessoas/fisicas/{doc}"
    elif len(doc) == 14:
        caminho = f"/pessoas/v1/pessoas/juridicas/{doc}"
    else:
        raise ValueError("Documento precisa ser um CPF (11) ou CNPJ (14 digitos)")

    try:
        status, dados = chamar("GET", caminho)
    except BsoftError as exc:
        # 404 aqui nao e falha de consulta: e a resposta de que o documento
        # nao esta cadastrado. Tratar como erro derrubava a busca inteira,
        # inclusive as partes que ja tinham sido resolvidas.
        if getattr(exc, "status", None) == 404:
            return None
        raise

    if status == 204 or not dados:
        return None
    # A API responde uma lista mesmo pra busca por documento.
    return dados[0] if isinstance(dados, list) else dados


def listar_enderecos(pessoa_id: str | int) -> list:
    """LEITURA. Enderecos cadastrados de uma pessoa."""
    return listar(f"/pessoas/v1/pessoas/{pessoa_id}/enderecos")


# Quantas paginas de veiculos percorrer. A listagem nao aceita filtro por
# placa (nao ha parametro documentado), entao a busca e local. Com o cache
# a varredura acontece uma vez a cada cinco minutos, entao da pra cobrir
# uma frota maior sem deixar a tela lenta.
MAX_PAGINAS_VEICULOS = 50
TAMANHO_PAGINA = 100


def _so_alfanumerico(texto: str) -> str:
    return "".join(c for c in (texto or "").upper() if c.isalnum())


# A frota nao muda de minuto em minuto, e paginar o cadastro inteiro pra
# cada placa deixava a tela lenta (sao ate tres placas por CT-e). O cache
# de processo transforma tres varreduras em uma.
_CACHE_VEICULOS: dict = {"quando": 0.0, "lista": []}
VALIDADE_CACHE_SEGUNDOS = 300


def _todos_os_veiculos() -> list:
    """LEITURA. Cadastro de veiculos, com cache curto."""
    agora = time.time()
    if _CACHE_VEICULOS["lista"] and agora - _CACHE_VEICULOS["quando"] < VALIDADE_CACHE_SEGUNDOS:
        return _CACHE_VEICULOS["lista"]

    todos: list = []
    for pagina in range(MAX_PAGINAS_VEICULOS):
        inicio = pagina * TAMANHO_PAGINA
        lote = listar(
            "/transporte/v1/veiculos",
            {"inicio": inicio, "fim": inicio + TAMANHO_PAGINA},
        )
        if not lote:
            break
        todos.extend(lote)
        if len(lote) < TAMANHO_PAGINA:
            break

    _CACHE_VEICULOS.update({"quando": agora, "lista": todos})
    return todos


def buscar_veiculo_por_placa(placa: str) -> dict | None:
    """LEITURA. Procura o veiculo pela placa.

    O GET /transporte/v1/veiculos nao tem parametro de busca documentado,
    entao a comparacao e local, com a placa normalizada (o cadastro pode
    ter hifen e o agendamento nao).
    """
    alvo = _so_alfanumerico(placa)
    if not alvo:
        return None
    for veiculo in _todos_os_veiculos():
        if _so_alfanumerico(str(veiculo.get("placa", ""))) == alvo:
            return veiculo
    return None


# Nomes possiveis do campo de numero na apolice. O cadastro nao esta
# documentado campo a campo, entao a busca tenta os nomes plausiveis em vez
# de fixar um so e falhar em silencio.
CAMPOS_NUMERO_APOLICE = ("numeroApolice", "numero", "apolice", "Apolice", "nroApolice")
CAMPOS_SEGURADORA = ("seguradora_id", "seguradoraId", "seguradora")


def buscar_apolice(numero: str) -> dict | None:
    """LEITURA. Acha a apolice de seguro pelo numero e devolve os ids.

    O CT-e exige seguradora_id; apolice_id e opcional pela documentacao.
    Como o numero ja e conhecido (202511, conferido no DACTE), da pra
    resolver o id por consulta em vez de configurar na mao.
    """
    alvo = str(numero or "").strip()
    if not alvo:
        return None

    for registro in listar("/transporte/v1/apolicesSeguro"):
        for campo in CAMPOS_NUMERO_APOLICE:
            if str(registro.get(campo, "")).strip() == alvo:
                seguradora = next(
                    (registro[c] for c in CAMPOS_SEGURADORA if registro.get(c)), ""
                )
                return {
                    "apolice_id": registro.get("id", ""),
                    "seguradora_id": seguradora,
                    "registro": registro,
                }
    return None
