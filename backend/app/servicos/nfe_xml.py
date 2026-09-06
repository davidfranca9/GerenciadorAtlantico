"""Leitura local do XML da NF-e.

Extrai os dados que alimentam o CT-e sem depender do Bsoft. Serve pra
validar o arquivo e barrar emissao duplicada ANTES de qualquer chamada
externa.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

# Unidades comerciais que indicam que o emitente declarou o peso em
# toneladas em vez de kg. Ver _analisar_peso.
UNIDADES_EM_TONELADA = {"TON", "TONELADA", "T", "TN"}


class NFeInvalida(Exception):
    pass


def _texto(no, caminho: str) -> str:
    if no is None:
        return ""
    achado = no.find(caminho, NS)
    return (achado.text or "").strip() if achado is not None else ""


def _decimal(valor: str):
    try:
        return Decimal(valor)
    except (InvalidOperation, TypeError):
        return None


def chave_valida(chave: str) -> bool:
    """Valida os 44 digitos pelo digito verificador (modulo 11), o mesmo
    calculo da SEFAZ. Evita aceitar chave digitada errada."""
    chave = re.sub(r"\D", "", chave or "")
    if len(chave) != 44:
        return False
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = 0
    for i, digito in enumerate(reversed(chave[:43])):
        soma += int(digito) * pesos[i % 8]
    resto = soma % 11
    dv = 0 if resto in (0, 1) else 11 - resto
    return dv == int(chave[43])


def _analisar_peso(peso_bruto: str, unidade: str, quantidade: str) -> dict:
    """Descobre se o peso da nota esta em kg ou em tonelada.

    O layout da NF-e manda pesoB em kg, mas nem todo ERP respeita: quando o
    produto e vendido em TON, alguns emitem pesoB igual a quantidade (27.000
    para 27 toneladas). Mandar esse 27 pra um campo em kg viraria uma carga
    de 27 kg no CT-e.

    Aqui a gente so DETECTA e avisa. A conversao nao acontece sozinha porque
    o CT-e tem que sair igual ao que e digitado hoje, e isso quem confirma e
    quem opera.
    """
    bruto = _decimal(peso_bruto)
    quant = _decimal(quantidade)
    unidade_em_tonelada = (unidade or "").strip().upper() in UNIDADES_EM_TONELADA
    # O sinal forte: unidade em tonelada E peso igual a quantidade vendida.
    em_tonelada = bool(unidade_em_tonelada and bruto is not None and bruto == quant)
    return {
        "peso_declarado": peso_bruto,
        "unidade_produto": unidade,
        "peso_provavelmente_em_tonelada": em_tonelada,
        "peso_kg_equivalente": str(bruto * 1000) if em_tonelada and bruto is not None else "",
    }


def extrair_mercadoria(xml_bytes: bytes) -> dict:
    """Monta a linha de mercadoria do CT-e a partir da NF-e.

    Os valores fiscais sao TRANSCRITOS da nota, nunca calculados: sao os
    mesmos campos que aparecem na secao Documentos da tela do Bsoft (BC de
    ICMS, Valor do ICMS, BC de ICMS-ST, Valor ICMS-ST, CFOP, NCM, peso).
    Recalcular por conta propria e exatamente o que faria o documento sair
    diferente do que sai hoje.
    """
    raiz = ElementTree.fromstring(xml_bytes)
    inf = raiz.find(".//nfe:infNFe", NS)
    if inf is None:
        raise NFeInvalida("XML nao parece ser de uma NF-e (infNFe nao encontrado)")

    ide = inf.find("nfe:ide", NS)
    total = inf.find(".//nfe:ICMSTot", NS)
    vol = inf.find(".//nfe:vol", NS)
    primeiro_item = inf.find("nfe:det", NS)
    prod = primeiro_item.find("nfe:prod", NS) if primeiro_item is not None else None

    # O CST fica dentro do grupo de tributacao (ICMS00, ICMS20, ICMS60...),
    # que muda de nota pra nota. Pega o primeiro CST que existir sob o ICMS.
    cst = ""
    if primeiro_item is not None:
        achado = primeiro_item.find(".//nfe:ICMS//nfe:CST", NS)
        cst = (achado.text or "").strip() if achado is not None else ""

    dados = {
        "chaveNFe": re.sub(r"\D", "", inf.attrib.get("Id", "")),
        "notaFiscal": _texto(ide, "nfe:nNF"),
        "serieNotaFiscal": _texto(ide, "nfe:serie"),
        "dtFiscal": _texto(ide, "nfe:dhEmi")[:10],
        "tipoNF": "S" if _texto(ide, "nfe:tpNF") == "1" else "E",
        "nCFOP": _texto(prod, "nfe:CFOP"),
        "NCM": _texto(prod, "nfe:NCM"),
        "CST": cst,
        "quant": _texto(vol, "nfe:qVol") or _texto(prod, "nfe:qCom"),
        "especie": _texto(vol, "nfe:esp"),
        "marca": _texto(vol, "nfe:marca"),
        "vProd": _texto(total, "nfe:vProd"),
        "vBC": _texto(total, "nfe:vBC"),
        "vICMS": _texto(total, "nfe:vICMS"),
        "vBCST": _texto(total, "nfe:vBCST"),
        "vST": _texto(total, "nfe:vST"),
        "valor": _texto(total, "nfe:vNF"),
        "descricao_produto": _texto(prod, "nfe:xProd"),
    }
    dados.update(
        _analisar_peso(
            _texto(vol, "nfe:pesoB"),
            _texto(prod, "nfe:uCom"),
            _texto(prod, "nfe:qCom"),
        )
    )
    return dados


def extrair_dados(xml_bytes: bytes) -> dict:
    """Devolve os dados da NF-e. Levanta NFeInvalida se o arquivo nao for
    uma NF-e legivel ou se a chave nao passar no digito verificador."""
    try:
        raiz = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        raise NFeInvalida(f"Arquivo nao e um XML valido: {exc}") from exc

    inf = raiz.find(".//nfe:infNFe", NS)
    if inf is None:
        raise NFeInvalida("XML nao parece ser de uma NF-e (infNFe nao encontrado)")

    chave = re.sub(r"\D", "", inf.attrib.get("Id", ""))
    if not chave_valida(chave):
        raise NFeInvalida("Chave de acesso da NF-e invalida (digito verificador nao confere)")

    ide = inf.find("nfe:ide", NS)
    emit = inf.find("nfe:emit", NS)
    dest = inf.find("nfe:dest", NS)
    total = inf.find(".//nfe:ICMSTot", NS)
    transp = inf.find(".//nfe:vol", NS)
    ender_emit = emit.find("nfe:enderEmit", NS) if emit is not None else None
    ender_dest = dest.find("nfe:enderDest", NS) if dest is not None else None

    # O destinatario pode ser pessoa juridica ou fisica (produtor rural). O
    # cadastro no Bsoft e consultado por endpoint diferente em cada caso.
    cnpj_dest = _texto(dest, "nfe:CNPJ")
    cpf_dest = _texto(dest, "nfe:CPF")

    return {
        "chave": chave,
        "numero": _texto(ide, "nfe:nNF"),
        "serie": _texto(ide, "nfe:serie"),
        "emissao": _texto(ide, "nfe:dhEmi")[:10],
        "emitente_cnpj": _texto(emit, "nfe:CNPJ"),
        "emitente_nome": _texto(emit, "nfe:xNome"),
        "municipio_origem": _texto(ender_emit, "nfe:xMun"),
        "ibge_origem": _texto(ender_emit, "nfe:cMun"),
        "uf_origem": _texto(ender_emit, "nfe:UF"),
        "destinatario_doc": cnpj_dest or cpf_dest,
        "destinatario_tipo": "juridica" if cnpj_dest else ("fisica" if cpf_dest else ""),
        "destinatario_nome": _texto(dest, "nfe:xNome"),
        "municipio_destino": _texto(ender_dest, "nfe:xMun"),
        "ibge_destino": _texto(ender_dest, "nfe:cMun"),
        "uf_destino": _texto(ender_dest, "nfe:UF"),
        # modFrete 1 = por conta do destinatario (FOB). Define quem e o
        # tomador do CT-e, entao segue junto.
        "modalidade_frete": _texto(inf.find(".//nfe:transp", NS), "nfe:modFrete"),
        "transportadora_cnpj": _texto(inf.find(".//nfe:transporta", NS), "nfe:CNPJ"),
        "valor_produtos": _texto(total, "nfe:vProd"),
        "valor_nota": _texto(total, "nfe:vNF"),
        "peso_bruto": _texto(transp, "nfe:pesoB"),
    }
