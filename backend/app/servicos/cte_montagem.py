"""Deriva os campos do CT-e a partir da NF-e.

Cada regra aqui foi conferida contra um documento real: a NF-e 158852 da
FERTIMAXI e o CT-e 5053 que a Atlantico emitiu pra ela (BA -> MG,
05/09/2026). O teste dourado em tests/test_cte_5053.py reproduz esse par.

Nada aqui inventa valor fiscal. O ICMS do CT-e quem calcula e o Bsoft, a
partir do CFOP e da base que a gente manda - conferido no DACTE 5053:
base 8.100,00 com aliquota 12% deu ICMS 972,00.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from ..config import settings
from . import nfe_xml

# Limite do campo "produto predominante" do CT-e. O DACTE 5053 mostra a
# descricao da nota cortada exatamente aqui.
TAMANHO_PRODUTO_PREDOMINANTE = 50

# modFrete da NF-e -> quem e o tomador do servico no CT-e. Conferido no
# 5053: modFrete 1 (por conta do destinatario) gerou tomador = ELTON, o
# destinatario da nota.
TOMADOR_POR_MODALIDADE = {
    "0": "remetente",
    "1": "destinatario",
    "3": "remetente",
    "4": "destinatario",
}

# Quem paga o frete (campo pagamentoFrete). Sai da mesma informacao que
# define o tomador, porque e a mesma pergunta: de quem e a conta.
# R = remetente, D = destinatario.
PAGAMENTO_POR_TOMADOR = {"remetente": "R", "destinatario": "D"}


# Especies cadastradas no tenant. A especie nao vem da NF-e: sai da
# embalagem do pedido.
#
# Todos os ids foram lidos do combo especieId, no formulario de emissao de
# CT-e do Bsoft. (Seis deles eu tinha deduzido pela posicao na lista antes
# de conseguir ler a tela; a leitura confirmou os seis.)
ESPECIES_BSOFT = {
    1: "GRANEL",
    3: "SACOS",
    4: "FARDOS",
    5: "BIG BAG",
    6: "PALLETS",
    7: "CAIXAS",
    8: "SACO DE 50 KG",
    9: "Saco de 20kg",
    10: "BIG BAG 1000 KG",
    11: "SACO DE 25 KG",
    12: "SC X 25 KG",
    13: "Tonelada",
    14: "SACOS 50 KG",
}

# A quantidade do CT-e e o numero de volumes fisicos, e a especie e um
# rotulo do cadastro: BIG BAG 1000 KG nao quer dizer que cada volume pese
# 1000 kg. Foi assim no CT-e 5053 (540 volumes, 27 t) e e a convencao da
# operacao - por isso nao existe conferencia de volume x peso aqui.

# O OCR normaliza toda embalagem de pedido pra este vocabulario (ver
# servicos/ocr.py). E so isso que chega aqui, entao o de-para e direto e
# fica num lugar so, em vez de espalhado em heuristica de texto.
EMBALAGEM_PARA_ESPECIE = {
    "GRANEL": 1,
    "BIG BAG": 10,
    "SACARIA": 8,
}


class DadosInsuficientes(Exception):
    pass


def sugerir_especie(embalagem: str, especie_id=None) -> dict:
    """Traduz a embalagem do pedido pra especie do cadastro do Bsoft.

    Quando a especie e escolhida na tela, ela vence a embalagem: e o mesmo
    comportamento do Bsoft, onde o campo e um combo que o operador ajusta.
    """
    if especie_id:
        escolhida = int(especie_id)
        if escolhida in ESPECIES_BSOFT:
            return {
                "especie_id": escolhida,
                "nome": ESPECIES_BSOFT[escolhida],
                "alternativas": [],
                "confianca": "alta",
            }

    texto = (embalagem or "").strip().upper()
    if not texto:
        return {"especie_id": None, "nome": "", "alternativas": [], "confianca": "nenhuma"}

    especie_id = EMBALAGEM_PARA_ESPECIE.get(texto)
    if especie_id:
        return {
            "especie_id": especie_id,
            "nome": ESPECIES_BSOFT[especie_id],
            "alternativas": [],
            "confianca": "alta",
        }

    # Embalagem digitada na mao, fora do vocabulario do OCR: aceita quando
    # for o nome exato de uma especie do cadastro.
    for candidato, nome in ESPECIES_BSOFT.items():
        if texto == nome.upper():
            return {"especie_id": candidato, "nome": nome, "alternativas": [], "confianca": "alta"}

    return {"especie_id": None, "nome": "", "alternativas": [], "confianca": "nenhuma"}


def _duas_casas(valor: Decimal) -> str:
    return str(valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def peso_em_kg(mercadoria: dict) -> Decimal:
    """Devolve o peso da carga em kg.

    A NF-e da Fertimaxi declara o peso na unidade do produto (TON), entao
    27.000 significa 27 toneladas. O CT-e 5053 registrou 27.000,0000 KG
    pra essa mesma nota, ou seja: a conversao acontece mesmo, e sem ela a
    carga sairia mil vezes menor.
    """
    bruto = Decimal(mercadoria.get("peso_declarado") or "0")
    if mercadoria.get("peso_provavelmente_em_tonelada"):
        return bruto * 1000
    return bruto


def peso_em_toneladas(mercadoria: dict) -> Decimal:
    return peso_em_kg(mercadoria) / 1000


def derivar(
    xml_bytes: bytes,
    *,
    tarifa_por_tonelada: str | None = None,
    embalagem: str = "",
    especie_id=None,
) -> dict:
    """Monta o espelho do CT-e a partir do XML da NF-e.

    A tarifa e digitada por quem emite (a regra 35 so multiplica tarifa x
    tonelada), entao entra como parametro e nunca e chutada: sem ela o
    espelho simplesmente nao calcula frete. No 5053 foram R$ 300,00 x 27 t
    = R$ 8.100,00.

    A embalagem vem do pedido e define a especie da carga - tambem nao sai
    da nota.
    """
    dados = nfe_xml.extrair_dados(xml_bytes)
    mercadoria = nfe_xml.extrair_mercadoria(xml_bytes)

    modalidade = dados.get("modalidade_frete") or ""
    tomador = TOMADOR_POR_MODALIDADE.get(modalidade, "")

    kg = peso_em_kg(mercadoria)
    toneladas = peso_em_toneladas(mercadoria)

    espelho = {
        "chaves_nfe": [dados["chave"]],
        "numero_nfe": dados["numero"],
        # Remetente e destinatario do CT-e sao os da nota, sem alteracao.
        "remetente_doc": dados["emitente_cnpj"],
        "remetente_nome": dados["emitente_nome"],
        "destinatario_doc": dados["destinatario_doc"],
        "destinatario_nome": dados["destinatario_nome"],
        "destinatario_tipo": dados["destinatario_tipo"],
        "tomador": tomador,
        "tomador_doc": dados["destinatario_doc"] if tomador == "destinatario" else dados["emitente_cnpj"],
        "ibge_origem": dados["ibge_origem"],
        "cep_origem": dados["cep_origem"],
        "municipio_origem": dados["municipio_origem"],
        "uf_origem": dados["uf_origem"],
        "ibge_destino": dados["ibge_destino"],
        "cep_destino": dados["cep_destino"],
        "municipio_destino": dados["municipio_destino"],
        "uf_destino": dados["uf_destino"],
        "produto_predominante": mercadoria["descricao_produto"][:TAMANHO_PRODUTO_PREDOMINANTE].rstrip(),
        "valor_mercadoria": mercadoria["valor"],
        "peso_kg": str(kg),
        "quantidade": mercadoria["quant"],
        "peso_convertido_de_tonelada": bool(mercadoria.get("peso_provavelmente_em_tonelada")),
        "especie": sugerir_especie(embalagem, especie_id),
        "embalagem_do_pedido": embalagem,
        # Guardado inteiro porque e daqui que sai a linha de mercadorias[]
        # do payload, com os valores fiscais transcritos da nota.
        "mercadoria": mercadoria,
    }

    if tarifa_por_tonelada:
        frete = toneladas * Decimal(str(tarifa_por_tonelada))
        espelho["tarifa_por_tonelada"] = _duas_casas(Decimal(str(tarifa_por_tonelada)))
        espelho["valor_frete"] = _duas_casas(frete)
        espelho["base_calculo"] = _duas_casas(frete)

    espelho["pendencias"] = _pendencias(espelho, mercadoria, tarifa_por_tonelada)
    espelho["avisos"] = _avisos(espelho, mercadoria)
    return espelho


def _pendencias(espelho: dict, mercadoria: dict, tarifa: str | None) -> list[str]:
    """O que IMPEDE a emissao. Aviso que so pede atencao vai em _avisos."""
    faltando = []
    if not tarifa:
        faltando.append(
            "Tarifa por tonelada nao informada: e ela que multiplica o peso pra dar o "
            "frete (no CT-e 5053 foram R$ 300,00/t x 27 t = R$ 8.100,00)."
        )
    if not espelho["tomador"]:
        faltando.append(
            f"Modalidade de frete {mercadoria.get('modalidade_frete', '')!r} nao mapeada: "
            "o tomador do servico precisa ser confirmado."
        )
    # A especie da carga nao vem da nota: o 5053 usou BIG BAG 1000 KG
    # enquanto a NF-e trazia BAGS. Ela sai da embalagem do pedido.
    especie = espelho["especie"]
    if especie["confianca"] == "nenhuma":
        embalagem = espelho["embalagem_do_pedido"]
        faltando.append(
            f"Especie da carga indefinida: a embalagem do pedido "
            f"({embalagem or 'nao informada'}) nao casou com nenhuma especie do Bsoft."
        )
    return faltando


def _avisos(espelho: dict, mercadoria: dict) -> list[str]:
    """O que vale conferir mas nao impede a emissao.

    A conversao de peso entra aqui: ela esta certa (o CT-e 5053 registrou os
    mesmos 27000 kg), so merece um olhar. Misturada com as pendencias, ela
    travava o botao de emitir sem nada de fato pendente.
    """
    recados = []
    if espelho["peso_convertido_de_tonelada"]:
        recados.append(
            f"Peso convertido de {mercadoria['peso_declarado']} t para {espelho['peso_kg']} kg, "
            "porque a nota declara o peso na unidade do produto."
        )
    return recados


# --------------------------------------------------------------------------
# Resolucao das partes (remetente e destinatario) no cadastro do Bsoft
# --------------------------------------------------------------------------


def _so_digitos(texto) -> str:
    return "".join(c for c in str(texto or "") if c.isdigit())


# O cadastro de enderecos nao esta documentado campo a campo, e o nome do
# CEP varia. Tentar so "cep" fazia o desempate falhar em silencio.
CAMPOS_CEP = ("cep", "CEP", "codigoPostal", "cepEndereco", "enderecoCep")


def _cep_do_endereco(endereco: dict) -> str:
    for campo in CAMPOS_CEP:
        digitos = _so_digitos(endereco.get(campo))
        if len(digitos) == 8:
            return digitos
    return ""


def _descrever(endereco: dict) -> str:
    partes = [endereco.get("logradouro"), endereco.get("numero"), endereco.get("bairro")]
    linha = ", ".join(str(x) for x in partes if x)
    cep = _cep_do_endereco(endereco)
    return f"{linha} - CEP {cep}" if cep else linha or f"endereco {endereco.get('id')}"


def _escolher_endereco(enderecos: list, ibge: str, cep: str = "") -> tuple:
    """Escolhe o endereco que corresponde ao da NF-e.

    Primeiro o codigo IBGE, que restringe ao municipio. Se sobrar mais de
    um, o CEP desempata - a nota traz o CEP de cada parte, entao a escolha
    continua vindo do documento e nao de chute. So depois disso entra o
    marcado como preferencial.

    Devolve tambem as candidatas, pra quem opera poder escolher na tela
    quando nem assim der pra decidir.
    """
    if not enderecos:
        return None, "Pessoa sem endereco cadastrado no Bsoft.", []

    ibge = (ibge or "").strip()
    if not ibge:
        return None, "NF-e sem codigo IBGE do municipio: nao da pra escolher o endereco.", []

    candidatos = [e for e in enderecos if str(e.get("codIBGE") or "").strip() == ibge]
    if not candidatos:
        cidades = ", ".join(str(e.get("cidade") or "?") for e in enderecos[:5])
        return None, (
            f"Nenhum endereco cadastrado no municipio {ibge} da NF-e "
            f"(cadastrados: {cidades})."
        ), enderecos

    if len(candidatos) > 1 and _so_digitos(cep):
        por_cep = [e for e in candidatos if _cep_do_endereco(e) == _so_digitos(cep)]
        if len(por_cep) == 1:
            return por_cep[0], "", candidatos
        if por_cep:
            candidatos = por_cep

    if len(candidatos) > 1:
        preferenciais = [e for e in candidatos if str(e.get("enderecoPreferencial")).upper() == "S"]
        if len(preferenciais) == 1:
            return preferenciais[0], "", candidatos
        return None, (
            f"{len(candidatos)} enderecos possiveis no municipio da NF-e: "
            "escolha qual o CT-e deve usar."
        ), candidatos

    return candidatos[0], "", candidatos


def resolver_parte(
    documento: str,
    ibge: str,
    *,
    buscar_pessoa,
    listar_enderecos,
    cep: str = "",
    endereco_id=None,
) -> dict:
    """Traduz documento + municipio da NF-e nos ids do cadastro do Bsoft.

    As buscas entram por parametro pra esta funcao poder ser testada sem
    tocar na API.
    """
    resultado = {
        "documento": documento,
        "pessoa_id": None,
        "endereco_id": None,
        "nome": "",
        "aviso": "",
        "enderecos": [],
    }
    if not documento:
        resultado["aviso"] = "Documento nao informado na NF-e."
        return resultado

    pessoa = buscar_pessoa(documento)
    if not pessoa:
        resultado["aviso"] = f"Documento {documento} nao esta cadastrado no Bsoft."
        return resultado

    resultado["pessoa_id"] = pessoa.get("id")
    resultado["nome"] = pessoa.get("nome") or pessoa.get("razaoSocial") or ""

    disponiveis = listar_enderecos(pessoa["id"])
    endereco, aviso, candidatos = _escolher_endereco(disponiveis, ibge, cep)
    resultado["enderecos"] = [
        {"id": e.get("id"), "descricao": _descrever(e)} for e in (candidatos or disponiveis)
    ]

    # Escolha feita na tela vence a automatica.
    if endereco_id:
        resultado["endereco_id"] = str(endereco_id)
        resultado["aviso"] = ""
        return resultado

    if endereco:
        resultado["endereco_id"] = endereco.get("id")
    resultado["aviso"] = aviso
    return resultado


def resolver_partes(
    espelho: dict,
    *,
    buscar_pessoa,
    listar_enderecos,
    endereco_remetente_id=None,
    endereco_destinatario_id=None,
) -> dict:
    """Resolve remetente e destinatario de uma vez, a partir do espelho."""
    remetente = resolver_parte(
        espelho["remetente_doc"], espelho["ibge_origem"],
        buscar_pessoa=buscar_pessoa, listar_enderecos=listar_enderecos,
        cep=espelho.get("cep_origem", ""), endereco_id=endereco_remetente_id,
    )
    destinatario = resolver_parte(
        espelho["destinatario_doc"], espelho["ibge_destino"],
        buscar_pessoa=buscar_pessoa, listar_enderecos=listar_enderecos,
        cep=espelho.get("cep_destino", ""), endereco_id=endereco_destinatario_id,
    )
    pendencias = []
    if remetente["aviso"]:
        pendencias.append(f"Remetente: {remetente['aviso']}")
    if destinatario["aviso"]:
        pendencias.append(f"Destinatario: {destinatario['aviso']}")
    return {
        "remetente": remetente,
        "destinatario": destinatario,
        "pendencias": pendencias,
        "completo": bool(
            remetente["pessoa_id"] and remetente["endereco_id"]
            and destinatario["pessoa_id"] and destinatario["endereco_id"]
        ),
    }


# --------------------------------------------------------------------------
# Payload do POST /transporte/v1/conhecimentos
#
# Os nomes de campo abaixo saem da colecao oficial (docs.bsoft.app), request
# "Transporte / Conhecimentos / Inserir". Nenhum foi inventado. Os que a
# operacao nao usa ficam de fora do payload em vez de irem preenchidos no
# chute - o exemplo da documentacao traz valor pra tudo, mas a maior parte e
# so ilustrativa.
# --------------------------------------------------------------------------

# Constantes lidas da tela de emissao e conferidas no DACTE 5053.
MODAL_RODOVIARIO = "R"          # unica opcao do combo dados_modalidade
TIPO_DOCUMENTO_NFE = "N"        # radio "NF-e" na tela
RESP_SEGURO_EMITENTE = "4"      # "Emi - Emitente"
CST_TRIBUTACAO_NORMAL = "000"   # DACTE 5053: "00 - Tributacao normal"
TIPO_CTE_NORMAL = "0"           # DACTE 5053: "TIPO DO CT-E Normal"
TIPO_SERVICO_NORMAL = "0"       # DACTE 5053: "TIPO DO SERVICO Normal"

# forPag do CT-e: 0 = pago, 1 = a pagar, 2 = outros.
FORMA_PAGAMENTO_A_PAGAR = "1"


def montar_payload_conhecimento(
    espelho: dict,
    *,
    partes: dict,
    veiculos: dict | None = None,
    aliquota_icms: str | None = None,
    rascunho: bool = True,
    agencia_id=None,
    talao_id=None,
    regra_frete_id=None,
    cfops_id=None,
    numero_apolice=None,
    natureza_carga_id=None,
    seguradora_id=None,
    apolice_id=None,
    km: str = "",
    forma_pagamento: str = "",
    dt_emissao: str = "",
) -> dict:
    """Monta o corpo do POST /conhecimentos.

    Sai como rascunho por padrao. A aliquota de ICMS e informada por quem
    emite, igual a tarifa: a funcao so multiplica pela base (no 5053,
    8.100,00 a 12% deu os 972,00 do DACTE), nunca escolhe a aliquota.
    """
    veiculos = veiculos or {}
    mercadoria = espelho.get("mercadoria") or {}
    valor = espelho.get("valor_frete", "")

    base = Decimal(valor) if valor else Decimal("0")
    if aliquota_icms:
        valor_icms = _duas_casas(base * Decimal(str(aliquota_icms)) / 100)
    else:
        valor_icms = ""

    agencia = str(agencia_id if agencia_id is not None else settings.bsoft_agencia_id)
    corpo = {
        "agencias_id": agencia,
        # A tela de emissao preenche a agencia de comissao com a mesma
        # agencia, entao o payload faz igual.
        "agenciasComissao_id": agencia,
        "tiposTaloes_id": str(talao_id if talao_id is not None else settings.bsoft_talao_cte_id),
        "regraFrete_id": str(regra_frete_id if regra_frete_id is not None else settings.bsoft_regra_frete_id),
        "cfops_id": str(cfops_id if cfops_id is not None else settings.bsoft_cfops_id_interestadual),
        "numeroApolice": str(numero_apolice if numero_apolice is not None else settings.bsoft_numero_apolice),
        "seguradora_id": str(seguradora_id if seguradora_id is not None else settings.bsoft_seguradora_id),
        "apolice_id": str(apolice_id if apolice_id is not None else settings.bsoft_apolice_id),
        # Quilometragem do trecho: nao sai da NF-e nem do cadastro, e
        # informada por viagem.
        "km": str(km or ""),
        # Quem paga o frete, derivado do mesmo modFrete que define o tomador.
        "pagamentoFrete": PAGAMENTO_POR_TOMADOR.get(espelho.get("tomador", ""), ""),
        "dtEmissao": dt_emissao or datetime.now().strftime("%Y-%m-%d %H:%M"),
        "rascunho": "S" if rascunho else "N",
        "modalidade": MODAL_RODOVIARIO,
        # Explicitos em vez de contar com o padrao do Bsoft: os dois saem
        # impressos no DACTE, entao e coisa que da pra conferir.
        "tpCTe": TIPO_CTE_NORMAL,
        "tpServ": TIPO_SERVICO_NORMAL,
        "tipoDocumentos": TIPO_DOCUMENTO_NFE,
        "respSeg": RESP_SEGURO_EMITENTE,
        "cteOS": "N",
        "globalizado": "N",
        # O CST do CT-e e proprio: incide sobre o frete, nao sobre a
        # mercadoria. O da NF-e (20 no 5053) nao entra aqui.
        "CST": CST_TRIBUTACAO_NORMAL,
        "definirCSTManualmente": "S",
        # Partes, resolvidas no cadastro do Bsoft pelo IBGE do municipio.
        "remetente_id": str(partes.get("remetente", {}).get("pessoa_id") or ""),
        "enderecoRemetente_id": str(partes.get("remetente", {}).get("endereco_id") or ""),
        "destinatario_id": str(partes.get("destinatario", {}).get("pessoa_id") or ""),
        "enderecoDestinatario_id": str(partes.get("destinatario", {}).get("endereco_id") or ""),
        # Percurso, direto da NF-e.
        "UFIni": espelho.get("uf_origem", ""),
        "UFFim": espelho.get("uf_destino", ""),
        "cMunIni": espelho.get("ibge_origem", ""),
        "cMunFim": espelho.get("ibge_destino", ""),
        # Valores. A tarifa e digitada e a regra de frete multiplica pelo
        # peso - por isso tarifaDigitada e o valor por tonelada, nao o total.
        "tarifaDigitada": espelho.get("tarifa_por_tonelada", ""),
        "valorFrete": valor,
        "baseCalculo": espelho.get("base_calculo", ""),
        "totalPrestacao": valor,
        "totalServico": valor,
        "aliquota": str(aliquota_icms or ""),
        "valorICMS": valor_icms,
        # Forma de pagamento do servico. Obrigatorio: o Bsoft recusa o POST
        # sem ele ("Atributo obrigatorio [forPag]"). O DACTE 5053 mostra
        # VALOR A RECEBER, ou seja, frete a pagar - por isso o padrao e 1.
        # Fica ajustavel na tela porque e decisao de quem emite.
        "forPag": str(forma_pagamento or FORMA_PAGAMENTO_A_PAGAR),
        # Componentes que o DACTE 5053 nao traz: la so aparecem FRETE VALOR,
        # ICMS e TARIFA PESO. Vao zerados em vez de omitidos, porque campo
        # de valor ausente costuma ser recusado.
        "valorISS": "0.00",
        "valoresOutros": "0.00",
        "valorSeguroAduaneiro": "0.00",
        "valorPedagioConhecimento": "0.00",
        "valorSeguro": "0.00",
        "diaria": "0.00",
        "Gris": "0.00",
        "mercadorias": [_linha_mercadoria(espelho, mercadoria, natureza_carga_id)],
    }

    for campo, valor_id in (
        ("motorista_id", veiculos.get("motorista_id")),
        ("veiculos_id", veiculos.get("veiculo_id")),
        ("carreta_id", veiculos.get("carreta_id")),
        ("semireboque_id", veiculos.get("semireboque_id")),
    ):
        if valor_id:
            corpo[campo] = str(valor_id)

    return corpo


def _linha_mercadoria(espelho: dict, mercadoria: dict, natureza_carga_id) -> dict:
    """Uma linha de mercadorias[]: a NF-e transportada.

    Os valores fiscais sao copiados da nota. quantKg e em quilos - por isso
    a conversao de tonelada acontece antes de chegar aqui.
    """
    natureza = natureza_carga_id if natureza_carga_id is not None else settings.bsoft_natureza_carga_id
    return {
        "chaveNFe": mercadoria.get("chaveNFe", ""),
        "notaFiscal": mercadoria.get("notaFiscal", ""),
        "serieNotaFiscal": mercadoria.get("serieNotaFiscal", ""),
        "dtFiscal": mercadoria.get("dtFiscal", ""),
        "tipoNF": mercadoria.get("tipoNF", ""),
        "especie": str(espelho.get("especie", {}).get("especie_id") or ""),
        "naturezaCarga": str(natureza),
        "quant": mercadoria.get("quant", ""),
        "quantKg": espelho.get("peso_kg", ""),
        "valor": mercadoria.get("valor", ""),
        "vProd": mercadoria.get("vProd", ""),
        "vBC": mercadoria.get("vBC", ""),
        "vICMS": mercadoria.get("vICMS", ""),
        "vBCST": mercadoria.get("vBCST", ""),
        "vST": mercadoria.get("vST", ""),
        "nCFOP": mercadoria.get("nCFOP", ""),
    }


def conferir_payload(corpo: dict) -> list[str]:
    """Diz o que impede este payload de virar um CT-e igual ao manual."""
    faltando = []
    obrigatorios = {
        "remetente_id": "Remetente nao encontrado no cadastro do Bsoft.",
        "enderecoRemetente_id": "Endereco do remetente nao resolvido.",
        "destinatario_id": "Destinatario nao encontrado no cadastro do Bsoft.",
        "enderecoDestinatario_id": "Endereco do destinatario nao resolvido.",
        "valorFrete": "Valor do frete ausente (falta a tarifa).",
        "aliquota": "Aliquota de ICMS nao informada.",
        "pagamentoFrete": "Nao deu pra saber quem paga o frete (modalidade da NF-e nao mapeada).",
        "km": "Quilometragem do trecho nao informada.",
        # apolice_id nao entra aqui: a documentacao marca o campo como
        # opcional. So a seguradora e obrigatoria.
        "seguradora_id": (
            f"Seguradora da apolice {settings.bsoft_numero_apolice} nao encontrada. "
            "Confira se a apolice esta cadastrada no Bsoft."
        ),
    }
    for campo, mensagem in obrigatorios.items():
        if not corpo.get(campo):
            faltando.append(mensagem)

    linha = (corpo.get("mercadorias") or [{}])[0]
    if not linha.get("chaveNFe"):
        faltando.append("Chave da NF-e ausente na linha de mercadorias.")
    if not linha.get("especie"):
        faltando.append("Especie da carga nao definida (falta a embalagem do pedido).")
    if not linha.get("quantKg"):
        faltando.append("Peso da carga ausente.")
    return faltando
