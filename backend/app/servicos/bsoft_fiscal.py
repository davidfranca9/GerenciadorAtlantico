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
from concurrent.futures import ThreadPoolExecutor

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


# Quantas paginas buscar ao mesmo tempo. Cada pagina e uma ida e volta ao
# Bsoft; em serie, 50 paginas viravam 50 esperas enfileiradas e a tela
# demorava demais. Sao todas GET, entao podem ir juntas.
PAGINAS_SIMULTANEAS = 8


def _pagina(caminho: str, offset: int) -> list:
    """LEITURA. Uma pagina da listagem, no formato documentado.

    A paginacao do Bsoft e `?limit=offset,quantidade` (ou `ini`/`fim`).
    O codigo mandava `inicio`, que a API ignora em silencio: toda pagina
    voltava sendo a primeira, e o sistema so enxergava os 100 primeiros
    veiculos e pessoas - "placa nao encontrada" pra quem estava depois.
    """
    _, dados = chamar("GET", caminho, params={"limit": f"{offset},{TAMANHO_PAGINA}"})
    if dados is None:
        return []
    return dados if isinstance(dados, list) else [dados]


def _paginar(caminho: str) -> list:
    """LEITURA. Le uma listagem inteira, em ondas de paginas paralelas.

    Para quando uma pagina vem incompleta (acabou) ou repetida (a API nao
    andou) - a segunda protecao existe porque foi exatamente o que passou
    despercebido: 50 paginas iguais, 25 copias do mesmo cadastro na tela.
    """
    todos: list = []
    vistos: set = set()
    pagina = 0
    while pagina < MAX_PAGINAS_VEICULOS:
        faixa = range(pagina, min(pagina + PAGINAS_SIMULTANEAS, MAX_PAGINAS_VEICULOS))
        with ThreadPoolExecutor(max_workers=PAGINAS_SIMULTANEAS) as executor:
            ondas = list(executor.map(lambda p: _pagina(caminho, p * TAMANHO_PAGINA), faixa))

        chegou_ao_fim = False
        for lote in ondas:
            novos = [item for item in lote if str(item.get("id")) not in vistos]
            for item in novos:
                vistos.add(str(item.get("id")))
            todos.extend(novos)
            # Pagina incompleta: o cadastro acabou. Pagina sem nada novo: a
            # API nao paginou - continuar so repetiria o mesmo.
            if len(lote) < TAMANHO_PAGINA or not novos:
                chegou_ao_fim = True
        if chegou_ao_fim:
            break
        pagina += PAGINAS_SIMULTANEAS

    return todos


def _todos_os_veiculos() -> list:
    """LEITURA. Cadastro de veiculos, com cache curto."""
    agora = time.time()
    if _CACHE_VEICULOS["lista"] and agora - _CACHE_VEICULOS["quando"] < VALIDADE_CACHE_SEGUNDOS:
        return _CACHE_VEICULOS["lista"]

    todos = _paginar("/transporte/v1/veiculos")
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

    # O GET /veiculos aceita `placa` como filtro (documentado). O cadastro
    # pode guardar com ou sem hifen, entao as duas formas sao tentadas
    # antes de cair na varredura completa.
    for forma in {placa.strip().upper(), alvo, f"{alvo[:3]}-{alvo[3:]}"}:
        if not forma:
            continue
        try:
            for veiculo in listar("/transporte/v1/veiculos", {"placa": forma}):
                if _so_alfanumerico(str(veiculo.get("placa", ""))) == alvo:
                    return veiculo
        except BsoftError:
            break

    for veiculo in _todos_os_veiculos():
        if _so_alfanumerico(str(veiculo.get("placa", ""))) == alvo:
            return veiculo
    return None


# O cadastro de veiculo do Bsoft guarda o motorista habitual, como texto:
# "042.xxx.xxx-39 - Joao" (CPF parcialmente mascarado, depois o nome). E o
# que permite escolher o motorista e trazer as placas dele junto, sem
# depender de conjunto cadastrado - so tres existem no tenant.
#
# As categorias sao as do GET /transporte/v1/categoriasVeiculos. Cada slot
# do CT-e recebe uma familia delas.
CATEGORIAS_CAVALO = ("CAVALO", "CAVALO SOZINHO", "TRUCK", "TOCO", "VAN", "VEICULO LIVRE")
CATEGORIAS_CARRETA = ("CARRETA", "CARRETA LIVRE", "BR13-CENTRAL")
CATEGORIAS_SEGUNDA_CARRETA = ("2 CARRETA", "DOLLY")


def _sem_acento(texto: str) -> str:
    import unicodedata
    limpo = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in limpo if not unicodedata.combining(c))


def _normalizar_categoria(categoria: str) -> str:
    """'2º CARRETA' -> '2 CARRETA', 'VEÍCULO LIVRE' -> 'VEICULO LIVRE'."""
    # O ordinal sai ANTES de tirar acento: o NFKD transforma "º" em "o", e
    # "2º CARRETA" viraria "2O CARRETA".
    sem_ordinal = str(categoria or "").replace("º", "").replace("ª", "").replace("°", "")
    return " ".join(_sem_acento(sem_ordinal).upper().split())


def _mesmo_motorista(texto_do_veiculo: str, cpf: str, nome: str) -> bool:
    """Diz se o motorista gravado no veiculo e este.

    O texto vem como "042.xxx.xxx-39 - Joao": o CPF pode estar mascarado,
    entao a comparacao aceita 'x' como coringa, digito a digito. Se o CPF
    nao decidir, vale o nome - sem acento, sem caixa.
    """
    texto = str(texto_do_veiculo or "").strip()
    if not texto:
        return False
    doc_parte, _, nome_parte = texto.partition(" - ")

    alvo = "".join(c for c in str(cpf or "") if c.isdigit())
    visiveis = "".join(c for c in doc_parte.lower() if c.isdigit() or c == "x")
    if len(alvo) == 11 and len(visiveis) == 11:
        if all(v == "x" or v == a for v, a in zip(visiveis, alvo)):
            return True
        return False  # CPF completo e diferente: nao e a mesma pessoa

    nome_alvo = _sem_acento(nome).upper().strip()
    nome_veiculo = _sem_acento(nome_parte or texto).upper().strip()
    if nome_alvo and nome_veiculo:
        return nome_alvo in nome_veiculo or nome_veiculo in nome_alvo
    return False


def nome_da_pessoa_por_id(pessoa_id) -> str:
    """LEITURA. Nome de uma pessoa fisica do cache, pelo id."""
    alvo = str(pessoa_id or "")
    for pessoa in _todas_as_pessoas_fisicas():
        if str(pessoa.get("id")) == alvo:
            return _nome_da_pessoa(pessoa)
    return ""


def veiculos_do_motorista(cpf: str = "", nome: str = "") -> dict:
    """LEITURA. Placas ligadas a um motorista no cadastro de veiculos.

    Devolve uma placa por slot do CT-e (cavalo, carreta, segunda carreta),
    escolhendo a atualizada mais recentemente quando ha mais de uma na
    mesma categoria - e a que esta em uso.
    """
    if not (cpf or nome):
        return {"placa_cavalo": "", "placa_carreta1": "", "placa_carreta2": "", "veiculos": []}

    achados = [
        v for v in _todos_os_veiculos()
        if _mesmo_motorista(v.get("motorista", ""), cpf, nome)
    ]
    achados.sort(key=lambda v: str(v.get("atualizacao") or ""), reverse=True)

    slots = {"placa_cavalo": "", "placa_carreta1": "", "placa_carreta2": ""}
    for veiculo in achados:
        categoria = _normalizar_categoria(veiculo.get("categoria", ""))
        placa = str(veiculo.get("placa") or "").strip()
        if not placa:
            continue
        if categoria in CATEGORIAS_CAVALO:
            slot = "placa_cavalo"
        elif categoria in CATEGORIAS_CARRETA:
            slot = "placa_carreta1"
        elif categoria in CATEGORIAS_SEGUNDA_CARRETA:
            slot = "placa_carreta2"
        else:
            continue
        if not slots[slot]:
            slots[slot] = placa

    slots["veiculos"] = [
        {"id": v.get("id"), "placa": v.get("placa"), "categoria": v.get("categoria", "")}
        for v in achados
    ]
    return slots


# Segunda fonte de placas: o ultimo CT-e emitido com o mesmo cavalo ou o
# mesmo motorista. O cadastro de veiculo so conhece o motorista habitual
# (o PFJ-2I64 e da Soraia, mesmo quando o Carlos dirige); o CT-e anterior
# sabe qual carreta andou atras de qual cavalo de verdade.
_CACHE_CTES: dict = {"quando": 0.0, "lista": []}
DIAS_DE_HISTORICO = 90  # o filtro por data aceita no maximo 3 meses


def _ctes_recentes() -> list:
    """LEITURA. CT-es dos ultimos meses, com cache curto."""
    from datetime import date, timedelta

    agora = time.time()
    if _CACHE_CTES["lista"] and agora - _CACHE_CTES["quando"] < VALIDADE_CACHE_SEGUNDOS:
        return _CACHE_CTES["lista"]
    hoje = date.today()
    lista = consultar_conhecimentos({
        "dataInicio": (hoje - timedelta(days=DIAS_DE_HISTORICO)).strftime("%Y-%m-%d"),
        "dataFim": hoje.strftime("%Y-%m-%d"),
    })
    _CACHE_CTES.update({"quando": agora, "lista": lista})
    return lista


def placas_do_ultimo_cte(placa_cavalo: str = "", motorista_nome: str = "", ctes: list | None = None) -> dict:
    """Placas do CT-e mais recente com este cavalo (ou, senao, este motorista).

    O cavalo vale mais que o motorista: a carreta anda atras do cavalo,
    nao atras da pessoa.
    """
    vazio = {"placa_cavalo": "", "placa_carreta1": "", "placa_carreta2": "", "fonte": ""}
    alvo_placa = _so_alfanumerico(placa_cavalo)
    alvo_nome = _sem_acento(motorista_nome).upper().strip()
    if not (alvo_placa or alvo_nome):
        return vazio

    lista = ctes if ctes is not None else _ctes_recentes()
    ordenada = sorted(lista, key=lambda c: str(c.get("dtEmissao") or ""), reverse=True)

    def _escolher(criterio):
        for cte in ordenada:
            dados = cte.get("dados_motorista") or {}
            if criterio(dados):
                numero = cte.get("nro")
                quando = str(cte.get("dtEmissao") or "")[:10]
                return {
                    "placa_cavalo": str(dados.get("veiculo") or "").strip(),
                    "placa_carreta1": str(dados.get("carreta") or "").strip(),
                    "placa_carreta2": str(dados.get("semiReboque") or "").strip(),
                    "fonte": f"CT-e {numero} de {quando}",
                }
        return None

    if alvo_placa:
        achado = _escolher(lambda d: _so_alfanumerico(str(d.get("veiculo") or "")) == alvo_placa)
        if achado:
            return achado
    if alvo_nome:
        achado = _escolher(lambda d: alvo_nome in _sem_acento(d.get("motorista") or "").upper())
        if achado:
            return achado
    return vazio


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


_CACHE_PESSOAS: dict = {"quando": 0.0, "lista": []}


def _nome_da_pessoa(pessoa: dict) -> str:
    """O cadastro guarda nome e sobrenome separados nas pessoas fisicas."""
    inteiro = " ".join(
        str(pessoa.get(campo) or "").strip()
        for campo in ("nome", "sobrenome")
    ).strip()
    return inteiro or str(pessoa.get("razaoSocial") or "").strip()


def _todas_as_pessoas_fisicas() -> list:
    """LEITURA. Cadastro de pessoas fisicas, com o mesmo cache curto dos
    veiculos - a busca por nome nao tem filtro documentado na API, entao a
    comparacao e local."""
    agora = time.time()
    if _CACHE_PESSOAS["lista"] and agora - _CACHE_PESSOAS["quando"] < VALIDADE_CACHE_SEGUNDOS:
        return _CACHE_PESSOAS["lista"]

    todas = _paginar("/pessoas/v1/pessoas/fisicas")
    _CACHE_PESSOAS.update({"quando": agora, "lista": todas})
    return todas


def buscar_pessoas_por_nome(termo: str, limite: int = 25) -> list:
    """LEITURA. Pessoas fisicas cujo nome contem o termo.

    E a lupa da tela: quando o CPF do agendamento nao acha ninguem, da pra
    procurar o motorista pelo nome.
    """
    alvo = (termo or "").strip().upper()
    if len(alvo) < 3:
        return []

    # `descricao` e o filtro documentado de pessoas fisicas: resolve no
    # servidor, sem depender de ter o cadastro inteiro em memoria.
    try:
        candidatas = listar("/pessoas/v1/pessoas/fisicas", {"descricao": termo.strip()})
    except BsoftError:
        candidatas = []
    if not candidatas:
        candidatas = _todas_as_pessoas_fisicas()

    achadas = []
    for pessoa in candidatas:
        nome = _nome_da_pessoa(pessoa)
        if alvo in nome.upper():
            achadas.append({
                "id": pessoa.get("id"),
                "nome": nome,
                "cpf": pessoa.get("cpf", ""),
            })
            if len(achadas) >= limite:
                break
    return achadas


def listar_chaves_nfes_recebidas(data_inicio: str, data_fim: str, ator: str = "TRA") -> list:
    """LEITURA. Chaves das NF-e recebidas no periodo.

    A documentacao exige dataInicio e dataFim com no maximo 3 meses de
    intervalo. O ator TRA filtra as notas em que a Atlantico aparece como
    transportadora - que sao justamente as que viram CT-e.
    """
    return listar(
        "/eDoc/v1/chavesDeAcesso/NFesRecebidas",
        {"dataInicio": data_inicio, "dataFim": data_fim, "ator": ator},
    )


def obter_xml_nfes_recebidas(chaves: list[str]) -> object:
    """LEITURA. XML das NF-e recebidas. Maximo de 50 chaves por requisicao."""
    if len(chaves) > 50:
        raise ValueError("A consulta aceita no maximo 50 chaves por requisicao")
    _, corpo = chamar(
        "POST",
        "/eDoc/v1/XMLDocumentosFiscais/NFesRecebidas",
        json_body={"chaveAcesso": list(chaves)},
    )
    return corpo


def listar_conjuntos_veiculos() -> list:
    """LEITURA. Conjuntos cadastrados: motorista, cavalo e carretas juntos.

    E a forma mais pratica de preencher o CT-e: escolher o motorista traz
    as placas dele, em vez de digitar uma a uma. A API tambem aceita os
    veiculos avulsos, mas exige um dos dois caminhos.
    """
    conjuntos = []
    for item in listar("/transporte/v1/conjuntoVeiculos"):
        placas = [item.get(campo) for campo in ("veiculo", "central", "carreta", "quartoVeiculo")]
        placas = [p for p in placas if p]
        conjuntos.append({
            "id": item.get("id"),
            "motorista": (item.get("motorista") or "").strip(),
            "placas": placas,
            "descricao": " · ".join([(item.get("motorista") or "sem motorista").strip()] + placas),
        })
    return conjuntos
