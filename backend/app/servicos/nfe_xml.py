"""Leitura local do XML da NF-e.

Extrai o minimo necessario (chave, numero, serie, emitente, destinatario,
valor e peso) sem depender do Bsoft. Serve pra validar o arquivo e barrar
emissao duplicada ANTES de qualquer chamada externa.
"""
from __future__ import annotations

import re
from xml.etree import ElementTree

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}


class NFeInvalida(Exception):
    pass


def _texto(no, caminho: str) -> str:
    if no is None:
        return ""
    achado = no.find(caminho, NS)
    return (achado.text or "").strip() if achado is not None else ""


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


def extrair_mercadoria(xml_bytes: bytes) -> dict:
    """Monta a linha de mercadoria do CT-e a partir da NF-e.

    Todos os valores sao TRANSCRITOS da nota, nunca calculados: sao os
    mesmos campos que aparecem na secao Documentos da tela do Bsoft (BC de
    ICMS, Valor do ICMS, BC de ICMS-ST, Valor ICMS-ST, CFOP, NCM, peso).
    Calcular por conta propria e o que nao pode acontecer aqui.
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

    return {
        "chaveNFe": re.sub(r"\D", "", inf.attrib.get("Id", "")),
        "notaFiscal": _texto(ide, "nfe:nNF"),
        "serieNotaFiscal": _texto(ide, "nfe:serie"),
        "dtFiscal": _texto(ide, "nfe:dhEmi")[:10],
        "tipoNF": "S" if _texto(ide, "nfe:tpNF") == "1" else "E",
        "nCFOP": _texto(prod, "nfe:CFOP"),
        "NCM": _texto(prod, "nfe:NCM"),
        "quant": _texto(vol, "nfe:qVol") or _texto(prod, "nfe:qCom"),
        "quantKg": _texto(vol, "nfe:pesoB"),
        "vProd": _texto(total, "nfe:vProd"),
        "vBC": _texto(total, "nfe:vBC"),
        "vICMS": _texto(total, "nfe:vICMS"),
        "vBCST": _texto(total, "nfe:vBCST"),
        "vST": _texto(total, "nfe:vST"),
        "valor": _texto(total, "nfe:vNF"),
        "descricao_produto": _texto(prod, "nfe:xProd"),
    }


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

    return {
        "chave": chave,
        "numero": _texto(ide, "nfe:nNF"),
        "serie": _texto(ide, "nfe:serie"),
        "emissao": _texto(ide, "nfe:dhEmi")[:10],
        "emitente_cnpj": _texto(emit, "nfe:CNPJ"),
        "emitente_nome": _texto(emit, "nfe:xNome"),
        "destinatario_doc": _texto(dest, "nfe:CNPJ") or _texto(dest, "nfe:CPF"),
        "destinatario_nome": _texto(dest, "nfe:xNome"),
        "municipio_destino": _texto(dest.find("nfe:enderDest", NS) if dest is not None else None, "nfe:xMun"),
        "uf_destino": _texto(dest.find("nfe:enderDest", NS) if dest is not None else None, "nfe:UF"),
        "valor_produtos": _texto(total, "nfe:vProd"),
        "valor_nota": _texto(total, "nfe:vNF"),
        "peso_bruto": _texto(transp, "nfe:pesoB"),
    }
