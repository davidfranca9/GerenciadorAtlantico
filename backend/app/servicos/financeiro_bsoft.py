"""Carregamentos a partir do Bsoft: tudo o que foi emitido no mes, sem digitar.

- CT-e (listagem): numero, data, motorista, placa, remetente e destinatario.
- XML autorizado do CT-e: valor do frete, peso e cidade de destino. O frete
  que vale pro financeiro e o VALOR A RECEBER (vRec), nao o total do servico
  (vTPrest): em carga CIF o tomador retem o ICMS ST e paga a diferenca - foi
  o que o CT-e 5250 mostrou (servico 9.440,00, ST 1.132,80, a receber
  8.307,20). Sem ST os dois sao iguais e nada muda.
  CT-e COMPLEMENTAR (tpCTe = 1) nao e viagem: so acrescenta valor a um CT-e
  que ja existe - vem sem peso e aponta o complementado em infCTeComp/chCTe.
  O valor dele soma na carga do CT-e original e o numero entra na lista
  ("5263/5264" vira "5263/5264/5265/5266"), em vez de virar carga de 0 t.
  O XML de cancelamento, quando existe, marca a carga como cancelada.
- Contrato de frete ("RECIBO DE FRETE"): os CT-es que ele cobre - e isso que
  junta "5005/5006" numa carga so. O VALOR do contrato nao e o pago ao
  motorista (em setembro/2026 nao bateu nenhuma vez com a planilha): fica
  so como referencia.
- Carta frete (do proprio sistema): o frete do motorista de verdade - bateu
  com a planilha em todas as cargas que tinham carta.

No Bsoft e so LEITURA. Agenciamento, comissao e contratante nao existem la:
ficam para completar na tela.
"""
from __future__ import annotations

import base64
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from ..models import CarregamentoFinanceiro, CartaFreteEnviada, Cidade
from . import financeiro as fin
from .bsoft_client import chamar
from .financeiro_importacao import nome_legivel

logger = logging.getLogger(__name__)

TAMANHO_PAGINA = 100
MAX_PAGINAS = 30
CHAVES_POR_CONSULTA = 50  # limite do endpoint de XML

FABRICAS = (
    ("fertimaxi", "Fertimaxi"),
    ("heringer", "Heringer"),
    ("timac", "Timac"),
    ("yara", "Yara"),
    ("mosaic", "Mosaic"),
    ("fertipar", "Fertipar"),
)


# --------------------------------------------------------------------------
# Leitura no Bsoft
# --------------------------------------------------------------------------


def _listar_periodo(caminho: str, params: dict) -> list:
    """Listagem inteira do periodo. A paginacao do Bsoft e `limit=offset,qtd`
    (o `inicio` e ignorado em silencio); para em pagina incompleta ou repetida."""
    todos, vistos = [], set()
    for pagina in range(MAX_PAGINAS):
        _, dados = chamar("GET", caminho, params={**params, "limit": f"{pagina * TAMANHO_PAGINA},{TAMANHO_PAGINA}"})
        lote = dados if isinstance(dados, list) else ([dados] if dados else [])
        novos = [item for item in lote if str(item.get("id")) not in vistos]
        vistos.update(str(item.get("id")) for item in novos)
        todos.extend(novos)
        if len(lote) < TAMANHO_PAGINA or not novos:
            break
    return todos


def _valores_dos_contratos(ids: set[str]) -> dict[str, dict]:
    """Valores (frete do motorista, tarifa, peso) de cada contrato. A listagem
    vem do mais novo pro mais antigo: le paginas ate achar todos os ids."""
    achados: dict[str, dict] = {}
    if not ids:
        return achados
    menor = min(int(i) for i in ids if str(i).isdigit()) if any(str(i).isdigit() for i in ids) else 0
    for pagina in range(MAX_PAGINAS):
        _, dados = chamar("GET", "/transporte/v1/contratosFrete/valores",
                          params={"limit": f"{pagina * TAMANHO_PAGINA},{TAMANHO_PAGINA}"})
        lote = dados if isinstance(dados, list) else ([dados] if dados else [])
        for item in lote:
            if str(item.get("id")) in ids:
                achados[str(item.get("id"))] = item
        ids_da_pagina = [int(item["id"]) for item in lote if str(item.get("id", "")).isdigit()]
        if len(achados) == len(ids) or len(lote) < TAMANHO_PAGINA or (ids_da_pagina and min(ids_da_pagina) < menor):
            break
    return achados


def _texto_xml(conteudo) -> str:
    if not conteudo:
        return ""
    texto = str(conteudo).strip()
    if texto.startswith("<"):
        return texto
    try:
        return base64.b64decode(texto).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _xmls(chaves: list[str]) -> dict[str, dict]:
    """{chave: {"autorizacao": xml, "cancelamento": xml}}."""
    resultado: dict[str, dict] = {}
    for i in range(0, len(chaves), CHAVES_POR_CONSULTA):
        _, dados = chamar("POST", "/eDoc/v1/XMLDocumentosFiscais/CTesEmitidos",
                          json_body={"chaveAcesso": chaves[i:i + CHAVES_POR_CONSULTA], "obterXmlEventos": "S"})
        for item in dados if isinstance(dados, list) else ([dados] if dados else []):
            xml = item.get("xml") or {}
            resultado[str(item.get("chaveAcesso"))] = {
                "autorizacao": _texto_xml(xml.get("autorizacao")),
                "cancelamento": _texto_xml(xml.get("cancelamento")),
            }
    return resultado


# --------------------------------------------------------------------------
# XML do CT-e
# --------------------------------------------------------------------------


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _filho(no, nome):
    for el in no.iter():
        if _local(el.tag) == nome:
            return el
    return None


def _texto(no, nome) -> str:
    el = _filho(no, nome) if no is not None else None
    return (el.text or "").strip() if el is not None and el.text else ""


def _numero(texto) -> Optional[float]:
    try:
        return float(str(texto).replace(",", "."))
    except (TypeError, ValueError):
        return None


# tpCTe do layout do CT-e: 0 normal, 1 complemento de valores, 2 anulacao de
# valores, 3 substituto.
TIPO_COMPLEMENTO = "1"


def numero_da_chave(chave) -> str:
    """Numero do CT-e dentro da chave de acesso (44 digitos, mesmo desenho da
    NF-e): cUF(2) AAMM(4) CNPJ(14) mod(2) serie(3) nCT(9) tpEmis(1) cCT(8)
    cDV(1) - o numero fica da 26a a 34a casa. E assim que da pra saber qual
    CT-e um complemento complementa mesmo quando o original nao veio na
    listagem do periodo (complemento emitido no mes seguinte)."""
    digitos = re.sub(r"\D", "", str(chave or ""))
    return digitos[25:34].lstrip("0") if len(digitos) == 44 else ""


def _chave_complementada(raiz) -> str:
    """Chave do CT-e complementado. A tag e `infCTeComp` no layout 4.00 e
    `infCteComp` em outros, por isso a comparacao ignora maiuscula; dentro
    dela vale qualquer texto de 44 digitos (chCTe nos XML que vimos)."""
    for el in raiz.iter():
        if _local(el.tag).lower() != "infctecomp":
            continue
        for filho in el.iter():
            digitos = re.sub(r"\D", "", filho.text or "")
            if len(digitos) == 44:
                return digitos
    return ""


def ler_xml_cte(xml: str) -> dict:
    """Frete (o que se recebe), peso (t), destino e partes de um CT-e autorizado."""
    if not xml:
        return {}
    try:
        raiz = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    except ET.ParseError:
        return {}
    ide = _filho(raiz, "ide")
    peso = None
    medidas = [el for el in raiz.iter() if _local(el.tag) == "infQ"]
    # Peso: a medida em KG (01) ou TON (02), de preferencia a que diz "PESO".
    medidas.sort(key=lambda m: 0 if "PESO" in _texto(m, "tpMed").upper() else 1)
    for medida in medidas:
        unidade, quantidade = _texto(medida, "cUnid"), _numero(_texto(medida, "qCarga"))
        if quantidade is None:
            continue
        if unidade == "01":
            peso = quantidade / 1000
            break
        if unidade == "02":
            peso = quantidade
            break
    prest = _filho(raiz, "vPrest")
    # vTPrest e o "VALOR TOTAL DO SERVICO" do DACTE; vRec e o "VALOR A
    # RECEBER". Em carga CIF, com substituicao tributaria, o tomador retem o
    # ICMS ST e paga so o vRec - e esse o dinheiro que chega na Atlantico.
    # Sem ST o XML repete o mesmo numero nos dois campos.
    total_servico = _numero(_texto(prest, "vTPrest"))
    a_receber = _numero(_texto(prest, "vRec"))
    if a_receber is None:
        a_receber = total_servico
    desconto = None
    if total_servico is not None and a_receber is not None and total_servico - a_receber > 0.005:
        desconto = round(total_servico - a_receber, 2)
    tipo = _texto(ide, "tpCTe")
    # Complemento: o CT-e complementado vem na chave de acesso, nao no numero.
    chave_complementado = _chave_complementada(raiz) if tipo == TIPO_COMPLEMENTO else ""
    return {
        "numero": _texto(ide, "nCT"),
        "emissao": _texto(ide, "dhEmi")[:10],
        "tipo": tipo,
        "complemento": tipo == TIPO_COMPLEMENTO,
        "chave_complementado": chave_complementado,
        "numero_complementado": numero_da_chave(chave_complementado),
        "municipio_fim": _texto(ide, "xMunFim"),
        "ibge_fim": _texto(ide, "cMunFim"),
        "uf_fim": _texto(ide, "UFFim"),
        "remetente": _texto(_filho(raiz, "rem"), "xNome"),
        "destinatario": _texto(_filho(raiz, "dest"), "xNome"),
        # valor_frete e o que entra na conta: o valor a receber.
        "valor_frete": a_receber,
        "valor_total_servico": total_servico,
        "desconto_icms_st": desconto,
        "peso": round(peso, 3) if peso is not None else None,
    }


_PALAVRAS_DE_RAZAO_SOCIAL = {
    "ltda", "s/a", "sa", "s.a.", "s.a", "eireli", "me", "epp", "industria", "comercio", "e", "de", "do", "da", "dos",
    "das", "fertilizantes", "importacao", "exportacao", "agroindustria", "cia", "companhia",
}


def nome_da_fabrica(remetente: str) -> str:
    """ "MM AGRICOLA E COMERCIO LTDA" -> "MM Agricola"; "OLMA INDUSTRIA E..." -> "Olma"."""
    chave = fin.sem_acento(remetente)
    for trecho, nome in FABRICAS:
        if trecho in chave:
            return nome
    palavras = [p for p in str(remetente or "").split() if fin.sem_acento(p) not in _PALAVRAS_DE_RAZAO_SOCIAL]
    if not palavras:
        return nome_legivel(remetente)
    escolhidas = palavras[:2] if len(palavras[0]) <= 3 else palavras[:1]
    # Sigla curta fica em maiuscula ("MM Agricola", nao "Mm Agricola").
    return " ".join(p.upper() if len(p) <= 3 and p.isalpha() else nome_legivel(p) for p in escolhidas)


# --------------------------------------------------------------------------
# Montagem das cargas
# --------------------------------------------------------------------------


def _data(texto) -> Optional[date]:
    try:
        return datetime.strptime(str(texto)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _destino(lido: dict, cidades: dict) -> str:
    """Cidade de destino pelo cadastro (acento certo); sem cadastro, o que veio no XML."""
    cidade = cidades.get(lido.get("ibge_fim"))
    if cidade:
        return f"{cidade.nome} {cidade.uf}"
    return " ".join(p for p in (nome_legivel(lido.get("municipio_fim", "")), lido.get("uf_fim", "")) if p)


def _somar_complemento(carga: dict, numero: str, lido: dict) -> None:
    """Joga o CT-e complementar na carga do CT-e complementado: o valor entra
    no frete cobrado e o numero na lista de CT-e ("5263/5264/5265/5266").

    O PESO nao muda - complemento so acrescenta dinheiro, a tonelada ja foi
    contada no CT-e original. E justamente por isso que a sobra por tonelada
    da carga passa a sair certa: antes o valor ficava numa linha de 0 t."""
    carga["numeros"] = sorted(set(carga["numeros"]) | {numero}, key=int)
    carga["ctes"] = "/".join(carga["numeros"])
    carga["complementos"] = "/".join(sorted(set(re.findall(r"\d+", carga["complementos"])) | {numero}, key=int))
    for campo, valor in (("frete_empresa_total", lido.get("valor_frete")),
                         ("complemento_total", lido.get("valor_frete")),
                         ("frete_servico_total", lido.get("valor_total_servico")),
                         ("desconto_icms_st", lido.get("desconto_icms_st"))):
        if valor:
            carga[campo] = fin.dinheiro((carga.get(campo) or 0) + valor)


def _carga_so_do_complemento(numero: str, lido: dict, doc: dict, original: str, cidades: dict, *, cancelado: bool) -> dict:
    """Complemento que nao achou o CT-e original no periodo (o original e de
    outro mes, ou o complemento foi cancelado).

    Vira linha propria, no mes em que foi emitido, pra o dinheiro continuar na
    conta - e com o frete do motorista ja em ZERO, porque complemento nao tem
    viagem nova: quem puxou a carga foi pago no CT-e original. Assim a linha
    nao fica pedindo motorista; ela se apresenta como o complemento que e."""
    valor = lido.get("valor_frete")
    return {
        "numeros": [numero],
        "ctes": numero,
        "data_emissao": _data(doc.get("dtEmissao")) or _data(lido.get("emissao")),
        "motorista": ((doc.get("dados_motorista") or {}).get("motorista") or "").strip().upper(),
        "placa": (doc.get("dados_motorista") or {}).get("veiculo") or "",
        "fabrica": nome_da_fabrica(lido.get("remetente") or doc.get("remetente")),
        "cliente": " ".join(str(lido.get("destinatario") or doc.get("destinatario") or "").split()),
        "destino": _destino(lido, cidades),
        # Complemento nao traz tonelada: a carga ja foi pesada no CT-e original.
        "peso": 0,
        "frete_empresa_total": fin.dinheiro(valor) if valor is not None else None,
        "frete_servico_total": fin.dinheiro(lido["valor_total_servico"]) if lido.get("valor_total_servico") is not None else None,
        "desconto_icms_st": fin.dinheiro(lido["desconto_icms_st"]) if lido.get("desconto_icms_st") else None,
        "frete_motorista_total": 0,
        "carta_frete": None,
        "valor_contrato": None,
        "contrato": "",
        "cancelado": cancelado,
        "contratos_detalhe": [],
        "complementos": numero,
        "complemento_total": fin.dinheiro(valor) if valor is not None else None,
        "complemento_de": original,
    }


def cargas_do_periodo(db: Session, inicio: date, fim: date) -> dict:
    """Le o Bsoft e devolve as cargas do periodo (uma por contrato de frete)."""
    ctes = _listar_periodo("/transporte/v1/conhecimentos", {"dataInicio": inicio.isoformat(), "dataFim": fim.isoformat()})
    ctes = [c for c in ctes if str(c.get("nro", "")).isdigit() and c.get("chaveAcesso")]
    # O contrato costuma sair minutos (as vezes dias) depois do CT-e.
    contratos = _listar_periodo("/transporte/v1/contratosFrete", {
        "dataInicio": (inicio - timedelta(days=7)).isoformat(), "dataFim": (fim + timedelta(days=15)).isoformat(),
    })
    contratos = [c for c in contratos if str(c.get("statusCancelado", "N")).upper() != "S"]
    valores = _valores_dos_contratos({str(c.get("id")) for c in contratos})
    xmls = _xmls([c["chaveAcesso"] for c in ctes])

    por_numero = {str(c["nro"]): c for c in ctes}
    lidos = {numero: ler_xml_cte((xmls.get(c["chaveAcesso"]) or {}).get("autorizacao")) for numero, c in por_numero.items()}
    cancelados = {numero for numero, c in por_numero.items() if (xmls.get(c["chaveAcesso"]) or {}).get("cancelamento")}
    # Complemento nao e viagem: fica de fora da montagem das cargas e, no fim,
    # o valor dele e somado na carga do CT-e que ele complementa.
    complementos = {numero: lido for numero, lido in lidos.items() if lido.get("complemento")}
    por_chave = {str(c.get("chaveAcesso")): numero for numero, c in por_numero.items()}
    # Anulacao (tpCTe 2) e substituto (3) continuam entrando como carga normal,
    # que e o que o sistema sempre fez. Sao raros e a regra de qual valor vale
    # depende de como o Bsoft lista os dois: fica avisado no log pra conferir.
    especiais = sorted(n for n, l in lidos.items() if l.get("tipo") in ("2", "3"))
    if especiais:
        logger.warning("CT-e de anulacao/substituto no periodo (conferir na mao): %s", ", ".join(especiais))

    # Todos os contratos que citam cada CT-e (pra conferencia do frete do motorista).
    contratos_do_cte: dict[str, list] = {}
    for contrato in contratos:
        for n in contrato.get("nrosCTe") or []:
            contratos_do_cte.setdefault(str(n), []).append(contrato)

    # `usados` ja comeca com os complementos: nem o contrato de frete nem a
    # sobra do fim transformam um complemento em carga.
    grupos, usados = [], set(complementos)
    for contrato in sorted(contratos, key=lambda c: int(c["id"]) if str(c.get("id", "")).isdigit() else 0):
        numeros = [str(n) for n in contrato.get("nrosCTe") or [] if str(n) in por_numero and str(n) not in usados]
        if numeros:
            usados.update(numeros)
            grupos.append((contrato, numeros))
    grupos.extend((None, [numero]) for numero in por_numero if numero not in usados)

    ibges = {l.get("ibge_fim") for l in lidos.values() if l.get("ibge_fim")}
    cidades = {c.ibge: c for c in db.query(Cidade).filter(Cidade.ibge.in_(ibges)).all()} if ibges else {}

    cargas = []
    for contrato, numeros in grupos:
        numeros.sort(key=int)
        docs = [por_numero[n] for n in numeros]
        xml = [lidos[n] for n in numeros]
        primeiro = xml[0] if xml else {}
        valor = valores.get(str(contrato.get("id"))) if contrato else None
        motorista = ((docs[0].get("dados_motorista") or {}).get("motorista") or (contrato or {}).get("motorista") or "").strip().upper()
        destino = _destino(primeiro, cidades)
        pesos = [x.get("peso") for x in xml if x.get("peso")]
        fretes = [x.get("valor_frete") for x in xml if x.get("valor_frete") is not None]
        # Total do servico e desconto do ICMS ST somados do mesmo jeito que o
        # frete: uma carga pode ser 5005/5006 e cada CT-e tem o seu.
        servicos = [x.get("valor_total_servico") for x in xml if x.get("valor_total_servico") is not None]
        descontos = [x.get("desconto_icms_st") for x in xml if x.get("desconto_icms_st")]
        peso = round(sum(pesos), 3) if pesos else _numero((valor or {}).get("pesoColeta"))
        datas = [d for d in (_data(doc.get("dtEmissao")) for doc in docs) if d]
        citados = {}
        for n in numeros:
            for c in contratos_do_cte.get(n, []):
                citados[str(c.get("id"))] = c
        detalhe_contratos = []
        for c in citados.values():
            v = valores.get(str(c.get("id"))) or {}
            detalhe_contratos.append({
                "numero": str(c.get("numeroCF") or ""), "emissao": str(c.get("dtEmissao") or "")[:16],
                "motorista": " ".join(str(c.get("motorista") or "").split()), "ctes": [str(x) for x in c.get("nrosCTe") or []],
                "valor_total_origem": _numero(v.get("valorTotalOrigem") or c.get("valorTotalOrigem")),
                "frete_liquido": _numero(v.get("freteLiquido")), "tarifa": _numero(v.get("tarifaMotoristaDigitada")),
                "tarifa_calculada": _numero(v.get("tarifaMotoristaCalculada")), "peso_coleta": _numero(v.get("pesoColeta")),
                "adiantamento": _numero(v.get("valorAdiantamento") or c.get("valorAdiantamento")), "saldo": _numero(v.get("saldo") or c.get("saldo")),
                "combustivel": _numero(v.get("valorCombustivel")), "pedagio": _numero(v.get("valorPedagio")),
                "descontos": _numero(v.get("outrosDescontos")), "acrescimos": _numero(v.get("outrosAcrescimos")),
                "tem_valores": bool(v),
            })
        cargas.append({
            "numeros": numeros,
            "ctes": "/".join(numeros),
            "data_emissao": min(datas) if datas else None,
            "motorista": motorista,
            "placa": (docs[0].get("dados_motorista") or {}).get("veiculo") or "",
            "fabrica": nome_da_fabrica(primeiro.get("remetente") or docs[0].get("remetente")),
            "cliente": " ".join(str(primeiro.get("destinatario") or docs[0].get("destinatario") or "").split()),
            "destino": destino,
            "peso": peso or 0,
            "frete_empresa_total": fin.dinheiro(sum(fretes)) if fretes else None,
            "frete_servico_total": fin.dinheiro(sum(servicos)) if servicos else None,
            "desconto_icms_st": fin.dinheiro(sum(descontos)) if descontos else None,
            "frete_motorista_total": None,  # vem da carta frete, logo abaixo
            "carta_frete": None,
            "valor_contrato": fin.dinheiro(_numero((valor or {}).get("valorTotalOrigem") or (contrato or {}).get("valorTotalOrigem")))
            if _numero((valor or {}).get("valorTotalOrigem") or (contrato or {}).get("valorTotalOrigem")) is not None else None,
            "contrato": str(contrato.get("numeroCF") or "") if contrato else "",
            "cancelado": all(n in cancelados for n in numeros),
            "contratos_detalhe": detalhe_contratos,
            # Preenchidos logo abaixo, se esta carga tiver complemento.
            "complementos": "", "complemento_total": None, "complemento_de": "",
        })

    # Cada complemento no seu lugar. Quando a carga do CT-e complementado esta
    # aqui, o valor soma nela; quando nao esta (original de outro mes) ou o
    # complemento foi cancelado, ele vira linha propria marcada como
    # complemento - o dinheiro nao some e nao vira carga fantasma de 0 t.
    por_cte = {n: carga for carga in cargas for n in carga["numeros"]}
    for numero in sorted(complementos, key=int):
        lido = complementos[numero]
        original = por_chave.get(lido.get("chave_complementado")) or lido.get("numero_complementado") or ""
        carga = por_cte.get(original)
        if carga is not None and numero not in cancelados:
            _somar_complemento(carga, numero, lido)
            continue
        cargas.append(_carga_so_do_complemento(numero, lido, por_numero[numero], original, cidades,
                                               cancelado=numero in cancelados))

    ligar_cartas_frete(db, cargas)
    return {"cargas": cargas, "ctes": len(por_numero), "contratos": len(contratos)}


def _so_letras_numeros(texto) -> str:
    return re.sub(r"[^A-Z0-9]", "", fin.sem_acento(texto).upper())


def _mesmo_nome(motorista: str, condutor: str) -> bool:
    """Os dois primeiros nomes batem ("KAIFFER NATAN" em "KAIFFER NATAN PEREIRA DA COSTA")."""
    a = [p for p in fin.sem_acento(motorista).upper().split() if len(p) > 2][:2]
    b = set(fin.sem_acento(condutor).upper().split())
    return len(a) == 2 and all(p in b for p in a)


def _valor_br(texto) -> Optional[float]:
    limpo = re.sub(r"[^\d,.-]", "", str(texto or ""))
    if not limpo:
        return None
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return None


def ligar_cartas_frete(db: Session, cargas: list[dict], dias: int = 5) -> None:
    """O frete do motorista sai da carta frete emitida pelo sistema: mesma
    placa do cavalo (ou mesmo motorista) e data perto da do CT-e."""
    cartas = []
    for carta in db.query(CartaFreteEnviada).filter(CartaFreteEnviada.status != "cancelada").all():
        try:
            dia = datetime.strptime(carta.data or "", "%d/%m/%Y").date()
        except ValueError:
            continue
        valor = _valor_br(carta.valor_frete)
        if valor:
            cartas.append((carta, dia, valor))
    usadas: set[int] = set()
    for carga in sorted(cargas, key=lambda c: c["data_emissao"] or date.max):
        # Linha de complemento solto nao procura carta: a viagem - e a carta
        # dela - esta no CT-e original, e pegar uma carta aqui roubaria o frete
        # do motorista da carga de verdade.
        if not carga["data_emissao"] or carga["cancelado"] or carga.get("complemento_de"):
            continue
        placa = _so_letras_numeros(carga.get("placa"))
        candidatas = []
        for carta, dia, valor in cartas:
            distancia = abs((dia - carga["data_emissao"]).days)
            if carta.id in usadas or distancia > dias:
                continue
            if placa and _so_letras_numeros(carta.placa_cavalo) == placa:
                candidatas.append((0, distancia, carta, dia, valor))
            elif _mesmo_nome(carga["motorista"], carta.condutor):
                candidatas.append((1, distancia, carta, dia, valor))
        if candidatas:
            _, _, carta, dia, valor = min(candidatas, key=lambda c: (c[0], c[1]))
            usadas.add(carta.id)
            carga["frete_motorista_total"] = fin.dinheiro(valor)
            carga["carta_frete"] = {"data": dia.isoformat(), "valor": fin.dinheiro(valor), "condutor": carta.condutor}


# --------------------------------------------------------------------------
# Sincronizacao com o controle
# --------------------------------------------------------------------------

CAMPOS_DO_BSOFT = ("data_emissao", "motorista", "fabrica", "destino", "cliente", "peso",
                   "frete_empresa_total", "frete_servico_total", "desconto_icms_st",
                   "frete_motorista_total", "contrato_frete", "cancelado")


def _numeros_de(texto: str) -> set[str]:
    return set(re.findall(r"\d+", texto or ""))


def _valores_da_carga(carga: dict) -> dict:
    return {
        # A lista de CT-e entra nos valores por causa do complemento: a carga
        # que era "5263/5264" vira "5263/5264/5265" quando ele chega.
        "ctes": carga["ctes"],
        "data_emissao": carga["data_emissao"], "motorista": carga["motorista"], "fabrica": carga["fabrica"],
        "destino": carga["destino"], "cliente": carga["cliente"], "peso": carga["peso"],
        "frete_empresa_total": carga["frete_empresa_total"], "frete_motorista_total": carga["frete_motorista_total"],
        "contrato_frete": carga["contrato"], "cancelado": carga["cancelado"], "valor_contrato_frete": carga.get("valor_contrato"),
        # Guardados pra conferir o frete cobrado: total do servico no CT-e e o
        # ICMS ST que o tomador retem. Nao entram em nenhuma soma.
        "frete_servico_total": carga.get("frete_servico_total"), "desconto_icms_st": carga.get("desconto_icms_st"),
        # Complemento: quais CT-e complementares ja estao dentro do frete
        # cobrado, quanto deles veio e, na linha solta, qual CT-e ela completa.
        "complementos": carga.get("complementos") or "", "complemento_total": carga.get("complemento_total"),
        "complemento_de": carga.get("complemento_de") or "",
    }


def _resumo(carga: dict) -> dict:
    return {
        "ctes": carga["ctes"], "data_emissao": carga["data_emissao"].isoformat() if carga["data_emissao"] else None,
        "motorista": carga["motorista"], "fabrica": carga["fabrica"], "destino": carga["destino"],
        "peso": carga["peso"], "frete_empresa": carga["frete_empresa_total"], "frete_motorista": carga["frete_motorista_total"],
        "frete_servico": carga.get("frete_servico_total"), "desconto_icms_st": carga.get("desconto_icms_st"),
        "cancelado": carga["cancelado"], "sem_contrato": not carga["contrato"],
        "carta_frete": carga.get("carta_frete"), "valor_contrato": carga.get("valor_contrato"),
        "contratos": carga.get("contratos_detalhe", []),
        "complementos": carga.get("complementos") or "", "complemento_total": carga.get("complemento_total"),
        "complemento_de": carga.get("complemento_de") or "",
    }


def sincronizar(db: Session, competencia: str, *, aplicar: bool = False, lido: Optional[dict] = None) -> dict:
    """Traz as cargas do mes. Nao mexe nos valores das que vieram da planilha
    ou foram digitadas: so completa campo vazio e aponta a diferenca.

    O "frete cobrado" que entra e o valor a receber do CT-e. Carga antiga da
    planilha, lancada pelo total do servico, aparece como divergencia - a
    diferenca e o ICMS ST."""
    inicio, fim = fin.limites_competencia(competencia)
    lido = lido if lido is not None else cargas_do_periodo(db, inicio, fim)
    existentes = db.query(CarregamentoFinanceiro).all()

    novos, atualizados, divergencias, removidos = [], [], [], []
    ja_existiam = 0
    try:
        for carga in lido["cargas"]:
            if not carga["data_emissao"] or fin.competencia_de(carga["data_emissao"]) != competencia:
                continue
            numeros = set(carga["numeros"])
            so_complementos = _numeros_de(carga.get("complementos"))
            # A linha da carga e a do CT-e da VIAGEM: o numero do complemento
            # so vale pra achar a linha quando ela e do proprio complemento
            # (senao a carga inteira cairia na linha de 0 t gravada antes).
            principais = numeros - so_complementos
            alvo = (next((c for c in existentes if _numeros_de(c.ctes) & principais), None)
                    or next((c for c in existentes if _numeros_de(c.ctes) & numeros), None))
            # Complemento que a versao antiga gravou como carga sozinha (linha
            # de 0 t pedindo motorista) sai de cena agora que o valor dele esta
            # dentro da carga do CT-e original - senao o dinheiro contaria duas vezes.
            for antiga in [c for c in existentes
                           if c is not alvo and c.origem == "bsoft" and _numeros_de(c.ctes)
                           and _numeros_de(c.ctes) <= so_complementos]:
                existentes.remove(antiga)
                removidos.append({"ctes": antiga.ctes, "frete_empresa": fin.dinheiro(antiga.frete_empresa_total),
                                  "juntado_em": carga["ctes"]})
                db.delete(antiga)
            valores = _valores_da_carga(carga)
            if alvo is None:
                # `ctes` vem dentro de `valores` (o complemento muda a lista).
                nova = CarregamentoFinanceiro(competencia=competencia, origem="bsoft",
                                              frete_motorista_ton=None, **valores)
                db.add(nova)
                existentes.append(nova)
                novos.append(_resumo(carga))
                continue
            ja_existiam += 1
            if alvo.origem == "bsoft":
                mudou = False
                for campo, valor in valores.items():
                    # Frete do motorista digitado na tela nao e trocado.
                    if campo == "frete_motorista_total" and (alvo.frete_motorista_total is not None or alvo.frete_motorista_ton is not None):
                        continue
                    # A lista de CT-e so cresce (o complemento que chegou
                    # depois entra na carga); nunca perde numero por causa de
                    # um agrupamento diferente.
                    if campo == "ctes" and not _numeros_de(valor) >= _numeros_de(alvo.ctes):
                        continue
                    # O rotulo do complemento anda junto com o valor: se o CT-e
                    # complementar for cancelado depois, a linha tem que perder
                    # os dois - por isso estes dois aceitam vazio.
                    if campo in ("complementos", "complemento_total"):
                        if getattr(alvo, campo) != valor:
                            setattr(alvo, campo, valor)
                            mudou = True
                        continue
                    if valor not in (None, "") and getattr(alvo, campo) != valor:
                        setattr(alvo, campo, valor)
                        mudou = True
                if mudou:
                    atualizados.append(_resumo(carga))
                continue
            # Veio da planilha ou foi digitada: completa o que falta, sem trocar valor.
            for campo in ("destino", "cliente", "contrato_frete", "motorista", "fabrica"):
                if not getattr(alvo, campo) and valores[campo]:
                    setattr(alvo, campo, valores[campo])
            if alvo.data_emissao is None and valores["data_emissao"]:
                alvo.data_emissao = valores["data_emissao"]
            if alvo.valor_contrato_frete is None and valores["valor_contrato_frete"] is not None:
                alvo.valor_contrato_frete = valores["valor_contrato_frete"]
            # Total do servico e ICMS ST sao referencia: preencher nao troca
            # nenhum valor da carga e mostra, na linha da planilha, quanto do
            # frete cobrado e imposto retido pelo tomador.
            for campo in ("frete_servico_total", "desconto_icms_st"):
                if getattr(alvo, campo) is None and valores[campo] is not None:
                    setattr(alvo, campo, valores[campo])
            totais = fin.totais_carregamento(alvo)
            diferencas = {}
            for rotulo, no_sistema, no_bsoft in (
                ("frete cobrado", totais["frete_empresa"], carga["frete_empresa_total"]),
                ("frete do motorista", totais["frete_motorista"], carga["frete_motorista_total"]),
                ("peso", float(alvo.peso or 0), carga["peso"]),
            ):
                if no_bsoft is not None and abs(float(no_sistema) - float(no_bsoft)) > 0.01:
                    diferencas[rotulo] = {"controle": no_sistema, "bsoft": no_bsoft}
            if diferencas:
                divergencias.append({"ctes": alvo.ctes, "motorista": alvo.motorista, "diferencas": diferencas,
                                     # Vai junto pra tela explicar a diferenca mais comum: o
                                     # controle antigo lancou o total do servico, com o ICMS ST dentro.
                                     "desconto_icms_st": carga.get("desconto_icms_st"),
                                     "contratos": carga.get("contratos_detalhe", [])})
        db.flush()
        if aplicar:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise

    return {
        "competencia": competencia,
        "aplicado": aplicar,
        "ctes_no_bsoft": lido["ctes"],
        "cargas_no_bsoft": len([c for c in lido["cargas"] if c["data_emissao"] and fin.competencia_de(c["data_emissao"]) == competencia]),
        "novos": novos,
        "atualizados": atualizados,
        # Linhas de 0 t que eram complemento e agora estao dentro da carga.
        "removidos": removidos,
        "ja_existiam": ja_existiam,
        "divergencias": divergencias,
        "sem_contrato": sum(1 for c in novos if c["sem_contrato"]),
        "com_carta_frete": sum(1 for c in novos if c["carta_frete"]),
        # Linha de complemento nao conta: ela nao tem viagem nem motorista.
        "motorista_a_completar": sum(1 for c in novos if not c["carta_frete"] and not c["cancelado"] and not c["complemento_de"]),
    }
