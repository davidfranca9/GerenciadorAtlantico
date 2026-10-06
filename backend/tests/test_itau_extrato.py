"""Extrato de conta corrente do Itau pela API, com o banco simulado.

NENHUMA chamada sai daqui: `requests` do servico e trocado por um objeto que
responde o que a documentacao mostra (token com `expires_in: 300` e eventos
com `operation`, `reversal`, `date.accounting` e `literal`).

O campo do VALOR nao aparece no print da documentacao que o banco mandou. Por
isso aqui ele e testado nos nomes plausiveis (`amount`, `value`,
`transaction_amount`, solto ou dentro de objeto) e tambem no caso em que nao
da pra achar: a importacao tem que falhar dizendo qual payload veio, nunca
gravar lancamento chutado no caixa.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import get_current_user  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models import ContaBancaria, LancamentoCaixa  # noqa: E402
from app.routers import financeiro as rotas  # noqa: E402
from app.servicos import financeiro_importacao as imp  # noqa: E402
from app.servicos import itau_extrato as itau  # noqa: E402
from tests.apoio_documentos import banco_em_memoria  # noqa: E402

INICIO, FIM = date(2026, 9, 1), date(2026, 9, 30)


# --------------------------------------------------------------------------
# Banco simulado
# --------------------------------------------------------------------------


class Resposta:
    def __init__(self, status: int = 200, corpo=None, texto: str = ""):
        self.status_code = status
        self._corpo = corpo
        self.text = texto or (json.dumps(corpo) if corpo is not None else "")

    def json(self):
        if self._corpo is None:
            raise ValueError("resposta sem JSON")
        return self._corpo


def evento(identificador, operation="C", valor="1000.00", accounting="2026-09-15",
           momento="2026-09-15T12:00:00Z", historico="PIX RECEBIDO ATLANTI", reversal=False,
           tipo="lancamento", campo_valor="amount"):
    """Um evento como o exemplo da documentacao, com o valor no campo pedido."""
    return {
        "id": identificador, "type": tipo, "operation": operation, "reversal": reversal,
        "date": {"event": momento, "accounting": accounting},
        "literal": {"code": "9980", "shortened": historico, "complete": historico,
                    "tip": "Lançamento referente a pagamento de boletos, transferências, DOCs, TEDs e PIX."},
        campo_valor: valor,
    }


class ItauFalso:
    """Responde token e extrato; conta quantas vezes cada um foi pedido."""

    def __init__(self, paginas, expires_in=300):
        self.paginas = paginas
        self.expires_in = expires_in
        self.tokens = 0
        self.gets = []
        self.status_token = 200
        self.recusar_primeiro_get = False
        self.exceptions = requests.exceptions

    def post(self, url, data=None, headers=None, cert=None, timeout=None):
        assert url == settings.itau_token_url
        assert data["grant_type"] == "client_credentials"
        assert data["client_id"] and data["client_secret"]
        assert cert == (settings.itau_cert_path, settings.itau_cert_key_path)
        self.tokens += 1
        if self.status_token != 200:
            return Resposta(self.status_token, None, '{"error":"invalid_client"}')
        return Resposta(200, {"access_token": f"token-{self.tokens}", "token_type": "Bearer",
                              "expires_in": self.expires_in, "refresh_token": "r", "scope": "extrato",
                              "active": True})

    def get(self, url, params=None, headers=None, cert=None, timeout=None):
        self.gets.append((url, dict(params or {}), (headers or {}).get("Authorization")))
        assert url.endswith("/statements/816100994788")
        assert params["type"] == "current_account"
        assert cert == (settings.itau_cert_path, settings.itau_cert_key_path)
        if self.recusar_primeiro_get:
            self.recusar_primeiro_get = False
            return Resposta(401, None, '{"message":"token expirado"}')
        pagina = int(params["page"])
        eventos = self.paginas[pagina - 1] if pagina <= len(self.paginas) else []
        return Resposta(200, {"data": [{"events": eventos}]})


@pytest.fixture
def credenciais(monkeypatch):
    """Credenciais de mentira; `page_size` 2 pra a paginacao aparecer nos testes."""
    valores = {
        "itau_client_id": "cliente-de-teste", "itau_client_secret": "segredo-de-teste",
        "itau_cert_path": "itau.crt", "itau_cert_key_path": "itau.key",
        "itau_agencia": "8161", "itau_conta": "99478", "itau_conta_dac": "8",
        "itau_token_url": "https://sts.rdhi.com.br/api/oauth/token",
        "itau_extrato_base_url": "https://account-statement.api.hom.itau.com/account-statement/v1",
        "itau_page_size": 2,
    }
    for campo, valor in valores.items():
        monkeypatch.setattr(settings, campo, valor)
    itau.limpar_token()
    yield
    itau.limpar_token()


def ligar(monkeypatch, paginas, expires_in=300) -> ItauFalso:
    falso = ItauFalso(paginas, expires_in=expires_in)
    monkeypatch.setattr(itau, "requests", falso)
    return falso


@pytest.fixture
def db():
    sessao = banco_em_memoria(ContaBancaria, LancamentoCaixa)
    yield sessao
    sessao.close()


def conta(db, nome="Itaú"):
    c = ContaBancaria(nome=nome, instituicao="Itaú", cor="#EC7000", saldo_inicial=0, saldo_inicial_em=INICIO)
    db.add(c)
    db.flush()
    return c


def cliente_http(db):
    app = FastAPI()
    app.include_router(rotas.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(email="dono@atlantico", role="admin")
    return TestClient(app)


# --------------------------------------------------------------------------
# Conta na URL e credenciais
# --------------------------------------------------------------------------


def test_conta_da_url_e_agencia_mais_dois_zeros_mais_conta_e_dac(credenciais):
    assert itau.conta_formatada() == "816100994788"


def test_conta_com_o_dac_junto_tambem_vale(credenciais, monkeypatch):
    monkeypatch.setattr(settings, "itau_conta", "99478-8")
    monkeypatch.setattr(settings, "itau_conta_dac", "")
    assert itau.conta_formatada() == "816100994788"


def test_sem_credencial_o_servico_pede_pra_configurar(monkeypatch, db):
    for campo in ("itau_client_id", "itau_client_secret", "itau_cert_path", "itau_cert_key_path",
                  "itau_agencia", "itau_conta"):
        monkeypatch.setattr(settings, campo, "")
    itau.limpar_token()
    bb = conta(db)
    db.commit()
    with pytest.raises(itau.CredencialItauAusente, match="Configure as credenciais do Itaú"):
        itau.importar_extrato(db, bb.id, INICIO, FIM)


def test_sem_credencial_a_rota_responde_400_claro(monkeypatch, db):
    for campo in ("itau_client_id", "itau_client_secret", "itau_cert_path", "itau_cert_key_path",
                  "itau_agencia", "itau_conta"):
        monkeypatch.setattr(settings, campo, "")
    itau.limpar_token()
    bb = conta(db)
    db.commit()
    resposta = cliente_http(db).post(f"/financeiro/contas/{bb.id}/extrato-itau",
                                     params={"inicio": "2026-09-01", "fim": "2026-09-30"})
    assert resposta.status_code == 400
    detalhe = resposta.json()["detail"]
    assert "Configure as credenciais do Itaú" in detalhe and "ITAU_CLIENT_ID" in detalhe


def test_conta_configurada_errado_nao_vira_url_torta(credenciais, monkeypatch):
    monkeypatch.setattr(settings, "itau_agencia", "81610")
    with pytest.raises(itau.CredencialItauAusente, match="4 dígitos"):
        itau.conta_formatada()


# --------------------------------------------------------------------------
# Token de 5 minutos
# --------------------------------------------------------------------------


def test_token_fica_em_memoria_e_renova_sozinho_quando_vence(credenciais, monkeypatch):
    relogio = [1000.0]
    monkeypatch.setattr(itau, "_agora", lambda: relogio[0])
    falso = ligar(monkeypatch, [[]])

    assert itau.token() == "token-1"
    assert itau.token() == "token-1" and falso.tokens == 1, "o mesmo token serve pra chamada seguinte"
    relogio[0] += 239  # 300s de validade menos 60s de folga: ainda vale
    assert itau.token() == "token-1" and falso.tokens == 1
    relogio[0] += 2    # passou da folga
    assert itau.token() == "token-2" and falso.tokens == 2


def test_token_morto_no_meio_da_paginacao_e_renovado_uma_vez(credenciais, monkeypatch):
    falso = ligar(monkeypatch, [[evento("1")]])
    falso.recusar_primeiro_get = True
    lido = itau.buscar_extrato(INICIO, FIM)
    assert len(lido["transacoes"]) == 1
    assert falso.tokens == 2, "o 401 derruba o token guardado e pega outro"
    assert [g[2] for g in falso.gets] == ["Bearer token-1", "Bearer token-2"]


def test_credencial_recusada_pelo_sts_nao_vaza_o_secret(credenciais, monkeypatch):
    falso = ligar(monkeypatch, [[]])
    falso.status_token = 401
    with pytest.raises(itau.ErroItau) as erro:
        itau.token()
    assert "HTTP 401" in str(erro.value)
    assert settings.itau_client_secret not in str(erro.value)


# --------------------------------------------------------------------------
# Credito, debito e estorno
# --------------------------------------------------------------------------


def test_credito_vira_entrada_e_debito_vira_saida(credenciais, monkeypatch):
    ligar(monkeypatch, [[
        evento("1", operation="C", valor="21824.00", historico="PIX RECEBIDO FERTIMAXI"),
        evento("2", operation="D", valor="45.90", historico="TARIFA PACOTE SERVICOS"),
    ]])
    lido = itau.buscar_extrato(INICIO, FIM)
    assert [(t["tipo"], t["valor"]) for t in lido["transacoes"]] == [("entrada", 21824.00), ("saida", 45.90)]


def test_debito_que_vem_com_valor_negativo_continua_saida(credenciais, monkeypatch):
    ligar(monkeypatch, [[evento("1", operation="D", valor="-45.90")]])
    lido = itau.buscar_extrato(INICIO, FIM)
    assert lido["transacoes"][0]["tipo"] == "saida" and lido["transacoes"][0]["valor"] == 45.90


def test_sem_operation_o_sinal_do_valor_decide(credenciais, monkeypatch):
    ligar(monkeypatch, [[evento("1", operation="", valor="-120,50")]])
    lido = itau.buscar_extrato(INICIO, FIM)
    assert lido["transacoes"][0] == {
        "fitid": "1", "data": date(2026, 9, 15), "valor": 120.50, "tipo": "saida",
        "descricao": "PIX RECEBIDO ATLANTI",
    }


def test_estorno_segue_o_sinal_do_banco_e_fica_marcado_na_descricao(credenciais, monkeypatch):
    """O estorno de um debito chega do banco como CREDITO: o `operation` ja vem
    invertido. Inverter de novo aqui faria o caixa fechar errado."""
    ligar(monkeypatch, [[
        evento("1", operation="C", valor="300.00", historico="TARIFA PACOTE SERVICOS", reversal=True),
        evento("2", operation="D", valor="500.00", historico="PIX ENVIADO", reversal=True),
    ]])
    lido = itau.buscar_extrato(INICIO, FIM)
    assert [(t["tipo"], t["valor"], t["descricao"]) for t in lido["transacoes"]] == [
        ("entrada", 300.00, "Estorno: TARIFA PACOTE SERVICOS"),
        ("saida", 500.00, "Estorno: PIX ENVIADO"),
    ]


# --------------------------------------------------------------------------
# Data contabil, linha de saldo e paginacao
# --------------------------------------------------------------------------


def test_a_data_do_lancamento_e_a_contabil_e_nao_o_instante_em_utc(credenciais, monkeypatch):
    """Exemplo da propria documentacao: evento 2024-08-06T02:59:00Z com data
    contabil 2024-08-05 (23h59 do dia 5 em Brasília)."""
    ligar(monkeypatch, [[evento("1", accounting="2024-08-05", momento="2024-08-06T02:59:00Z")]])
    lido = itau.buscar_extrato(date(2024, 8, 1), date(2024, 8, 31))
    assert lido["transacoes"][0]["data"] == date(2024, 8, 5)


def test_sem_data_contabil_o_instante_em_utc_volta_pro_horario_de_brasilia(credenciais, monkeypatch):
    ligar(monkeypatch, [[evento("1", accounting="", momento="2024-08-06T02:59:00Z")]])
    lido = itau.buscar_extrato(date(2024, 8, 1), date(2024, 8, 31))
    assert lido["transacoes"][0]["data"] == date(2024, 8, 5)


def test_linha_de_saldo_do_itau_nao_vira_lancamento(credenciais, monkeypatch):
    ligar(monkeypatch, [[
        evento("1", operation="C", valor="62.00", accounting="2026-08-31", historico="SALDO ANTERIOR"),
        evento("2", operation="D", valor="457.82", accounting="2026-09-01", historico="JUROS SALDO DEVEDOR C/C"),
    ], [
        evento("3", operation="D", valor="395.82", accounting="2026-09-01", historico="SALDO TOTAL DISPONÍVEL DIA"),
    ]])
    lido = itau.buscar_extrato(INICIO, FIM)
    assert [(t["data"].day, t["tipo"], t["valor"]) for t in lido["transacoes"]] == [(1, "saida", 457.82)]
    assert len(lido["linhas_de_saldo"]) == 2
    assert lido["saldo_anterior"] == {"data": date(2026, 8, 31), "valor": 62.0}
    # Sem o nome do campo de saldo na documentacao nao tem o que conferir.
    assert lido["saldo"] is None


def test_paginacao_le_todas_as_paginas_e_para_na_incompleta(credenciais, monkeypatch):
    falso = ligar(monkeypatch, [
        [evento("1"), evento("2")],
        [evento("3"), evento("4")],
        [evento("5")],
    ])
    lido = itau.buscar_extrato(INICIO, FIM)
    assert [t["fitid"] for t in lido["transacoes"]] == ["1", "2", "3", "4", "5"]
    assert [p["page"] for _, p, _ in falso.gets] == [1, 2, 3]
    assert {p["page_size"] for _, p, _ in falso.gets} == {2}
    assert lido["eventos_lidos"] == 5 and lido["paginas"] == 3
    assert falso.tokens == 1, "um token serve pra todas as páginas"


def test_pagina_repetida_nao_vira_lancamento_em_dobro(credenciais, monkeypatch):
    """Se a API devolver a mesma pagina de novo, a leitura para em vez de
    duplicar tudo."""
    ligar(monkeypatch, [[evento("1"), evento("2")], [evento("1"), evento("2")]])
    lido = itau.buscar_extrato(INICIO, FIM)
    assert [t["fitid"] for t in lido["transacoes"]] == ["1", "2"]


def test_tipos_de_evento_vem_no_resumo_pra_conferir_na_primeira_chamada(credenciais, monkeypatch, db):
    ligar(monkeypatch, [[evento("1"), evento("2", tipo="saldo", historico="SALDO TOTAL DISPONÍVEL DIA")]])
    bb = conta(db)
    db.commit()
    resumo = itau.importar_extrato(db, bb.id, INICIO, FIM)
    assert resumo["tipos_de_evento"] == {"lancamento": 1, "saldo": 1}
    assert resumo["eventos_lidos"] == 2


# --------------------------------------------------------------------------
# O campo do valor, que a documentacao nao mostra
# --------------------------------------------------------------------------


@pytest.mark.parametrize("campo", ["amount", "value", "transaction_amount", "valor"])
def test_valor_e_achado_em_qualquer_um_dos_nomes_plausiveis(credenciais, monkeypatch, campo):
    ligar(monkeypatch, [[evento("1", valor="1.234,56", campo_valor=campo)]])
    lido = itau.buscar_extrato(INICIO, FIM)
    assert lido["transacoes"][0]["valor"] == 1234.56


def test_valor_dentro_de_objeto_com_moeda(credenciais, monkeypatch):
    bruto = evento("1")
    bruto["amount"] = {"value": "980.75", "currency": "BRL"}
    ligar(monkeypatch, [[bruto]])
    lido = itau.buscar_extrato(INICIO, FIM)
    assert lido["transacoes"][0]["valor"] == 980.75


def test_saldo_em_objeto_vizinho_nao_e_confundido_com_o_valor(credenciais, monkeypatch):
    bruto = evento("1", valor="10.00")
    bruto["balance"] = {"amount": "999999.99"}
    ligar(monkeypatch, [[bruto]])
    lido = itau.buscar_extrato(INICIO, FIM)
    assert lido["transacoes"][0]["valor"] == 10.00


def test_valor_em_campo_desconhecido_falha_dizendo_o_que_veio(credenciais, monkeypatch):
    """O print da documentacao esta cortado no campo do valor. Se o nome real
    nao estiver na lista, a importacao PARA e mostra o evento inteiro - melhor
    ajustar um nome do que gravar caixa chutado."""
    bruto = evento("1")
    del bruto["amount"]
    bruto["montante_do_lancamento"] = "1000.00"
    ligar(monkeypatch, [[bruto]])
    with pytest.raises(itau.PayloadItauDesconhecido) as erro:
        itau.buscar_extrato(INICIO, FIM)
    mensagem = str(erro.value)
    assert "montante_do_lancamento" in mensagem and "amount" in mensagem
    assert "documentação" in mensagem


def test_lancamento_sem_data_tambem_falha_claro(credenciais, monkeypatch):
    bruto = evento("1")
    bruto["date"] = {}
    ligar(monkeypatch, [[bruto]])
    with pytest.raises(itau.PayloadItauDesconhecido, match="data contábil"):
        itau.buscar_extrato(INICIO, FIM)


def test_valor_zero_nao_vira_lancamento(credenciais, monkeypatch):
    ligar(monkeypatch, [[evento("1", valor="0.00")]])
    assert itau.buscar_extrato(INICIO, FIM)["transacoes"] == []


# --------------------------------------------------------------------------
# Entra no mesmo fluxo do OFX
# --------------------------------------------------------------------------

OFX = b"""OFXHEADER:100
DATA:OFXSGML
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260915120000[-3:BRT]<TRNAMT>21824.00<FITID>A1<MEMO>PIX RECEBIDO FERTIMAXI</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""


def test_lancamento_do_itau_fica_igual_ao_do_mesmo_extrato_em_ofx(credenciais, monkeypatch, db):
    """Mesma movimentacao pelas duas portas: tem que virar o mesmo lancamento
    (dia, tipo, valor, forma, descricao e origem)."""
    ligar(monkeypatch, [[evento("1", operation="C", valor="21824.00", historico="PIX RECEBIDO FERTIMAXI")]])
    pelo_arquivo = conta(db, "Itaú arquivo")
    pela_api = conta(db, "Itaú API")
    db.commit()

    imp.importar_extrato(db, pelo_arquivo.id, OFX, aplicar=True, usuario="dono")
    itau.importar_extrato(db, pela_api.id, INICIO, FIM, aplicar=True, usuario="dono")

    def como_ficou(conta_id):
        lanc = db.query(LancamentoCaixa).filter(LancamentoCaixa.conta_id == conta_id).one()
        return (lanc.data, lanc.tipo, lanc.valor, lanc.forma, lanc.descricao, lanc.origem)

    assert como_ficou(pela_api.id) == como_ficou(pelo_arquivo.id)
    assert como_ficou(pela_api.id) == (date(2026, 9, 15), "entrada", 21824.00, "PIX", "PIX RECEBIDO FERTIMAXI", "extrato")


def test_previa_nao_grava_e_puxar_de_novo_nao_duplica(credenciais, monkeypatch, db):
    ligar(monkeypatch, [[evento("1", valor="100.00"), evento("2", operation="D", valor="40.00")]])
    bb = conta(db)
    db.commit()

    previa = itau.importar_extrato(db, bb.id, INICIO, FIM)
    assert previa["fonte"] == "itau_api" and previa["aplicado"] is False
    assert previa["lancamentos"] == {"novos": 2, "ja_existiam": 0, "parecidos_ignorados": 0}
    assert previa["periodo"] == {"inicio": "2026-09-15", "fim": "2026-09-15"}
    assert previa["periodo_pedido"] == {"inicio": "2026-09-01", "fim": "2026-09-30"}
    assert db.query(LancamentoCaixa).count() == 0

    feito = itau.importar_extrato(db, bb.id, INICIO, FIM, aplicar=True)
    assert feito["aplicado"] is True and db.query(LancamentoCaixa).count() == 2
    assert {l.id_externo for l in db.query(LancamentoCaixa).all()} == {"itau:1", "itau:2"}

    de_novo = itau.importar_extrato(db, bb.id, INICIO, FIM, aplicar=True)
    assert de_novo["lancamentos"]["novos"] == 0 and db.query(LancamentoCaixa).count() == 2


def test_o_que_veio_do_ofx_nao_entra_de_novo_pela_api(credenciais, monkeypatch, db):
    """Transicao: quem importou o OFX do mes e depois puxou o mesmo mes na API
    nao pode lancar tudo em dobro - mesmo dia, tipo e valor ficam de fora."""
    ligar(monkeypatch, [[evento("Z9", operation="C", valor="21824.00", historico="PIX RECEBIDO FERTIMAXI")]])
    bb = conta(db)
    db.commit()
    imp.importar_extrato(db, bb.id, OFX, aplicar=True)
    assert db.query(LancamentoCaixa).count() == 1

    resumo = itau.importar_extrato(db, bb.id, INICIO, FIM, aplicar=True)
    assert resumo["lancamentos"] == {"novos": 0, "ja_existiam": 0, "parecidos_ignorados": 1}
    assert db.query(LancamentoCaixa).count() == 1


def test_conta_inexistente_nao_chega_a_chamar_o_banco(credenciais, monkeypatch, db):
    falso = ligar(monkeypatch, [[evento("1")]])
    with pytest.raises(Exception, match="Conta bancária"):
        itau.importar_extrato(db, 999, INICIO, FIM)
    assert falso.tokens == 0 and falso.gets == []


# --------------------------------------------------------------------------
# Rota
# --------------------------------------------------------------------------


def test_rota_mostra_a_previa_e_depois_grava(credenciais, monkeypatch, db):
    ligar(monkeypatch, [[evento("1", valor="100.00"), evento("2", operation="D", valor="40.00")]])
    bb = conta(db)
    db.commit()
    http = cliente_http(db)
    endereco = f"/financeiro/contas/{bb.id}/extrato-itau"
    periodo = {"inicio": "2026-09-01", "fim": "2026-09-30"}

    previa = http.post(endereco, params=periodo)
    assert previa.status_code == 200
    assert previa.json()["lancamentos"]["novos"] == 2 and previa.json()["aplicado"] is False
    assert db.query(LancamentoCaixa).count() == 0

    feito = http.post(endereco, params={**periodo, "aplicar": True})
    assert feito.status_code == 200 and feito.json()["aplicado"] is True
    assert db.query(LancamentoCaixa).count() == 2


def test_rota_recusa_periodo_invertido_e_periodo_longo(credenciais, monkeypatch, db):
    ligar(monkeypatch, [[]])
    bb = conta(db)
    db.commit()
    http = cliente_http(db)
    endereco = f"/financeiro/contas/{bb.id}/extrato-itau"
    invertido = http.post(endereco, params={"inicio": "2026-09-30", "fim": "2026-09-01"})
    assert invertido.status_code == 400 and "antes do início" in invertido.json()["detail"]
    longo = http.post(endereco, params={"inicio": "2026-01-01", "fim": "2026-12-31"})
    assert longo.status_code == 400 and "3 meses" in longo.json()["detail"]


def test_rota_devolve_502_com_o_payload_quando_o_campo_do_valor_e_outro(credenciais, monkeypatch, db):
    bruto = evento("1")
    del bruto["amount"]
    bruto["montante_do_lancamento"] = "1000.00"
    ligar(monkeypatch, [[bruto]])
    bb = conta(db)
    db.commit()
    resposta = cliente_http(db).post(f"/financeiro/contas/{bb.id}/extrato-itau",
                                     params={"inicio": "2026-09-01", "fim": "2026-09-30"})
    assert resposta.status_code == 502 and "montante_do_lancamento" in resposta.json()["detail"]


def test_rota_de_extrato_e_so_de_administrador(credenciais, monkeypatch, db):
    ligar(monkeypatch, [[evento("1")]])
    bb = conta(db)
    db.commit()
    app = FastAPI()
    app.include_router(rotas.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        email="operador@atlantico", role="user", paginas_liberadas="/financeiro/caixa")
    resposta = TestClient(app).post(f"/financeiro/contas/{bb.id}/extrato-itau",
                                    params={"inicio": "2026-09-01", "fim": "2026-09-30"})
    assert resposta.status_code == 403


def test_certificado_pode_vir_colado_na_variavel(monkeypatch, tmp_path):
    """No servidor nao ha onde largar arquivo: o .crt e a .key vem colados na
    variavel de ambiente e o sistema escreve os dois em disco."""
    from app.config import settings
    from app.servicos import itau_extrato as itau

    monkeypatch.setattr(settings, "itau_cert_path", "", raising=False)
    monkeypatch.setattr(settings, "itau_cert_key_path", "", raising=False)
    monkeypatch.setattr(settings, "itau_cert_pem", "-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----", raising=False)
    monkeypatch.setattr(settings, "itau_cert_key_pem", "-----BEGIN PRIVATE KEY-----\ndef\n-----END PRIVATE KEY-----", raising=False)

    crt, key = itau._certificado()

    assert Path(crt).read_text(encoding="utf-8").startswith("-----BEGIN CERTIFICATE-----")
    assert Path(key).read_text(encoding="utf-8").startswith("-----BEGIN PRIVATE KEY-----")
    # Nada disso encosta no repositorio.
    assert "GerenciadorAtlantico" not in crt and "GerenciadorAtlantico" not in key


def test_caminho_de_arquivo_vence_o_conteudo_colado(monkeypatch):
    from app.config import settings
    from app.servicos import itau_extrato as itau

    monkeypatch.setattr(settings, "itau_cert_path", "/etc/itau/prod.crt", raising=False)
    monkeypatch.setattr(settings, "itau_cert_key_path", "/etc/itau/prod.key", raising=False)
    monkeypatch.setattr(settings, "itau_cert_pem", "-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----", raising=False)

    assert itau._certificado() == ("/etc/itau/prod.crt", "/etc/itau/prod.key")
