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


class DadosInsuficientes(Exception):
    pass


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


def derivar(xml_bytes: bytes, *, tarifa_por_tonelada: str | None = None) -> dict:
    """Monta o espelho do CT-e a partir do XML da NF-e.

    O frete so e calculado quando a tarifa e informada: no 5053 foram
    R$ 300,00 por tonelada x 27 t = R$ 8.100,00, que e a regra "Calculo
    FERTIMAXI" (regraFrete_id 35). A tarifa muda por cliente e por rota,
    entao ela entra como parametro, nunca chutada.
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
            "Tarifa por tonelada nao informada: sem ela nao da pra calcular o frete "
            "(no CT-e 5053 foram R$ 300,00/t x 27 t = R$ 8.100,00)."
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
    # enquanto a NF-e trazia BAGS. E escolha de quem cadastra.
    faltando.append(
        f"Especie da carga: a nota diz {mercadoria.get('especie') or 'nao informada'!r}, "
        "mas o CT-e usa o cadastro do Bsoft (no 5053 foi BIG BAG 1000 KG). Confirmar."
    )
    return faltando
