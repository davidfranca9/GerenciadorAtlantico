"""Teste dourado: NF-e 158852 tem que derivar o CT-e 5053.

Este par e real. A Atlantico emitiu o CT-e 5053 (chave ...1615 9889, serie
1, modelo 57, 05/09/2026) a partir da NF-e 158852 da FERTIMAXI, e os
valores abaixo foram lidos do DACTE autorizado pela SEFAZ.

E aqui que se prova o requisito "tem que ser igual": se alguma regra de
montagem mudar e o documento parar de sair identico ao que sai hoje na
tela do Bsoft, este arquivo quebra.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.fiscal import escolher_cfops_id  # noqa: E402
from app.servicos import cte_montagem  # noqa: E402

# NF-e 158852 - FERTIMAXI (Conceicao do Jacuipe/BA) -> produtor rural em
# Montes Claros/MG. 540 volumes, 27 toneladas de ureia.
NFE_158852 = b"""<?xml version="1.0" encoding="UTF-8"?>
<NFe xmlns="http://www.portalfiscal.inf.br/nfe"><infNFe Id="NFe29260908068476000176550010001588521343374682">
<ide><nNF>158852</nNF><serie>1</serie><tpNF>1</tpNF><dhEmi>2026-09-05T11:17:00-03:00</dhEmi></ide>
<emit><CNPJ>08068476000176</CNPJ><xNome>FERTIMAXI INDUSTRIA, COMERCIO E SERVICOS DE FERTILIZANTES LT</xNome>
<enderEmit><cMun>2908507</cMun><xMun>CONCEICAO DO JACUIPE</xMun><UF>BA</UF></enderEmit></emit>
<dest><CPF>36831417604</CPF><xNome>ELTON CALDEIRA DA SILVA</xNome>
<enderDest><cMun>3143302</cMun><xMun>MONTES CLAROS</xMun><UF>MG</UF></enderDest></dest>
<det nItem="1"><prod><xProd>UREIA PRILL MICROGRANULADA 46% N Emb.: SACO DE 50 KG</xProd>
<NCM>31021010</NCM><CFOP>6101</CFOP><uCom>TON</uCom><qCom>27.0000</qCom><vProd>68850.00</vProd></prod>
<imposto><ICMS><ICMS20><orig>0</orig><CST>20</CST><vBC>22950.00</vBC><vICMS>2754.00</vICMS></ICMS20></ICMS></imposto></det>
<total><ICMSTot><vBC>22950.00</vBC><vICMS>2754.00</vICMS><vBCST>0</vBCST><vST>0</vST>
<vProd>68850.00</vProd><vNF>68850.00</vNF></ICMSTot></total>
<transp><modFrete>1</modFrete><transporta><CNPJ>08187322000101</CNPJ></transporta>
<vol><qVol>540</qVol><esp>BAGS</esp><marca>Fertimaxi</marca><pesoL>27.000</pesoL><pesoB>27.000</pesoB></vol></transp>
</infNFe></NFe>"""

# Tarifa da regra "Calculo FERTIMAXI" nessa rota, lida do proprio DACTE:
# o componente TARIFA PESO vale 300,00 e o frete fechou em 8.100,00 para
# 27 toneladas.
TARIFA_5053 = "300.00"


def espelho():
    return cte_montagem.derivar(NFE_158852, tarifa_por_tonelada=TARIFA_5053)


def test_peso_bate_com_o_dacte():
    # DACTE 5053: PESO BRUTO 27.000,0000 KG. A nota dizia 27.000 (toneladas).
    assert espelho()["peso_kg"] == "27000.000"
    assert espelho()["peso_convertido_de_tonelada"] is True


def test_frete_e_icms_batem_com_o_dacte():
    # DACTE 5053: TARIFA PESO 300,00 / FRETE VALOR 8.100,00 / BC 8.100,00.
    resultado = espelho()
    assert resultado["valor_frete"] == "8100.00"
    assert resultado["base_calculo"] == "8100.00"


def test_icms_de_12_por_cento_sobre_a_base_da_os_972_do_dacte():
    # Confere a coerencia do numero que o Bsoft calculou: 12% de 8.100,00.
    base = float(espelho()["base_calculo"])
    assert round(base * 0.12, 2) == 972.00


def test_tomador_e_o_destinatario():
    # DACTE 5053: TOMADOR DO SERVICO ELTON CALDEIRA DA SILVA (o
    # destinatario), porque a nota veio com modFrete 1.
    resultado = espelho()
    assert resultado["tomador"] == "destinatario"
    assert resultado["tomador_doc"] == "36831417604"


def test_cfop_e_6352():
    # DACTE 5053: CFOP 6352 - Prest. Servico de Transp. Estabelecimento
    # industrial. Na config do tenant esse CFOP e o cfops_id 3.
    resultado = espelho()
    assert escolher_cfops_id(resultado["uf_origem"], resultado["uf_destino"]) == 3


def test_origem_e_destino_batem_com_o_dacte():
    # DACTE 5053: origem Conceicao do Jacuipe - BA (2908507),
    # destino Montes Claros - MG (3143302).
    resultado = espelho()
    assert resultado["ibge_origem"] == "2908507"
    assert resultado["ibge_destino"] == "3143302"


def test_remetente_e_destinatario_batem_com_o_dacte():
    resultado = espelho()
    assert resultado["remetente_doc"] == "08068476000176"   # FERTIMAXI
    assert resultado["destinatario_doc"] == "36831417604"   # ELTON
    assert resultado["destinatario_tipo"] == "fisica"


def test_valor_da_mercadoria_bate_com_o_dacte():
    # DACTE 5053: VALOR TOTAL DA MERCADORIA 68.850,00.
    assert espelho()["valor_mercadoria"] == "68850.00"


def test_produto_predominante_sai_cortado_como_no_dacte():
    # O DACTE mostra "...Emb.: SACO DE 50", sem o KG final: o campo do CT-e
    # e menor que a descricao da nota.
    assert espelho()["produto_predominante"] == "UREIA PRILL MICROGRANULADA 46% N Emb.: SACO DE 50"


def test_quantidade_de_volumes_bate_com_o_dacte():
    # DACTE 5053: QTD 540,0000.
    assert espelho()["quantidade"] == "540"


def test_avisa_que_a_especie_nao_vem_da_nota():
    # A nota diz BAGS, o CT-e 5053 saiu como BIG BAG 1000 KG.
    assert any("Especie" in p for p in espelho()["pendencias"])


def test_sem_tarifa_nao_inventa_frete():
    resultado = cte_montagem.derivar(NFE_158852)
    assert "valor_frete" not in resultado
    assert any("Tarifa" in p for p in resultado["pendencias"])


def test_embalagem_do_pedido_vira_a_especie_do_dacte():
    # O 5053 saiu com BIG BAG 1000 KG, que e a especie 10 do cadastro.
    resultado = cte_montagem.derivar(
        NFE_158852, tarifa_por_tonelada=TARIFA_5053, embalagem="BIG BAG 1000 KG"
    )
    assert resultado["especie"]["especie_id"] == 10
    assert resultado["especie"]["confianca"] == "alta"
    # Resolvida a especie, nao sobra pendencia sobre ela.
    assert not any("Especie" in p for p in resultado["pendencias"])
