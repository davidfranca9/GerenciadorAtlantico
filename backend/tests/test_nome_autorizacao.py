"""A autorizacao sai no nome do motorista quando ele existe; senao, do cliente.

Vale pro arquivo baixado, pro anexo e pro assunto do e-mail. Nenhum e-mail
sai daqui: o envio e simulado.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos.comunicacao import montar_autorizacao_agendamento  # noqa: E402
from tests.apoio_documentos import cliente_http  # noqa: E402

PRODUTO = {
    "contrato": "41556", "produto": "UREIA PRILL MICROGRANULADA 46% N", "embalagem": "SACARIA",
    "toneladas": "32", "cidade": "Montes Claros", "cliente": "WAGMAR JOSE DE OLIVEIRA",
}


def pedido(**motorista):
    base = {"template": "AFL", "produtos": [PRODUTO], "data_carregamento": "15/09/2026"}
    base.update(motorista)
    return base


def nome_do_arquivo(resposta) -> str:
    cabecalho = resposta.headers["content-disposition"]
    if "filename*=" in cabecalho:
        return unquote(cabecalho.split("filename*=")[1].split("''", 1)[1])
    return cabecalho.split("filename=")[1].strip('"')


# --------------------------------------------------------------------------
# Assunto do e-mail
# --------------------------------------------------------------------------


def test_assunto_com_motorista_leva_o_nome_dele():
    titulo, _ = montar_autorizacao_agendamento("WAGMAR JOSE DE OLIVEIRA", "41556", "15/09/2026", motorista="TALISSON JUNIOR")
    assert titulo == "AUTORIZAÇÃO AGENDAMENTO: TALISSON JUNIOR - Nº 41556"


def test_assunto_sem_motorista_leva_o_cliente():
    for vazio in ("", "   ", None):
        titulo, _ = montar_autorizacao_agendamento("WAGMAR JOSE DE OLIVEIRA", "41556", "15/09/2026", motorista=vazio)
        assert titulo == "AUTORIZAÇÃO AGENDAMENTO: WAGMAR JOSE DE OLIVEIRA - Nº 41556"


# --------------------------------------------------------------------------
# Arquivo baixado
# --------------------------------------------------------------------------


def _baixar(monkeypatch, corpo):
    cliente, documentos = cliente_http(db=None)
    # Baixar tambem registra o agendamento no banco; aqui so interessa o arquivo.
    monkeypatch.setattr(documentos, "_salvar_agendamento_oc", lambda *a, **k: SimpleNamespace(id=7))
    return cliente.post("/ordens-coleta/gerar-autorizacao", json=corpo)


def test_arquivo_sem_motorista_sai_no_nome_do_cliente(monkeypatch):
    resposta = _baixar(monkeypatch, pedido())
    assert resposta.status_code == 200, resposta.text
    assert nome_do_arquivo(resposta) == "Autorizacao de carregamento_WAGMAR JOSE DE OLIVEIRA.xlsx"


def test_arquivo_com_motorista_sai_no_nome_dele(monkeypatch):
    resposta = _baixar(monkeypatch, pedido(nome="TALISSON JUNIOR GUIMARAES RIBEIRO", cpf="12159781622", placa1="PFJ2I64"))
    assert resposta.status_code == 200, resposta.text
    assert nome_do_arquivo(resposta) == "Autorizacao de carregamento_TALISSON JUNIOR GUIMARAES RIBEIRO.xlsx"


# --------------------------------------------------------------------------
# E-mail (anexo e assunto), pela rota da tela de Contratos
# --------------------------------------------------------------------------


def _enviar(monkeypatch, corpo):
    # Enviar agora registra o agendamento: o banco entra simulado.
    cliente, documentos = cliente_http(db=SimpleNamespace(commit=lambda: None))
    monkeypatch.setattr(documentos, "_salvar_agendamento_oc", lambda *a, **k: SimpleNamespace(id=7))
    enviados = []
    monkeypatch.setattr(
        documentos, "send_email_message",
        lambda destinatarios, assunto, corpo_html, anexos, **kw: enviados.append((assunto, [Path(a).name for a in anexos])),
    )
    resposta = cliente.post("/ordens-coleta/enviar-autorizacao-email", json=corpo)
    return resposta, enviados


def test_email_sem_motorista_leva_o_cliente_no_assunto_e_no_anexo(monkeypatch):
    resposta, enviados = _enviar(monkeypatch, pedido())
    assert resposta.status_code == 200, resposta.text
    assert enviados == [(
        "AUTORIZAÇÃO AGENDAMENTO: WAGMAR JOSE DE OLIVEIRA - Nº 41556",
        ["Autorizacao de carregamento_WAGMAR JOSE DE OLIVEIRA.xlsx"],
    )]


def test_email_com_motorista_leva_o_motorista_no_assunto_e_no_anexo(monkeypatch):
    resposta, enviados = _enviar(monkeypatch, pedido(nome="TALISSON JUNIOR GUIMARAES RIBEIRO"))
    assert resposta.status_code == 200, resposta.text
    assert enviados == [(
        "AUTORIZAÇÃO AGENDAMENTO: TALISSON JUNIOR GUIMARAES RIBEIRO - Nº 41556",
        ["Autorizacao de carregamento_TALISSON JUNIOR GUIMARAES RIBEIRO.xlsx"],
    )]
