"""CT-e complementar (tpCTe = 1): valor que entra na carga que ja existe.

Caso real de outubro/2026: o carregamento de 04/10 saiu com os CT-e 5263 e
5264 (30 t, 11.100,00, motorista 6.600,00) e no dia 05/10 vieram dois
complementos - o 5265 de 400,00 e o 5266 de 200,00. Complemento nao tem peso
nem viagem: antes virava carga de 0 t pedindo motorista na tela.

O Bsoft e simulado, nenhuma chamada sai daqui. O XML segue o layout do CT-e:
`ide/tpCTe` diz o tipo e `infCTeComp/chCTe` traz a chave do CT-e complementado.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import (  # noqa: E402
    CarregamentoFinanceiro, CartaFreteEnviada, Cidade, ContaAvulsa, ContaBancaria, Despesa, Divida, LancamentoCaixa, MetaMensal, PagamentoAgenda,
)
from app.servicos import financeiro as fin  # noqa: E402
from app.servicos import financeiro_bsoft as fb  # noqa: E402
from tests.apoio_documentos import banco_em_memoria  # noqa: E402

# Chave de acesso: cUF(31) AAMM(2610) CNPJ(14) modelo(57) serie(001) nCT(9)
# tpEmis(1) cCT(8) cDV(1) = 44 digitos.
INICIO_DA_CHAVE = "31" + "2610" + "12345678000199" + "57" + "001"


def chave(numero) -> str:
    return f"{INICIO_DA_CHAVE}{int(numero):09d}1{'0' * 8}7"


CLIENTE = "JOSE CARLOS DE OLIVEIRA"
FABRICA = "FERTIMAXI FERTILIZANTES LTDA"


def xml_normal(numero, valor, peso_kg):
    """CT-e normal (tpCTe 0), com peso e valor do frete."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<cteProc xmlns="http://www.portalfiscal.inf.br/cte" versao="4.00"><CTe><infCte Id="CTe{chave(numero)}" versao="4.00">
<ide><cUF>31</cUF><nCT>{numero}</nCT><dhEmi>2026-10-04T14:20:00-03:00</dhEmi><tpCTe>0</tpCTe>
<cMunIni>2906501</cMunIni><xMunIni>CANDEIAS</xMunIni><UFIni>BA</UFIni>
<cMunFim>3147907</cMunFim><xMunFim>PAVAO</xMunFim><UFFim>MG</UFFim></ide>
<emit><xNome>ATLANTICO FERTLOG</xNome></emit>
<rem><CNPJ>1</CNPJ><xNome>{FABRICA}</xNome></rem>
<dest><CPF>2</CPF><xNome>{CLIENTE}</xNome></dest>
<vPrest><vTPrest>{valor}</vTPrest><vRec>{valor}</vRec>
<Comp><xNome>FRETE VALOR</xNome><vComp>{valor}</vComp></Comp></vPrest>
<infCTeNorm><infCarga><vCarga>90000.00</vCarga><proPred>FERTILIZANTE</proPred>
<infQ><cUnid>01</cUnid><tpMed>PESO BRUTO</tpMed><qCarga>{peso_kg}</qCarga></infQ>
</infCarga></infCTeNorm></infCte></CTe></cteProc>"""


def xml_complemento(numero, valor, complementado, dia="05", tag="infCTeComp"):
    """CT-e complementar: tpCTe 1, sem infCarga (nao tem peso) e com a chave do
    CT-e complementado. A tag sai como `infCTeComp` ou `infCteComp` conforme o
    layout - o `tag` do teste cobre as duas grafias."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<cteProc xmlns="http://www.portalfiscal.inf.br/cte" versao="4.00"><CTe><infCte Id="CTe{chave(numero)}" versao="4.00">
<ide><cUF>31</cUF><nCT>{numero}</nCT><dhEmi>2026-10-{dia}T09:40:00-03:00</dhEmi><tpCTe>1</tpCTe>
<cMunIni>2906501</cMunIni><xMunIni>CANDEIAS</xMunIni><UFIni>BA</UFIni>
<cMunFim>3147907</cMunFim><xMunFim>PAVAO</xMunFim><UFFim>MG</UFFim></ide>
<emit><xNome>ATLANTICO FERTLOG</xNome></emit>
<rem><CNPJ>1</CNPJ><xNome>{FABRICA}</xNome></rem>
<dest><CPF>2</CPF><xNome>{CLIENTE}</xNome></dest>
<vPrest><vTPrest>{valor}</vTPrest><vRec>{valor}</vRec>
<Comp><xNome>FRETE VALOR</xNome><vComp>{valor}</vComp></Comp></vPrest>
<{tag}><chCTe>{chave(complementado)}</chCTe></{tag}>
</infCte></CTe></cteProc>"""


def _cte(numero, dia, hora="14:20:00"):
    return {"id": str(numero), "nro": str(numero), "dtEmissao": f"2026-10-{dia} {hora}", "chaveAcesso": chave(numero),
            "remetente": "FERTIMAXI", "destinatario": CLIENTE,
            "dados_motorista": {"motorista": "VENI PEREIRA DA COSTA ", "veiculo": "PAV-1A11"}}


# O carregamento de 04/10: 5263 e 5264 juntos pelo contrato de frete, 15 t e
# 5.550,00 cada - os 30 t e 11.100,00 da tela.
CTES = [_cte(5263, "04"), _cte(5264, "04", "14:35:00")]
COMPLEMENTOS = [_cte(5265, "05", "09:40:00"), _cte(5266, "05", "09:45:00")]
CONTRATOS = [{"id": "2600", "numeroCF": "2590", "motorista": "VENI PEREIRA DA COSTA", "statusCancelado": "N",
              "nrosCTe": ["5263", "5264"], "valorTotalOrigem": "6600.00"}]
VALORES = [{"id": "2600", "valorTotalOrigem": "6600.00", "tarifaMotoristaDigitada": "220.000000000", "pesoColeta": "30.0000"}]
XMLS = {
    chave(5263): {"autorizacao": xml_normal(5263, "5550.00", "15000.0000"), "cancelamento": ""},
    chave(5264): {"autorizacao": xml_normal(5264, "5550.00", "15000.0000"), "cancelamento": ""},
    chave(5265): {"autorizacao": xml_complemento(5265, "400.00", 5263), "cancelamento": ""},
    # O segundo complemento aponta o outro CT-e da mesma carga e usa a grafia
    # alternativa da tag: tem que cair na mesma carga do mesmo jeito.
    chave(5266): {"autorizacao": xml_complemento(5266, "200.00", 5264, tag="infCteComp"), "cancelamento": ""},
}


def _bsoft_simulado(monkeypatch, ctes, contratos, valores, xmls):
    """Troca o cliente do Bsoft pelas listas dadas (nenhuma chamada de verdade)."""
    def chamar(metodo, caminho, params=None, json_body=None, **kw):
        offset, qtd = (int(x) for x in (params or {}).get("limit", "0,100").split(","))
        if caminho == "/transporte/v1/conhecimentos":
            return 200, ctes[offset:offset + qtd]
        if caminho == "/transporte/v1/contratosFrete":
            return 200, contratos[offset:offset + qtd]
        if caminho == "/transporte/v1/contratosFrete/valores":
            return 200, valores[offset:offset + qtd]
        if caminho == "/eDoc/v1/XMLDocumentosFiscais/CTesEmitidos":
            return 200, [{"chaveAcesso": c, "xml": xmls.get(c, {"autorizacao": "", "cancelamento": ""})}
                         for c in json_body["chaveAcesso"]]
        raise AssertionError(caminho)

    monkeypatch.setattr(fb, "chamar", chamar)


@pytest.fixture
def bsoft(monkeypatch):
    """Outubro inteiro: a carga de 04/10 e os dois complementos de 05/10."""
    _bsoft_simulado(monkeypatch, CTES + COMPLEMENTOS, CONTRATOS, VALORES, XMLS)


@pytest.fixture
def bsoft_sem_complemento(monkeypatch):
    """So a carga de 04/10, como era antes dos complementos existirem."""
    _bsoft_simulado(monkeypatch, CTES, CONTRATOS, VALORES, XMLS)


@pytest.fixture
def bsoft_so_complementos(monkeypatch):
    """Complementos emitidos num mes em que o CT-e original nao aparece."""
    _bsoft_simulado(monkeypatch, COMPLEMENTOS, [], [], XMLS)


@pytest.fixture
def db():
    sessao = banco_em_memoria(CarregamentoFinanceiro, CartaFreteEnviada, Cidade, ContaBancaria, LancamentoCaixa,
                              MetaMensal, Despesa, ContaAvulsa, PagamentoAgenda, Divida)
    sessao.add_all([
        Cidade(nome="Pavão", uf="MG", ibge="3147907"),
        # A autorizacao de abastecimento e o frete do motorista de verdade.
        CartaFreteEnviada(data="04/10/2026", condutor="VENI PEREIRA DA COSTA", placa_cavalo="PAV-1A11",
                          valor_frete="6.600,00", status="enviada"),
    ])
    sessao.commit()
    yield sessao
    sessao.close()


# --------------------------------------------------------------------------
# Leitura do XML
# --------------------------------------------------------------------------


def test_le_o_complemento_no_xml():
    """tpCTe 1, chave do complementado em infCTeComp e nenhum peso."""
    lido = fb.ler_xml_cte(xml_complemento(5265, "400.00", 5263))
    assert (lido["numero"], lido["tipo"], lido["complemento"]) == ("5265", "1", True)
    assert (lido["chave_complementado"], lido["numero_complementado"]) == (chave(5263), "5263")
    assert (lido["valor_frete"], lido["peso"]) == (400.0, None)


def test_le_o_complemento_com_a_outra_grafia_da_tag():
    """Em alguns layouts a tag vem como `infCteComp`."""
    lido = fb.ler_xml_cte(xml_complemento(5266, "200.00", 5264, tag="infCteComp"))
    assert (lido["complemento"], lido["numero_complementado"], lido["valor_frete"]) == (True, "5264", 200.0)


def test_cte_normal_nao_e_complemento():
    lido = fb.ler_xml_cte(xml_normal(5263, "5550.00", "15000.0000"))
    assert (lido["tipo"], lido["complemento"], lido["numero_complementado"]) == ("0", False, "")
    assert (lido["valor_frete"], lido["peso"]) == (5550.0, 15.0)


def test_numero_do_cte_sai_da_chave():
    """E assim que se acha o CT-e complementado quando ele nao veio na listagem."""
    assert fb.numero_da_chave(chave(5263)) == "5263"
    assert fb.numero_da_chave("123") == "" and fb.numero_da_chave(None) == ""


# --------------------------------------------------------------------------
# Montagem das cargas
# --------------------------------------------------------------------------


def test_carga_sem_complemento_continua_igual(db, bsoft_sem_complemento):
    """Nada muda pra quem nao tem complemento: 30 t, 11.100,00 e sobra 4.500,00."""
    cargas = fb.cargas_do_periodo(db, date(2026, 10, 1), date(2026, 10, 31))["cargas"]
    assert [c["ctes"] for c in cargas] == ["5263/5264"]
    carga = cargas[0]
    assert (carga["peso"], carga["frete_empresa_total"], carga["frete_motorista_total"]) == (30.0, 11100.0, 6600.0)
    assert (carga["complementos"], carga["complemento_total"], carga["complemento_de"]) == ("", None, "")
    assert (carga["destino"], carga["fabrica"], carga["motorista"]) == ("Pavão MG", "Fertimaxi", "VENI PEREIRA DA COSTA")


def test_complemento_soma_na_carga_do_cte_original(db, bsoft):
    """Os dois complementos entram na carga de 04/10: uma linha so, com os
    quatro numeros, 11.700,00 e os mesmos 30 t (complemento nao traz tonelada)."""
    cargas = fb.cargas_do_periodo(db, date(2026, 10, 1), date(2026, 10, 31))["cargas"]
    assert [c["ctes"] for c in cargas] == ["5263/5264/5265/5266"]  # nenhuma carga de 0 t
    carga = cargas[0]
    assert (carga["peso"], carga["frete_empresa_total"]) == (30.0, 11700.0)
    assert (carga["complementos"], carga["complemento_total"]) == ("5265/5266", 600.0)
    # O frete do motorista continua o da viagem, e a data e a do carregamento.
    assert (carga["frete_motorista_total"], carga["data_emissao"]) == (6600.0, date(2026, 10, 4))


def test_complemento_cancelado_nao_entra_no_frete(db, monkeypatch):
    """CT-e complementar cancelado nao e dinheiro: fica de fora da soma e vira
    uma linha propria marcada como cancelada."""
    xmls = {**XMLS, chave(5266): {**XMLS[chave(5266)], "cancelamento": "<procEventoCTe>cancelado</procEventoCTe>"}}
    _bsoft_simulado(monkeypatch, CTES + COMPLEMENTOS, CONTRATOS, VALORES, xmls)
    cargas = {c["ctes"]: c for c in fb.cargas_do_periodo(db, date(2026, 10, 1), date(2026, 10, 31))["cargas"]}
    assert cargas["5263/5264/5265"]["frete_empresa_total"] == 11500.0
    assert cargas["5266"]["cancelado"] is True and cargas["5266"]["complemento_de"] == "5264"


# --------------------------------------------------------------------------
# O que vai pro financeiro
# --------------------------------------------------------------------------


def test_sincronizar_grava_uma_carga_so_e_a_sobra_sai_certa(db, bsoft):
    """O reflexo do complemento: faturamento 11.700,00, sobra 5.100,00 e
    170,00/t - antes eram 4.500,00 em 30 t mais duas linhas de 0 t fora da conta."""
    feito = fb.sincronizar(db, "2026-10", aplicar=True)
    assert len(feito["novos"]) == 1 and feito["motorista_a_completar"] == 0
    assert (feito["novos"][0]["complementos"], feito["novos"][0]["complemento_total"]) == ("5265/5266", 600.0)
    carga = db.query(CarregamentoFinanceiro).one()
    assert (carga.ctes, carga.frete_empresa_total, carga.peso) == ("5263/5264/5265/5266", 11700, 30)
    assert (carga.complementos, carga.complemento_total, carga.complemento_de) == ("5265/5266", 600, "")
    totais = fin.totais_carregamento(carga)
    assert (totais["frete_empresa"], totais["liquido"], totais["por_tonelada"]) == (11700.0, 5100.0, 170.0)
    r = fin.resultado_mensal(db, "2026-10", hoje=date(2026, 10, 31))
    assert (r["resumo"]["frete_empresa"], r["resumo"]["lucro_bruto"]) == (11700.0, 5100.0)
    assert (r["resumo"]["carregamentos"], r["resumo"]["toneladas"]) == (1, 30.0)


def test_sincronizar_de_novo_nao_soma_o_complemento_duas_vezes(db, bsoft):
    fb.sincronizar(db, "2026-10", aplicar=True)
    de_novo = fb.sincronizar(db, "2026-10", aplicar=True)
    assert de_novo["novos"] == [] and de_novo["atualizados"] == [] and de_novo["ja_existiam"] == 1
    carga = db.query(CarregamentoFinanceiro).one()
    assert (carga.frete_empresa_total, carga.complemento_total) == (11700, 600)


def test_complemento_que_chega_depois_entra_na_carga_ja_gravada(db, monkeypatch):
    """Primeiro sincronizou so o 5263/5264; quando os complementos aparecem, a
    mesma linha passa a ter os quatro numeros e o frete maior."""
    _bsoft_simulado(monkeypatch, CTES, CONTRATOS, VALORES, XMLS)
    fb.sincronizar(db, "2026-10", aplicar=True)
    carga = db.query(CarregamentoFinanceiro).one()
    assert (carga.ctes, carga.frete_empresa_total) == ("5263/5264", 11100)
    _bsoft_simulado(monkeypatch, CTES + COMPLEMENTOS, CONTRATOS, VALORES, XMLS)
    feito = fb.sincronizar(db, "2026-10", aplicar=True)
    db.refresh(carga)
    assert [a["ctes"] for a in feito["atualizados"]] == ["5263/5264/5265/5266"]
    assert db.query(CarregamentoFinanceiro).count() == 1
    assert (carga.ctes, carga.frete_empresa_total, carga.complementos) == ("5263/5264/5265/5266", 11700, "5265/5266")


def test_linha_de_0_t_gravada_antes_sai_quando_o_complemento_entra_na_carga(db, bsoft):
    """Quem puxou outubro antes do acerto ficou com o 5265 e o 5266 como carga
    propria. Ao puxar de novo o valor passa pra carga do CT-e original e as
    linhas velhas somem: o dinheiro nao pode ser contado duas vezes."""
    db.add_all([
        CarregamentoFinanceiro(competencia="2026-10", ctes="5263/5264", data_emissao=date(2026, 10, 4),
                               motorista="VENI PEREIRA DA COSTA", peso=30, frete_empresa_total=11100,
                               frete_motorista_total=6600, origem="bsoft"),
        CarregamentoFinanceiro(competencia="2026-10", ctes="5265", data_emissao=date(2026, 10, 5),
                               motorista="VENI PEREIRA DA COSTA", peso=0, frete_empresa_total=400, origem="bsoft"),
        CarregamentoFinanceiro(competencia="2026-10", ctes="5266", data_emissao=date(2026, 10, 5),
                               motorista="VENI PEREIRA DA COSTA", peso=0, frete_empresa_total=200, origem="bsoft"),
    ])
    db.commit()
    feito = fb.sincronizar(db, "2026-10", aplicar=True)
    assert [x["ctes"] for x in feito["removidos"]] == ["5265", "5266"]
    assert feito["removidos"][0] == {"ctes": "5265", "frete_empresa": 400.0, "juntado_em": "5263/5264/5265/5266"}
    carga = db.query(CarregamentoFinanceiro).one()
    assert (carga.ctes, carga.frete_empresa_total, carga.peso) == ("5263/5264/5265/5266", 11700, 30)
    r = fin.resultado_mensal(db, "2026-10", hoje=date(2026, 10, 31))
    assert (r["resumo"]["frete_empresa"], r["resumo"]["lucro_bruto"]) == (11700.0, 5100.0)


def test_complemento_sem_o_original_no_periodo_nao_some(db, bsoft_so_complementos):
    """Complemento emitido num mes em que o CT-e original nao aparece: vira
    linha propria, no mes em que foi emitido, marcada com o CT-e que ela
    completa. O dinheiro continua na conta e a linha nao pede motorista."""
    feito = fb.sincronizar(db, "2026-10", aplicar=True)
    assert len(feito["novos"]) == 2 and feito["motorista_a_completar"] == 0
    linhas = {c.ctes: c for c in db.query(CarregamentoFinanceiro).all()}
    assert set(linhas) == {"5265", "5266"}
    linha = linhas["5265"]
    assert (linha.complemento_de, linha.peso, linha.frete_empresa_total) == ("5263", 0, 400)
    # Complemento nao tem viagem nova: o motorista ja foi pago no CT-e original.
    assert linha.frete_motorista_total == 0
    dados = fin.carregamento_para_dict(linha)
    assert dados["a_completar"] is False and dados["faltando"] == []
    assert (dados["totais"]["liquido"], dados["totais"]["completo"]) == (400.0, True)
    r = fin.resultado_mensal(db, "2026-10", hoje=date(2026, 10, 31))
    assert (r["resumo"]["frete_empresa"], r["resumo"]["lucro_bruto"]) == (600.0, 600.0)
    assert r["resumo"]["pendentes"]["carregamentos"] == 0
