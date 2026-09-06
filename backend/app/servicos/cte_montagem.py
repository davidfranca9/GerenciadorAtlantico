"""Deriva os campos do CT-e a partir da NF-e.

Cada regra aqui foi conferida contra um documento real: a NF-e 158852 da
FERTIMAXI e o CT-e 5053 que a Atlantico emitiu pra ela (BA -> MG,
05/09/2026). O teste dourado em tests/test_cte_5053.py reproduz esse par.

Nada aqui inventa valor fiscal. O ICMS do CT-e quem calcula e o Bsoft, a
partir do CFOP e da base que a gente manda - conferido no DACTE 5053:
base 8.100,00 com aliquota 12% deu ICMS 972,00.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

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


# Especies cadastradas no tenant (lidas via GET /bsoft/configuracoes-cte).
# A especie nao vem da NF-e: ela sai da embalagem do pedido, e varia -
# big bag, saco, granel.
ESPECIES_BSOFT = {
    1: "GRANEL",
    3: "SACOS",
    5: "BIG BAG",
    8: "SACO DE 50 KG",
    10: "BIG BAG 1000 KG",
    13: "Tonelada",
    14: "SACOS 50 KG",
}


class DadosInsuficientes(Exception):
    pass


def sugerir_especie(embalagem: str) -> dict:
    """Sugere a especie do Bsoft a partir da embalagem do pedido.

    Devolve sugestao, nunca decisao fechada. Onde o cadastro tem opcoes
    quase iguais (SACOS, SACO DE 50 KG e SACOS 50 KG), a funcao lista as
    candidatas em vez de escolher no chute - quem opera confirma.
    """
    texto = (embalagem or "").strip().upper()
    if not texto:
        return {"especie_id": None, "nome": "", "alternativas": [], "confianca": "nenhuma"}

    # Nome identico ao cadastro resolve na hora.
    for especie_id, nome in ESPECIES_BSOFT.items():
        if texto == nome.upper():
            return {"especie_id": especie_id, "nome": nome, "alternativas": [], "confianca": "alta"}

    if "GRANEL" in texto:
        return {"especie_id": 1, "nome": ESPECIES_BSOFT[1], "alternativas": [], "confianca": "alta"}

    if "BAG" in texto:
        if "1000" in texto:
            return {"especie_id": 10, "nome": ESPECIES_BSOFT[10], "alternativas": [], "confianca": "alta"}
        return {
            "especie_id": 5,
            "nome": ESPECIES_BSOFT[5],
            "alternativas": [{"especie_id": 10, "nome": ESPECIES_BSOFT[10]}],
            "confianca": "ambigua",
        }

    if "SACO" in texto or "SACARIA" in texto:
        candidatas = [8, 14] if "50" in texto else [3, 8, 14]
        return {
            "especie_id": candidatas[0],
            "nome": ESPECIES_BSOFT[candidatas[0]],
            "alternativas": [{"especie_id": i, "nome": ESPECIES_BSOFT[i]} for i in candidatas[1:]],
            "confianca": "ambigua",
        }

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
        "municipio_origem": dados["municipio_origem"],
        "uf_origem": dados["uf_origem"],
        "ibge_destino": dados["ibge_destino"],
        "municipio_destino": dados["municipio_destino"],
        "uf_destino": dados["uf_destino"],
        "produto_predominante": mercadoria["descricao_produto"][:TAMANHO_PRODUTO_PREDOMINANTE].rstrip(),
        "valor_mercadoria": mercadoria["valor"],
        "peso_kg": str(kg),
        "quantidade": mercadoria["quant"],
        "peso_convertido_de_tonelada": bool(mercadoria.get("peso_provavelmente_em_tonelada")),
        "especie": sugerir_especie(embalagem),
        "embalagem_do_pedido": embalagem,
    }

    if tarifa_por_tonelada:
        frete = toneladas * Decimal(str(tarifa_por_tonelada))
        espelho["tarifa_por_tonelada"] = _duas_casas(Decimal(str(tarifa_por_tonelada)))
        espelho["valor_frete"] = _duas_casas(frete)
        espelho["base_calculo"] = _duas_casas(frete)

    espelho["pendencias"] = _pendencias(espelho, mercadoria, tarifa_por_tonelada)
    return espelho


def _pendencias(espelho: dict, mercadoria: dict, tarifa: str | None) -> list[str]:
    """O que ainda impede o documento de sair identico ao manual."""
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
    if espelho["peso_convertido_de_tonelada"]:
        faltando.append(
            f"Peso convertido de {mercadoria['peso_declarado']} t para {espelho['peso_kg']} kg. "
            "Confira antes de emitir."
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
    elif especie["confianca"] == "ambigua":
        opcoes = ", ".join(a["nome"] for a in especie["alternativas"])
        faltando.append(
            f"Especie sugerida {especie['nome']}, mas o cadastro tem opcao parecida "
            f"({opcoes}). Confirmar qual usar."
        )
    return faltando
