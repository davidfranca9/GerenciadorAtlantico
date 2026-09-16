"""Carregamentos a partir do Bsoft: tudo o que foi emitido no mes, sem digitar.

- CT-e (listagem): numero, data, motorista, placa, remetente e destinatario.
- XML autorizado do CT-e: valor do frete (vTPrest), peso e cidade de destino.
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


def ler_xml_cte(xml: str) -> dict:
    """Frete, peso (t), destino e partes de um CT-e autorizado."""
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
    return {
        "numero": _texto(ide, "nCT"),
        "emissao": _texto(ide, "dhEmi")[:10],
        "tipo": _texto(ide, "tpCTe"),
        "municipio_fim": _texto(ide, "xMunFim"),
        "ibge_fim": _texto(ide, "cMunFim"),
        "uf_fim": _texto(ide, "UFFim"),
        "remetente": _texto(_filho(raiz, "rem"), "xNome"),
        "destinatario": _texto(_filho(raiz, "dest"), "xNome"),
        "valor_frete": _numero(_texto(_filho(raiz, "vPrest"), "vTPrest")),
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

    # Todos os contratos que citam cada CT-e (pra conferencia do frete do motorista).
    contratos_do_cte: dict[str, list] = {}
    for contrato in contratos:
        for n in contrato.get("nrosCTe") or []:
            contratos_do_cte.setdefault(str(n), []).append(contrato)

    grupos, usados = [], set()
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
        cidade = cidades.get(primeiro.get("ibge_fim"))
        destino = f"{cidade.nome} {cidade.uf}" if cidade else " ".join(
            p for p in (nome_legivel(primeiro.get("municipio_fim", "")), primeiro.get("uf_fim", "")) if p
        )
        pesos = [x.get("peso") for x in xml if x.get("peso")]
        fretes = [x.get("valor_frete") for x in xml if x.get("valor_frete") is not None]
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
            "frete_motorista_total": None,  # vem da carta frete, logo abaixo
            "carta_frete": None,
            "valor_contrato": fin.dinheiro(_numero((valor or {}).get("valorTotalOrigem") or (contrato or {}).get("valorTotalOrigem")))
            if _numero((valor or {}).get("valorTotalOrigem") or (contrato or {}).get("valorTotalOrigem")) is not None else None,
            "contrato": str(contrato.get("numeroCF") or "") if contrato else "",
            "cancelado": all(n in cancelados for n in numeros),
            "contratos_detalhe": detalhe_contratos,
        })
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
        if not carga["data_emissao"] or carga["cancelado"]:
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
                   "frete_empresa_total", "frete_motorista_total", "contrato_frete", "cancelado")


def _numeros_de(texto: str) -> set[str]:
    return set(re.findall(r"\d+", texto or ""))


def _valores_da_carga(carga: dict) -> dict:
    return {
        "data_emissao": carga["data_emissao"], "motorista": carga["motorista"], "fabrica": carga["fabrica"],
        "destino": carga["destino"], "cliente": carga["cliente"], "peso": carga["peso"],
        "frete_empresa_total": carga["frete_empresa_total"], "frete_motorista_total": carga["frete_motorista_total"],
        "contrato_frete": carga["contrato"], "cancelado": carga["cancelado"], "valor_contrato_frete": carga.get("valor_contrato"),
    }


def _resumo(carga: dict) -> dict:
    return {
        "ctes": carga["ctes"], "data_emissao": carga["data_emissao"].isoformat() if carga["data_emissao"] else None,
        "motorista": carga["motorista"], "fabrica": carga["fabrica"], "destino": carga["destino"],
        "peso": carga["peso"], "frete_empresa": carga["frete_empresa_total"], "frete_motorista": carga["frete_motorista_total"],
        "cancelado": carga["cancelado"], "sem_contrato": not carga["contrato"],
        "carta_frete": carga.get("carta_frete"), "valor_contrato": carga.get("valor_contrato"),
        "contratos": carga.get("contratos_detalhe", []),
    }


def sincronizar(db: Session, competencia: str, *, aplicar: bool = False, lido: Optional[dict] = None) -> dict:
    """Traz as cargas do mes. Nao mexe nos valores das que vieram da planilha
    ou foram digitadas: so completa campo vazio e aponta a diferenca."""
    inicio, fim = fin.limites_competencia(competencia)
    lido = lido if lido is not None else cargas_do_periodo(db, inicio, fim)
    existentes = db.query(CarregamentoFinanceiro).all()

    novos, atualizados, divergencias = [], [], []
    ja_existiam = 0
    try:
        for carga in lido["cargas"]:
            if not carga["data_emissao"] or fin.competencia_de(carga["data_emissao"]) != competencia:
                continue
            numeros = set(carga["numeros"])
            alvo = next((c for c in existentes if _numeros_de(c.ctes) & numeros), None)
            valores = _valores_da_carga(carga)
            if alvo is None:
                nova = CarregamentoFinanceiro(competencia=competencia, ctes=carga["ctes"], origem="bsoft",
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
        "ja_existiam": ja_existiam,
        "divergencias": divergencias,
        "sem_contrato": sum(1 for c in novos if c["sem_contrato"]),
        "com_carta_frete": sum(1 for c in novos if c["carta_frete"]),
        "motorista_a_completar": sum(1 for c in novos if not c["carta_frete"] and not c["cancelado"]),
    }
