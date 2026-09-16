"""Importar CNH, CRLV e RNTRC: todos ao mesmo tempo, uma chamada por arquivo.

Antes eram lidos um depois do outro, cada um com duas chamadas a IA (tipo,
depois campos): tres documentos, seis chamadas em fila. A IA aqui e
simulada - nenhum documento sai do computador.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import get_current_user  # noqa: E402
from app.routers import bsoft as rotas_bsoft  # noqa: E402
from app.servicos import ocr_gemini  # noqa: E402

CNH = {"nome": "TALISSON JUNIOR GUIMARAES RIBEIRO", "cpf": "121.597.816-22", "numero": "123", "categoria": "E"}
CRLV_CAVALO = {"placa": "PFJ2I64", "categoria_veiculo": "CAVALO"}
CRLV_CARRETA = {"placa": "NZB4H89", "categoria_veiculo": "SEMI-REBOQUE 1"}


def leitura_simulada(espera=0.0, falhar=()):
    def ler(caminho):
        time.sleep(espera)
        nome = Path(caminho).read_bytes().decode()
        if nome in falhar:
            raise RuntimeError("IA fora do ar")
        return {
            "cnh": {"tipo": "CNH", "dados": dict(CNH)},
            "rntrc": {"tipo": "RNTRC", "dados": {"rntrc": "0123456"}},
            "cavalo": {"tipo": "CRLV", "dados": dict(CRLV_CAVALO)},
            "carreta": {"tipo": "CRLV", "dados": dict(CRLV_CARRETA)},
        }.get(nome, {"tipo": "DESCONHECIDO", "dados": {}})
    return ler


@pytest.fixture
def cliente():
    app = FastAPI()
    app.include_router(rotas_bsoft.router)
    app.dependency_overrides[get_current_user] = lambda: None
    return TestClient(app)


def enviar(cliente, *nomes):
    # O conteudo do arquivo e o nome do caso: a leitura simulada decide por ele.
    arquivos = [("files", (f"{nome}.pdf", nome.encode(), "application/pdf")) for nome in nomes]
    return cliente.post("/bsoft/importar-documentos", files=arquivos)


def test_tres_documentos_sao_lidos_ao_mesmo_tempo(cliente, monkeypatch):
    monkeypatch.setattr(ocr_gemini, "ler_documento_com_gemini", leitura_simulada(espera=0.6))
    inicio = time.perf_counter()
    resposta = enviar(cliente, "cnh", "cavalo", "carreta")
    duracao = time.perf_counter() - inicio
    assert resposta.status_code == 200, resposta.text
    # Em fila seriam 1,8 s; juntos, perto do mais lento.
    assert duracao < 1.4, f"demorou {duracao:.2f}s - parece estar em fila"
    corpo = resposta.json()
    assert corpo["motorista"]["nome"] == CNH["nome"]
    assert [v["placa"] for v in corpo["veiculos"]] == ["PFJ2I64", "NZB4H89"]


def test_rntrc_nao_apaga_o_que_a_cnh_leu(cliente, monkeypatch):
    monkeypatch.setattr(ocr_gemini, "ler_documento_com_gemini", leitura_simulada())
    motorista = enviar(cliente, "cnh", "rntrc").json()["motorista"]
    assert motorista["nome"] == CNH["nome"] and motorista["rntrc"] == "0123456"


def test_arquivo_com_erro_nao_derruba_os_outros(cliente, monkeypatch):
    monkeypatch.setattr(ocr_gemini, "ler_documento_com_gemini", leitura_simulada(falhar=("cavalo",)))
    monkeypatch.setattr(ocr_gemini, "classificar_e_extrair_documento_com_gemini", leitura_simulada(falhar=("cavalo",)))
    monkeypatch.setattr(rotas_bsoft, "_classificar_e_extrair_fallback", leitura_simulada(falhar=("cavalo",)))
    corpo = enviar(cliente, "cnh", "cavalo", "carreta").json()
    assert corpo["motorista"]["nome"] == CNH["nome"]
    assert [v["placa"] for v in corpo["veiculos"]] == ["NZB4H89"]


def test_se_a_leitura_combinada_falha_usa_o_caminho_antigo(cliente, monkeypatch):
    monkeypatch.setattr(ocr_gemini, "ler_documento_com_gemini", leitura_simulada(falhar=("cavalo",)))
    monkeypatch.setattr(ocr_gemini, "classificar_e_extrair_documento_com_gemini", leitura_simulada())
    assert [v["placa"] for v in enviar(cliente, "cavalo").json()["veiculos"]] == ["PFJ2I64"]


# --------------------------------------------------------------------------
# A leitura combinada: uma chamada, o bloco certo pra cada tipo
# --------------------------------------------------------------------------


@pytest.mark.parametrize("resposta_ia, esperado", [
    ({"tipo": "CNH", "cnh": CNH, "crlv": {"placa": "LIXO"}}, {"tipo": "CNH", "dados": CNH}),
    ({"tipo": "CRLV", "crlv": CRLV_CAVALO}, {"tipo": "CRLV", "dados": CRLV_CAVALO}),
    ({"tipo": "RNTRC", "rntrc": "0123456"}, {"tipo": "RNTRC", "dados": {"rntrc": "0123456"}}),
    ({"tipo": "OUTRA COISA"}, {"tipo": "DESCONHECIDO", "dados": {}}),
])
def test_leitura_combinada_devolve_o_bloco_do_tipo(monkeypatch, tmp_path, resposta_ia, esperado):
    chamadas = []

    def extrair(caminho, prompt, schema):
        chamadas.append(prompt)
        return resposta_ia

    monkeypatch.setattr(ocr_gemini, "_extrair_com_schema", extrair)
    arquivo = tmp_path / "doc.pdf"
    arquivo.write_bytes(b"x")
    assert ocr_gemini.ler_documento_com_gemini(str(arquivo)) == esperado
    assert len(chamadas) == 1
    # As mesmas instrucoes das leituras especificas.
    assert ocr_gemini.PROMPT_CNH in chamadas[0] and ocr_gemini.PROMPT_CRLV in chamadas[0]
