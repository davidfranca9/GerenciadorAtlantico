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


def test_se_a_ia_falha_nao_preenche_chute_e_avisa_qual_arquivo(cliente, monkeypatch):
    # 16/09/2026: com a IA fora, o OCR local trocou registro e seguro da CNH
    # e levou 30 s. Agora o arquivo fica de fora, com aviso pra reenviar.
    ocr_local, segunda_chamada = [], []
    monkeypatch.setattr(ocr_gemini, "ler_documento_com_gemini", leitura_simulada(falhar=("cavalo",)))
    monkeypatch.setattr(ocr_gemini, "classificar_e_extrair_documento_com_gemini", lambda c: segunda_chamada.append(c))
    monkeypatch.setattr(rotas_bsoft, "_classificar_e_extrair_fallback", lambda c: ocr_local.append(c))
    corpo = enviar(cliente, "cnh", "cavalo").json()
    assert ocr_local == [] and segunda_chamada == []
    assert corpo["veiculos"] == [] and corpo["motorista"]["nome"] == CNH["nome"]
    leituras = {l["arquivo"]: l for l in corpo["leituras"]}
    assert leituras["cnh.pdf"]["metodo"] == "ia" and leituras["cnh.pdf"]["aviso"] == ""
    assert leituras["cavalo.pdf"]["metodo"] == "falhou" and leituras["cavalo.pdf"]["aviso"] == "a IA não conseguiu ler o arquivo"
    assert leituras["cavalo.pdf"]["erro_ia"] == "RuntimeError: IA fora do ar" and leituras["cnh.pdf"]["erro_ia"] == ""
    assert all(isinstance(l["segundos"], float) for l in corpo["leituras"])


def test_ia_ocupada_avisa_pra_tentar_de_novo(cliente, monkeypatch):
    def ocupada(caminho):
        raise ocr_gemini.genai_errors.ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})
    monkeypatch.setattr(ocr_gemini, "ler_documento_com_gemini", ocupada)
    leitura = enviar(cliente, "cnh").json()["leituras"][0]
    assert (leitura["metodo"], leitura["aviso"]) == ("falhou", "a IA está ocupada agora")


def test_sem_ia_configurada_usa_o_ocr_local_com_aviso(cliente, monkeypatch):
    def sem_chave(caminho):
        raise ocr_gemini.GeminiIndisponivel("GEMINI_API_KEY nao configurada")
    monkeypatch.setattr(ocr_gemini, "ler_documento_com_gemini", sem_chave)
    monkeypatch.setattr(rotas_bsoft, "_classificar_e_extrair_fallback", leitura_simulada())
    corpo = enviar(cliente, "cavalo").json()
    assert [v["placa"] for v in corpo["veiculos"]] == ["PFJ2I64"]
    assert (corpo["leituras"][0]["metodo"], corpo["leituras"][0]["aviso"]) == ("ocr_local", "IA não configurada")


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
        self.modelos = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.configs.append(config)
        self.modelos.append(model)
        if self.falhas:
            raise self.falhas.pop(0)
        return _Resposta()


def _erro(codigo, mensagem="erro"):
    classe = ocr_gemini.genai_errors.ClientError if codigo < 500 else ocr_gemini.genai_errors.ServerError
    return classe(codigo, {"error": {"code": codigo, "message": mensagem, "status": "X"}})


@pytest.fixture
def arquivo(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr_gemini, "_sem_nivel_raciocinio", set())
    monkeypatch.setattr(ocr_gemini, "_modelos_inexistentes", set())
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


def test_erro_de_pedido_nao_repete_no_mesmo_modelo(monkeypatch, arquivo):
    cliente = _ClienteFalso(falhas=[_erro(400, "arquivo invalido")] * len(ocr_gemini.MODELOS))
    monkeypatch.setattr(ocr_gemini, "_client", lambda: cliente)
    with pytest.raises(ocr_gemini.genai_errors.ClientError):
        ocr_gemini.ler_documento_com_gemini(arquivo)
    assert cliente.modelos == list(ocr_gemini.MODELOS)


def test_modelo_aposentado_passa_pro_proximo_e_nao_tenta_mais(monkeypatch, arquivo):
    cliente = _ClienteFalso(falhas=[_erro(404, "models/gemini-3.6-flash is not found")])
    monkeypatch.setattr(ocr_gemini, "_client", lambda: cliente)
    assert ocr_gemini.ler_documento_com_gemini(arquivo)["tipo"] == "RNTRC"
    assert cliente.modelos == [ocr_gemini.MODELOS[0], ocr_gemini.MODELOS[1]]
    ocr_gemini.ler_documento_com_gemini(arquivo)
    assert cliente.modelos[-1] == ocr_gemini.MODELOS[1]


def test_sem_cota_tenta_de_novo_e_depois_outro_modelo(monkeypatch, arquivo):
    cliente = _ClienteFalso(falhas=[_erro(429, "quota"), _erro(429, "quota")])
    monkeypatch.setattr(ocr_gemini, "_client", lambda: cliente)
    assert ocr_gemini.ler_documento_com_gemini(arquivo)["tipo"] == "RNTRC"
    assert cliente.modelos == [ocr_gemini.MODELOS[0], ocr_gemini.MODELOS[0], ocr_gemini.MODELOS[1]]


def test_modelo_sem_nivel_de_raciocinio_segue_sem(monkeypatch, arquivo):
    cliente = _ClienteFalso(falhas=[_erro(400, "thinking_level is not supported for this model")])
    monkeypatch.setattr(ocr_gemini, "_client", lambda: cliente)
    assert ocr_gemini.ler_documento_com_gemini(arquivo)["tipo"] == "RNTRC"
    assert cliente.configs[1].thinking_config is None
    assert ocr_gemini.MODELOS[0] in ocr_gemini._sem_nivel_raciocinio


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
    if esperado["tipo"] == "CRLV":
        esperado = {"tipo": "CRLV", "dados": ocr_gemini.limpar_crlv(CRLV_CAVALO)}
    assert ocr_gemini.ler_documento_com_gemini(str(arquivo)) == esperado
    assert len(chamadas) == 1
    # As mesmas instrucoes das leituras especificas.
    assert ocr_gemini.PROMPT_CNH in chamadas[0] and ocr_gemini.PROMPT_CRLV in chamadas[0]


# --------------------------------------------------------------------------
# O pedido que vai pro Gemini
# --------------------------------------------------------------------------


def _listas_de_opcoes(schema, caminho="schema"):
    if isinstance(schema, dict):
        if "enum" in schema:
            yield caminho, schema["enum"]
        for chave, valor in schema.items():
            yield from _listas_de_opcoes(valor, f"{caminho}.{chave}")


def test_nenhuma_lista_de_opcoes_tem_opcao_vazia(monkeypatch, arquivo):
    # 16/09/2026: "enum[9]: cannot be empty" - a API recusava toda leitura.
    enviados = []

    def gerar(client, modelo, conteudo, schema):
        enviados.append(schema)
        return _Resposta()

    monkeypatch.setattr(ocr_gemini, "_client", lambda: object())
    monkeypatch.setattr(ocr_gemini, "_gerar", gerar)
    ocr_gemini.ler_documento_com_gemini(arquivo)
    ocr_gemini.extrair_dados_cnh_com_gemini(arquivo)
    ocr_gemini.extrair_dados_crlv_com_gemini(arquivo)
    listas = [item for schema in enviados for item in _listas_de_opcoes(schema)]
    assert len(listas) >= 4
    for caminho, opcoes in listas:
        assert opcoes and all(str(o).strip() for o in opcoes), caminho


def test_campo_com_opcoes_nao_e_obrigatorio():
    for schema in (ocr_gemini.CNH_SCHEMA, ocr_gemini.CRLV_SCHEMA):
        obrigatorios = set(schema["required"])
        com_opcoes = {campo for campo, regra in schema["properties"].items() if "enum" in regra}
        assert not (obrigatorios & com_opcoes) - {"categoria_veiculo"}


def test_crlv_sem_marca_volta_com_campo_vazio():
    dados = ocr_gemini.limpar_crlv({"placa": "JDA-8A89", "eixos": 4})
    assert dados["marca"] == "" and dados["tipo_carroceria"] == "" and dados["eixos"] == "4"
