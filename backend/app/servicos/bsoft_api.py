"""Cliente da API Bsoft TMS.

Portado de gerenciador_atlantico/servicos/bsoft_api.py sem a dependencia de
tkinter: erros agora levantam BsoftApiError em vez de abrir messagebox.
"""
from __future__ import annotations

import json

import requests

from ..config import settings

def _base_url() -> str:
    """A URL vem de settings.bsoft_api_base_url (variavel de ambiente) - nao
    fica fixa no codigo, pra dar pra apontar pra outro tenant/homologacao."""
    return (settings.bsoft_api_base_url or "").rstrip("/")


class BsoftApiError(Exception):
    pass


def _auth():
    return (settings.bsoft_api_user, settings.bsoft_api_password)


def _clean(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if v is not None and v != ""}


def cadastrar_veiculo_bsoft(dados_veiculo: dict) -> dict:
    endpoint_url = f"{_base_url()}/transporte/v1/veiculos"
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
    endpoint_url = f"{_base_url()}/pessoas/v1/pessoas/{cod_pessoa}/enderecos"
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
    endpoint_url = f"{_base_url()}/pessoas/v1/pessoas/fisicas"
    resp = requests.post(endpoint_url, json=_payload_pessoa_fisica(dados_motorista), auth=_auth(), timeout=20)
    if resp.status_code in (200, 201):
        return resp.json()
    raise BsoftApiError(f"Falha ao cadastrar motorista (status {resp.status_code}): {resp.text}")


def atualizar_pessoa_fisica_bsoft(cpf: str, dados_motorista: dict) -> dict:
    endpoint_url = f"{_base_url()}/pessoas/v1/pessoas/fisicas/{cpf}"
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
    endpoint_url = f"{_base_url()}/pessoas/v1/pessoas/juridicas"
    resp = requests.post(endpoint_url, json=_payload_pessoa_juridica(dados_empresa.get("cnpj"), dados_empresa), auth=_auth(), timeout=20)
    if resp.status_code in (200, 201):
        return resp.json()
    raise BsoftApiError(f"Falha ao cadastrar proprietario PJ (status {resp.status_code}): {resp.text}")


def atualizar_pessoa_juridica_bsoft(cnpj: str, dados_empresa: dict) -> dict:
    endpoint_url = f"{_base_url()}/pessoas/v1/pessoas/juridicas/{cnpj}"
    resp = requests.put(endpoint_url, json=_payload_pessoa_juridica(cnpj, dados_empresa), auth=_auth(), timeout=20)
    if resp.status_code == 200:
        return resp.json()
    raise BsoftApiError(f"Falha ao atualizar proprietario PJ (status {resp.status_code}): {resp.text}")


def buscar_pessoa_fisica_por_cpf(cpf: str) -> str | None:
    if not cpf:
        return None
    url = f"{_base_url()}/pessoas/v1/pessoas/fisicas/{cpf}"
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
    url = f"{_base_url()}/pessoas/v1/pessoas/juridicas/{cnpj}"
    try:
        resp = requests.get(url, auth=_auth(), timeout=20)
        if resp.status_code == 200 and resp.text and resp.json():
            return resp.json()[0].get("id")
    except requests.exceptions.RequestException:
        return None
    return None


# Configuracoes do modulo de transporte que a emissao de CT-e precisa
# referenciar por id (a complexidade fiscal fica nesses cadastros, ja
# configurados dentro do Bsoft - a gente so precisa descobrir os ids).
CONFIGS_CTE = {
    "parametros_criacao_cte": "/transporte/v1/paramCriaCteViaNFe",
    "parametros_criacao_manifesto": "/transporte/v1/parametroCriacaoManifesto",
    "agencias": "/transporte/v1/agencias",
    "tipos_taloes": "/transporte/v1/tiposTaloes",
    "apolices_seguro": "/transporte/v1/apolicesSeguro",
    "conjuntos_veiculos": "/transporte/v1/conjuntoVeiculos",
    "operadoras_credito": "/transporte/v1/contratosFrete/operadorasCredito",
    "naturezas_carga": "/transporte/v1/naturezaCargas",
    "naturezas_operacao": "/transporte/v1/naturezasOperacao",
    "tipos_operacoes_tms": "/transporte/v1/tiposOperacoesTMS",
    "especies": "/transporte/v1/especies",
}


def _listar_bsoft(caminho: str, params: dict | None = None) -> list:
    """GET numa listagem do Bsoft. As listagens exigem o parametro 'fim'
    (paginacao) e devolvem 204 sem corpo quando o cadastro esta vazio."""
    # O Bsoft rejeita fim > 100 ("Limite invalido, valor maximo aceitavel de
    # retorno: 100").
    consulta = {"inicio": 0, "fim": 100}
    consulta.update(params or {})
    resp = requests.get(f"{_base_url()}{caminho}", params=consulta, auth=_auth(), timeout=30)
    if resp.status_code == 204 or not resp.text.strip():
        return []
    if resp.status_code != 200:
        raise BsoftApiError(f"{resp.status_code} em {caminho}: {resp.text[:300]}")
    try:
        dados = resp.json()
    except json.JSONDecodeError:
        raise BsoftApiError(f"Resposta nao-JSON em {caminho}: {resp.text[:300]}")
    return dados if isinstance(dados, list) else [dados]


def obter_configuracao_cte(nome: str, params: dict | None = None) -> dict:
    caminho = CONFIGS_CTE.get(nome)
    if not caminho:
        raise BsoftApiError(f"Configuracao '{nome}' desconhecida")
    return {"ok": True, "dados": _listar_bsoft(caminho, params)}


def obter_todas_configuracoes_cte() -> dict:
    """Le os cadastros que a emissao de CT-e referencia por id. Cada um pode
    falhar isolado (modulo nao contratado, permissao do usuario de
    integracao), entao o erro fica junto do resultado em vez de derrubar
    tudo. Os taloes dependem da agencia, entao sao buscados por agencia."""
    resultado = {}
    for nome in CONFIGS_CTE:
        if nome == "tipos_taloes":
            continue
        try:
            resultado[nome] = obter_configuracao_cte(nome)
        except Exception as exc:
            resultado[nome] = {"ok": False, "erro": str(exc)[:300]}

    agencias = resultado.get("agencias", {})
    if not agencias.get("ok"):
        resultado["tipos_taloes"] = {"ok": False, "erro": "depende das agencias, que falharam acima"}
        return resultado

    taloes = []
    erros_taloes = []
    for agencia in (agencias.get("dados") or []):
        agencia_id = agencia.get("id") if isinstance(agencia, dict) else None
        if not agencia_id:
            continue
        try:
            for talao in _listar_bsoft(CONFIGS_CTE["tipos_taloes"], {"agencia_id": agencia_id}):
                talao["_agencia_id"] = agencia_id
                taloes.append(talao)
        except Exception as exc:
            erros_taloes.append(f"agencia {agencia_id}: {str(exc)[:150]}")
    resultado["tipos_taloes"] = (
        {"ok": True, "dados": taloes} if not erros_taloes or taloes
        else {"ok": False, "erro": "; ".join(erros_taloes)[:300]}
    )
    return resultado


def obter_exemplos_documentos(quantidade: int = 3) -> dict:
    """Le (somente GET) os ultimos contratos de frete e CT-es ja emitidos.
    Serve pra descobrir, na pratica, quais ids/campos a operacao usa de
    verdade (regra de frete, forma de pagamento, natureza de operacao,
    talao) em vez de adivinhar o payload de emissao."""
    resultado = {}
    for nome, caminho in (
        ("contratos_frete", "/transporte/v1/contratosFrete"),
        ("conhecimentos", "/transporte/v1/conhecimentos"),
    ):
        try:
            registros = _listar_bsoft(caminho, {"fim": max(1, min(quantidade, 100))})
            resultado[nome] = {"ok": True, "dados": registros[:quantidade]}
        except Exception as exc:
            resultado[nome] = {"ok": False, "erro": str(exc)[:300]}

    # O detalhamento de valores traz campos que a listagem resume - e onde
    # pode aparecer a regra de frete (regrasCarreto_id), que e obrigatoria
    # no POST e nao tem endpoint proprio de cadastro.
    contratos = resultado.get("contratos_frete", {}).get("dados") or []
    contrato_id = contratos[0].get("id") if contratos and isinstance(contratos[0], dict) else None
    if contrato_id:
        try:
            valores = _listar_bsoft("/transporte/v1/contratosFrete/valores", {"id": contrato_id})
            resultado["contrato_frete_valores"] = {"ok": True, "dados": valores}
        except Exception as exc:
            resultado["contrato_frete_valores"] = {"ok": False, "erro": str(exc)[:300]}
    return resultado


# Cadastros citados por id no payload de emissao (regrasCarreto_id, cfops_id,
# etc) que nao tem GET documentado. A API segue o padrao /transporte/v1/<nome>,
# entao vale sondar os nomes provaveis - tudo GET, nao altera nada.
CANDIDATOS_CADASTROS = [
    "regrasCarreto", "regrasCarretos", "regraCarreto", "regrasFrete", "regraFrete",
    "carretos", "tabelasFrete", "precosConhecimento", "precos", "perfisApropriacao",
    "rotasDistribuicao", "rotaDistribuicao", "percursos", "percurso", "cfops", "cfop",
    "seguradoras", "operacoes", "operacoesMercadorias", "mercadorias", "modalidades",
]


def sondar_cadastros_transporte() -> dict:
    """Tenta GET em nomes provaveis de cadastro do modulo transporte, pra
    descobrir endpoints existentes que nao estao na documentacao publica."""
    achados = {}
    for nome in CANDIDATOS_CADASTROS:
        caminho = f"/transporte/v1/{nome}"
        try:
            resp = requests.get(
                f"{_base_url()}{caminho}", params={"inicio": 0, "fim": 100}, auth=_auth(), timeout=20
            )
        except Exception as exc:
            achados[nome] = {"status": "erro", "detalhe": str(exc)[:150]}
            continue
        if resp.status_code == 404:
            continue  # nao existe - nao polui o resultado
        registro = {"status": resp.status_code}
        if resp.status_code == 204:
            registro["detalhe"] = "existe, mas cadastro vazio"
        elif resp.status_code == 200:
            try:
                dados = resp.json()
                dados = dados if isinstance(dados, list) else [dados]
                registro["detalhe"] = f"{len(dados)} registro(s)"
                registro["amostra"] = dados[:10]
            except json.JSONDecodeError:
                registro["detalhe"] = resp.text[:200]
        else:
            registro["detalhe"] = resp.text[:200]
        achados[nome] = registro
    return achados


def listar_documentos_fiscais(data_inicio: str, data_fim: str) -> dict:
    """Somente leitura: CT-es emitidos e contratos de frete (com o CIOT) do
    periodo, pra exibir os documentos dentro do proprio sistema. Cada CT-e
    recebe o contrato de frete correspondente quando existe vinculo."""
    conhecimentos, contratos = [], []
    erros = {}
    try:
        conhecimentos = _listar_bsoft(
            "/transporte/v1/conhecimentos", {"dataInicio": data_inicio, "dataFim": data_fim}
        )
    except Exception as exc:
        erros["conhecimentos"] = str(exc)[:300]
    try:
        contratos = _listar_bsoft(
            "/transporte/v1/contratosFrete", {"dataInicio": data_inicio, "dataFim": data_fim}
        )
    except Exception as exc:
        erros["contratos_frete"] = str(exc)[:300]

    # O contrato de frete lista os numeros de CT-e que cobre (nrosCTe).
    contrato_por_cte = {}
    for contrato in contratos:
        for nro in contrato.get("nrosCTe") or []:
            contrato_por_cte[str(nro)] = contrato

    documentos = []
    for cte in conhecimentos:
        contrato = contrato_por_cte.get(str(cte.get("nro")))
        motorista = (cte.get("dados_motorista") or {})
        documentos.append({
            "cte_id": cte.get("id"),
            "cte_numero": cte.get("nro"),
            "emitido_em": cte.get("dtEmissao"),
            "chave_acesso": cte.get("chaveAcesso"),
            "remetente": cte.get("remetente"),
            "destinatario": cte.get("destinatario"),
            "cliente": cte.get("cliente"),
            "motorista": (motorista.get("motorista") or "").strip(),
            "veiculo": motorista.get("veiculo"),
            "carreta": motorista.get("carreta"),
            "favorecido": motorista.get("favorecido"),
            "status_averbacao": cte.get("statusAverbacao"),
            "contrato_numero": contrato.get("numeroCF") if contrato else None,
            "ciot": contrato.get("CIOT") if contrato else None,
            "operadora": contrato.get("operadoraCredito") if contrato else None,
            "valor": contrato.get("valorTotalOrigem") if contrato else None,
        })
    return {"documentos": documentos, "total_contratos": len(contratos), "erros": erros}


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
