"""Carregamentos puxados do Bsoft: CT-e + XML + contrato de frete.

O Bsoft e simulado (nenhuma chamada sai daqui). Os formatos seguem a
documentacao e as respostas reais lidas em 16/09/2026: listagem de CT-e com
`dados_motorista`, contrato de frete com `nrosCTe`, valores com
`valorTotalOrigem`/`tarifaMotoristaDigitada` e XML com `autorizacao`/`cancelamento`.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import (  # noqa: E402
    CarregamentoFinanceiro, Cidade, ContaAvulsa, ContaBancaria, Despesa, Divida, LancamentoCaixa, MetaMensal, PagamentoAgenda,
)
from app.servicos import financeiro as fin  # noqa: E402
from app.servicos import financeiro_bsoft as fb  # noqa: E402
from tests.apoio_documentos import banco_em_memoria  # noqa: E402


def xml_cte(numero, valor, peso_kg, municipio="CARATINGA", ibge="3113404", uf="MG", remetente="FERTIMAXI FERTILIZANTES LTDA",
            destinatario="MOYSES ALVINO COVRE"):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<cteProc xmlns="http://www.portalfiscal.inf.br/cte" versao="4.00"><CTe><infCte Id="CTe29" versao="4.00">
<ide><cUF>29</cUF><nCT>{numero}</nCT><dhEmi>2026-09-02T10:15:00-03:00</dhEmi><tpCTe>0</tpCTe>
<cMunIni>2906501</cMunIni><xMunIni>CANDEIAS</xMunIni><UFIni>BA</UFIni>
<cMunFim>{ibge}</cMunFim><xMunFim>{municipio}</xMunFim><UFFim>{uf}</UFFim></ide>
<emit><xNome>ATLANTICO FERTLOG</xNome></emit>
<rem><CNPJ>1</CNPJ><xNome>{remetente}</xNome></rem>
<dest><CPF>2</CPF><xNome>{destinatario}</xNome></dest>
<vPrest><vTPrest>{valor}</vTPrest><vRec>{valor}</vRec></vPrest>
<infCTeNorm><infCarga><vCarga>100000.00</vCarga><proPred>SUPER SIMPLES</proPred>
<infQ><cUnid>03</cUnid><tpMed>SACOS</tpMed><qCarga>640.0000</qCarga></infQ>
<infQ><cUnid>01</cUnid><tpMed>PESO BRUTO</tpMed><qCarga>{peso_kg}</qCarga></infQ>
</infCarga></infCTeNorm></infCte></CTe></cteProc>"""


CTES = [
    {"id": "10", "nro": "5005", "dtEmissao": "2026-09-01 08:00:00", "chaveAcesso": "K5005", "remetente": "HERINGER",
     "destinatario": "X", "dados_motorista": {"motorista": "LINDOMAR DA SILVA ", "veiculo": "ABC-1D23"}},
    {"id": "11", "nro": "5006", "dtEmissao": "2026-09-01 08:05:00", "chaveAcesso": "K5006", "remetente": "HERINGER",
     "destinatario": "X", "dados_motorista": {"motorista": "LINDOMAR DA SILVA ", "veiculo": "ABC-1D23"}},
    {"id": "12", "nro": "5121", "dtEmissao": "2026-09-16 17:24:00", "chaveAcesso": "K5121", "remetente": "TIMAC AGRO",
     "destinatario": "MOYSES", "dados_motorista": {"motorista": "JOSE ALBERTO SEBEN ", "veiculo": "JCU-8D98"}},
    {"id": "13", "nro": "5122", "dtEmissao": "2026-09-16 18:00:00", "chaveAcesso": "K5122", "remetente": "FERTIMAXI",
     "destinatario": "Y", "dados_motorista": {"motorista": "SEM CONTRATO", "veiculo": "XYZ-9A99"}},
    {"id": "14", "nro": "Rascunho", "dtEmissao": "2026-09-16 18:10:00", "chaveAcesso": "", "dados_motorista": {}},
    {"id": "15", "nro": "5123", "dtEmissao": "2026-09-16 19:00:00", "chaveAcesso": "K5123", "remetente": "FERTIMAXI",
     "destinatario": "Z", "dados_motorista": {"motorista": "CANCELADO", "veiculo": "CAN-0C00"}},
]
CONTRATOS = [
    {"id": "2300", "numeroCF": "2290", "motorista": "LINDOMAR DA SILVA", "statusCancelado": "N", "nrosCTe": ["5005", "5006"], "valorTotalOrigem": "7040.00"},
    {"id": "2410", "numeroCF": "2400", "motorista": "JOSE ALBERTO SEBEN", "statusCancelado": "N", "nrosCTe": ["5121"], "valorTotalOrigem": "9200.00"},
    {"id": "2411", "numeroCF": "2401", "motorista": "X", "statusCancelado": "S", "nrosCTe": ["5122"], "valorTotalOrigem": "1.00"},
]
VALORES = [
    {"id": "2410", "valorTotalOrigem": "9200.00", "tarifaMotoristaDigitada": "230.000000000", "pesoColeta": "40.0000"},
    {"id": "2300", "valorTotalOrigem": "7040.00", "tarifaMotoristaDigitada": "220.000000000", "pesoColeta": "32.0000"},
]
XMLS = {
    "K5005": {"autorizacao": xml_cte(5005, "4640.00", "16000.0000", "TEOFILO OTONI", "3168606", "MG", "FERTILIZANTES HERINGER S.A."), "cancelamento": ""},
    "K5006": {"autorizacao": xml_cte(5006, "4640.00", "16000.0000", "TEOFILO OTONI", "3168606", "MG", "FERTILIZANTES HERINGER S.A."), "cancelamento": ""},
    "K5121": {"autorizacao": xml_cte(5121, "12000.00", "40000.0000", "NOVA BASSANO", "4312906", "RS", "TIMAC AGRO INDUSTRIA E COMERCIO"), "cancelamento": ""},
    "K5122": {"autorizacao": xml_cte(5122, "9600.00", "32000.0000"), "cancelamento": None},
    "K5123": {"autorizacao": xml_cte(5123, "9000.00", "30000.0000"), "cancelamento": "<procEventoCTe>cancelado</procEventoCTe>"},
}


@pytest.fixture
def bsoft(monkeypatch):
    chamadas = []

    def chamar(metodo, caminho, params=None, json_body=None, **kw):
        chamadas.append((metodo, caminho, params, json_body))
        offset, qtd = (int(x) for x in (params or {}).get("limit", "0,100").split(","))
        if caminho == "/transporte/v1/conhecimentos":
            return 200, CTES[offset:offset + qtd]
        if caminho == "/transporte/v1/contratosFrete":
            return 200, CONTRATOS[offset:offset + qtd]
        if caminho == "/transporte/v1/contratosFrete/valores":
            return 200, VALORES[offset:offset + qtd]
        if caminho == "/eDoc/v1/XMLDocumentosFiscais/CTesEmitidos":
            assert json_body["obterXmlEventos"] == "S" and len(json_body["chaveAcesso"]) <= 50
            return 200, [{"chaveAcesso": c, "xml": XMLS[c]} for c in json_body["chaveAcesso"]]
        raise AssertionError(caminho)

    monkeypatch.setattr(fb, "chamar", chamar)
    return chamadas


@pytest.fixture
def db():
    sessao = banco_em_memoria(CarregamentoFinanceiro, Cidade, ContaBancaria, LancamentoCaixa, MetaMensal, Despesa,
                              ContaAvulsa, PagamentoAgenda, Divida)
    sessao.add_all([Cidade(nome="Teófilo Otoni", uf="MG", ibge="3168606"), Cidade(nome="Nova Bassano", uf="RS", ibge="4312906")])
    sessao.commit()
    yield sessao
    sessao.close()


def test_le_frete_peso_e_destino_do_xml():
    lido = fb.ler_xml_cte(xml_cte(5121, "12000.00", "40000.0000", "NOVA BASSANO", "4312906", "RS"))
    assert (lido["numero"], lido["valor_frete"], lido["peso"], lido["ibge_fim"], lido["uf_fim"]) == ("5121", 12000.0, 40.0, "4312906", "RS")
    assert lido["remetente"] == "FERTIMAXI FERTILIZANTES LTDA" and lido["destinatario"] == "MOYSES ALVINO COVRE"


def test_peso_em_tonelada_no_xml():
    xml = xml_cte(1, "10", "0").replace("<cUnid>01</cUnid><tpMed>PESO BRUTO</tpMed><qCarga>0</qCarga>",
                                         "<cUnid>02</cUnid><tpMed>PESO BRUTO</tpMed><qCarga>27.0000</qCarga>")
    assert fb.ler_xml_cte(xml)["peso"] == 27.0


def test_xml_invalido_nao_quebra():
    assert fb.ler_xml_cte("<nao fechado") == {}


def test_monta_uma_carga_por_contrato(db, bsoft):
    lido = fb.cargas_do_periodo(db, date(2026, 9, 1), date(2026, 9, 30))
    cargas = {c["ctes"]: c for c in lido["cargas"]}
    assert set(cargas) == {"5005/5006", "5121", "5122", "5123"}  # rascunho fica de fora
    junta = cargas["5005/5006"]
    assert (junta["frete_empresa_total"], junta["peso"], junta["frete_motorista_total"], junta["contrato"]) == (9280.0, 32.0, 7040.0, "2290")
    assert (junta["destino"], junta["fabrica"], junta["motorista"]) == ("Teófilo Otoni MG", "Heringer", "LINDOMAR DA SILVA")
    timac = cargas["5121"]
    assert (timac["fabrica"], timac["destino"], timac["frete_motorista_ton"], timac["data_emissao"]) == ("Timac", "Nova Bassano RS", 230.0, date(2026, 9, 16))
    # Contrato cancelado nao conta: a carga fica sem frete do motorista.
    assert (cargas["5122"]["frete_motorista_total"], cargas["5122"]["contrato"]) == (None, "")
    assert cargas["5123"]["cancelado"] is True and cargas["5122"]["cancelado"] is False
    paginas = [c for c in bsoft if c[1] == "/transporte/v1/conhecimentos"]
    assert paginas[0][2]["limit"] == "0,100" and paginas[0][2]["dataInicio"] == "2026-09-01"


def test_sincronizar_previa_nao_grava_e_aplicar_cria(db, bsoft):
    previa = fb.sincronizar(db, "2026-09")
    assert previa["aplicado"] is False and len(previa["novos"]) == 4
    assert db.query(CarregamentoFinanceiro).count() == 0
    feito = fb.sincronizar(db, "2026-09", aplicar=True)
    assert len(feito["novos"]) == 4 and feito["sem_contrato"] == 2
    carga = db.query(CarregamentoFinanceiro).filter(CarregamentoFinanceiro.ctes == "5005/5006").one()
    assert (carga.origem, carga.frete_empresa_total, carga.frete_motorista_total, carga.peso) == ("bsoft", 9280, 7040, 32)
    dados = fin.carregamento_para_dict(carga)
    assert dados["a_completar"] is True and dados["totais"]["liquido"] == 2240
    de_novo = fb.sincronizar(db, "2026-09", aplicar=True)
    assert de_novo["novos"] == [] and de_novo["ja_existiam"] == 4 and de_novo["atualizados"] == []


def test_carga_da_planilha_nao_tem_valor_trocado(db, bsoft):
    # A planilha tinha 290/t de frete; o Bsoft diz 9.280 no total (290 x 32).
    planilha = CarregamentoFinanceiro(competencia="2026-09", ctes="5005/5006", motorista="LINDOMAR DA SILVA", fabrica="Heringer",
                                      destino="", peso=32, frete_empresa_ton=280, frete_motorista_ton=220, agenciamento_ton=20,
                                      contratante="Queiroz", origem="planilha")
    db.add(planilha)
    db.commit()
    feito = fb.sincronizar(db, "2026-09", aplicar=True)
    assert feito["ja_existiam"] == 1 and len(feito["novos"]) == 3
    db.refresh(planilha)
    assert (planilha.frete_empresa_ton, planilha.agenciamento_ton, planilha.contratante) == (280, 20, "Queiroz")
    assert planilha.destino == "Teófilo Otoni MG" and planilha.contrato_frete == "2290"  # so completa o vazio
    assert feito["divergencias"] == [{"ctes": "5005/5006", "motorista": "LINDOMAR DA SILVA",
                                      "diferencas": {"frete cobrado": {"controle": 8960.0, "bsoft": 9280.0}}}]


def test_carga_do_bsoft_e_atualizada_mas_mantem_o_que_foi_completado(db, bsoft):
    fb.sincronizar(db, "2026-09", aplicar=True)
    carga = db.query(CarregamentoFinanceiro).filter(CarregamentoFinanceiro.ctes == "5121").one()
    carga.agenciamento_ton, carga.contratante = 10, "Junior"
    db.commit()
    VALORES[0]["valorTotalOrigem"] = "9400.00"
    try:
        feito = fb.sincronizar(db, "2026-09", aplicar=True)
    finally:
        VALORES[0]["valorTotalOrigem"] = "9200.00"
    db.refresh(carga)
    assert [a["ctes"] for a in feito["atualizados"]] == ["5121"]
    assert (carga.frete_motorista_total, carga.agenciamento_ton, carga.contratante) == (9400, 10, "Junior")
    assert fin.carregamento_para_dict(carga)["a_completar"] is False


def test_rota_puxar_do_bsoft(db, bsoft):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.auth import get_current_user
    from app.database import get_db
    from app.routers import financeiro as rotas

    app = FastAPI()
    app.include_router(rotas.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(email="dono", role="admin")
    http = TestClient(app)
    previa = http.post("/financeiro/carregamentos/bsoft", params={"competencia": "2026-09"})
    assert previa.status_code == 200 and len(previa.json()["novos"]) == 4
    assert http.post("/financeiro/carregamentos/bsoft", params={"competencia": "2026-13"}).status_code == 400
