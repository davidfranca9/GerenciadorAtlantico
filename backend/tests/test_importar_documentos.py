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


def test_se_a_ia_falha_le_sem_ia_e_avisa_qual_arquivo(cliente, monkeypatch):
    # O caminho antigo de duas chamadas saiu: falhava igual e dobrava a espera.
    segunda_chamada = []
    monkeypatch.setattr(ocr_gemini, "ler_documento_com_gemini", leitura_simulada(falhar=("cavalo",)))
    monkeypatch.setattr(ocr_gemini, "classificar_e_extrair_documento_com_gemini", lambda c: segunda_chamada.append(c))
    monkeypatch.setattr(rotas_bsoft, "_classificar_e_extrair_fallback", leitura_simulada())
    corpo = enviar(cliente, "cnh", "cavalo").json()
    assert segunda_chamada == []
    assert [v["placa"] for v in corpo["veiculos"]] == ["PFJ2I64"]
    leituras = {l["arquivo"]: l for l in corpo["leituras"]}
    assert leituras["cnh.pdf"]["metodo"] == "ia" and leituras["cnh.pdf"]["aviso"] == ""
    assert leituras["cavalo.pdf"]["metodo"] == "ocr_local" and leituras["cavalo.pdf"]["aviso"] == "a IA não respondeu"
    assert all(isinstance(l["segundos"], float) for l in corpo["leituras"])


# --------------------------------------------------------------------------
# O que a IA devolve e conferido antes de ir pra tela
# --------------------------------------------------------------------------


def test_cnh_da_foto_do_whatsapp_sai_limpa():
    # Leitura real de 16/09/2026: "OL RE" antes do nome e categoria "X".
    lido = {
        "nome": "OL RE FABIO GIOVANI SEBEN", "cpf": "016.755.820-09", "numero": "04392175535",
        "seguro": "90989746464", "categoria": "X", "protocolo": "2407044568",
        "dtValidade": "04/04/2032", "dtExpedicao": "03/06/2022", "dtPrimeiraExpedicao": "26/06/2008",
        "dtNascimento": "15/12/1989 MARAU/RS",
    }
    limpo = ocr_gemini.limpar_cnh(lido)
    assert limpo["nome"] == "FABIO GIOVANI SEBEN"
    assert limpo["categoria"] == ""  # melhor em branco que errado
    assert limpo["dtNascimento"] == "15/12/1989"
    assert (limpo["cpf"], limpo["numero"], limpo["protocolo"]) == ("016.755.820-09", "04392175535", "2407044568")


@pytest.mark.parametrize("categoria, esperado", [("e", "E"), ("A E", "AE"), ("AB", "AB"), ("ACC", ""), ("", "")])
def test_categoria_so_passa_se_existir(categoria, esperado):
    assert ocr_gemini.limpar_cnh({"categoria": categoria})["categoria"] == esperado


@pytest.mark.parametrize("nome, esperado", [
    ("FABIO GIOVANI SEBEN", "FABIO GIOVANI SEBEN"),
    ("NOME: JOSE DA SILVA", "JOSE DA SILVA"),
    ("2 e 1 JOAO DE SOUZA", "JOAO DE SOUZA"),
    ("ANA", "ANA"),
])
def test_nome_perde_so_o_lixo_do_comeco(nome, esperado):
    assert ocr_gemini.limpar_cnh({"nome": nome})["nome"] == esperado


def test_cpf_incompleto_fica_vazio():
    assert ocr_gemini.limpar_cnh({"cpf": "016.755.820"})["cpf"] == ""


# --------------------------------------------------------------------------
# A chamada: raciocinio curto, nova tentativa so pra falha passageira
# --------------------------------------------------------------------------


class _Resposta:
    text = '{"tipo": "RNTRC", "rntrc": "123"}'


class _ClienteFalso:
    def __init__(self, falhas=()):
        self.falhas = list(falhas)
        self.configs = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.configs.append(config)
        if self.falhas:
            raise self.falhas.pop(0)
        return _Resposta()


def _erro(codigo, mensagem="erro"):
    classe = ocr_gemini.genai_errors.ClientError if codigo < 500 else ocr_gemini.genai_errors.ServerError
    return classe(codigo, {"error": {"code": codigo, "message": mensagem, "status": "X"}})


@pytest.fixture
def arquivo(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr_gemini, "_aceita_nivel_raciocinio", True)
    monkeypatch.setattr(ocr_gemini.time, "sleep", lambda s: None)
    caminho = tmp_path / "doc.pdf"
    caminho.write_bytes(b"%PDF")
    return str(caminho)


def test_pede_raciocinio_curto(monkeypatch, arquivo):
    cliente = _ClienteFalso()
    monkeypatch.setattr(ocr_gemini, "_client", lambda: cliente)
    assert ocr_gemini.ler_documento_com_gemini(arquivo)["tipo"] == "RNTRC"
    assert cliente.configs[0].thinking_config.thinking_level == ocr_gemini.NIVEL_RACIOCINIO


def test_limite_de_uso_tenta_de_novo_uma_vez(monkeypatch, arquivo):
    cliente = _ClienteFalso(falhas=[_erro(429)])
    monkeypatch.setattr(ocr_gemini, "_client", lambda: cliente)
    assert ocr_gemini.ler_documento_com_gemini(arquivo)["tipo"] == "RNTRC"
    assert len(cliente.configs) == 2


def test_erro_de_pedido_nao_repete(monkeypatch, arquivo):
    cliente = _ClienteFalso(falhas=[_erro(400, "arquivo invalido")])
    monkeypatch.setattr(ocr_gemini, "_client", lambda: cliente)
    with pytest.raises(ocr_gemini.genai_errors.ClientError):
        ocr_gemini.ler_documento_com_gemini(arquivo)
    assert len(cliente.configs) == 1


def test_modelo_sem_nivel_de_raciocinio_segue_sem(monkeypatch, arquivo):
    cliente = _ClienteFalso(falhas=[_erro(400, "thinking_level is not supported for this model")])
    monkeypatch.setattr(ocr_gemini, "_client", lambda: cliente)
    assert ocr_gemini.ler_documento_com_gemini(arquivo)["tipo"] == "RNTRC"
    assert cliente.configs[1].thinking_config is None
    assert ocr_gemini._aceita_nivel_raciocinio is False


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
    if esperado["tipo"] == "CNH":
        # A CNH passa pela conferencia de formato antes de voltar.
        esperado = {"tipo": "CNH", "dados": ocr_gemini.limpar_cnh(CNH)}
    assert ocr_gemini.ler_documento_com_gemini(str(arquivo)) == esperado
    assert len(chamadas) == 1
    # As mesmas instrucoes das leituras especificas.
    assert ocr_gemini.PROMPT_CNH in chamadas[0] and ocr_gemini.PROMPT_CRLV in chamadas[0]
