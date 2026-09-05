"""Testes do cliente Bsoft e da camada fiscal.

Tudo com mock - nenhum teste toca a API real nem o banco de producao.
Rodar de dentro de backend/:  python -m pytest tests -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.servicos import bsoft_client, bsoft_fiscal  # noqa: E402


class RespostaFalsa:
    def __init__(self, status_code=200, corpo=None, texto=None):
        self.status_code = status_code
        self._corpo = corpo
        self.text = texto if texto is not None else ("" if corpo is None else "{}")

    def json(self):
        if self._corpo is None:
            raise ValueError("sem corpo")
        return self._corpo


@pytest.fixture(autouse=True)
def credenciais():
    with patch.object(settings, "bsoft_api_user", "usuario"), \
         patch.object(settings, "bsoft_api_password", "senha"), \
         patch.object(settings, "bsoft_api_base_url", "https://exemplo.bsoft.app/services/index.php"):
        yield


def test_sanitizar_remove_campos_sensiveis():
    limpo = bsoft_client.sanitizar({"arquivo": "AAAA", "cpf_motorista": "12345678900", "valorFrete": 10})
    assert limpo["arquivo"] == "<omitido>"
    assert limpo["cpf_motorista"] == "<omitido>"
    assert limpo["valorFrete"] == 10


def test_sanitizar_encurta_string_longa():
    assert bsoft_client.sanitizar("x" * 500).startswith("<string de 500")


def test_204_vira_lista_vazia():
    with patch("requests.request", return_value=RespostaFalsa(204, texto="")):
        assert bsoft_client.listar("/transporte/v1/agencias") == []


def test_listagem_forca_paginacao_maxima_do_bsoft():
    with patch("requests.request", return_value=RespostaFalsa(200, [{"id": 1}], "[]")) as req:
        bsoft_client.listar("/transporte/v1/agencias")
    assert req.call_args.kwargs["params"]["fim"] == 100


def test_erro_http_vira_bsoft_error_com_status():
    with patch("requests.request", return_value=RespostaFalsa(400, texto='{"message":"invalido"}')):
        with pytest.raises(bsoft_client.BsoftError) as exc:
            bsoft_client.chamar("GET", "/transporte/v1/agencias")
    assert exc.value.status == 400


def test_get_tem_retry_em_falha_de_rede():
    with patch("requests.request", side_effect=requests.exceptions.ConnectionError("queda")) as req, \
         patch("time.sleep"):
        with pytest.raises(bsoft_client.BsoftError):
            bsoft_client.chamar("GET", "/transporte/v1/agencias")
    assert req.call_count == bsoft_client.MAX_TENTATIVAS_LEITURA


def test_post_nunca_repete_apos_timeout():
    """Repetir criacao fiscal apos timeout pode duplicar documento."""
    with patch.object(settings, "bsoft_emissao_habilitada", True), \
         patch("requests.request", side_effect=requests.exceptions.Timeout("estourou")) as req, \
         patch("time.sleep"):
        with pytest.raises(bsoft_client.BsoftError):
            bsoft_client.chamar("POST", "/transporte/v1/conhecimentos", json_body={}, operacao_de_escrita=True)
    assert req.call_count == 1


def test_trava_bloqueia_escrita_sem_enviar_requisicao():
    with patch.object(settings, "bsoft_emissao_habilitada", False), \
         patch("requests.request") as req:
        with pytest.raises(bsoft_client.BsoftEmissaoBloqueada):
            bsoft_client.chamar("POST", "/transporte/v1/conhecimentos", json_body={}, operacao_de_escrita=True)
    req.assert_not_called()


def test_trava_nao_atrapalha_leitura():
    with patch.object(settings, "bsoft_emissao_habilitada", False), \
         patch("requests.request", return_value=RespostaFalsa(200, [{"id": "2"}], "[]")):
        assert bsoft_client.listar("/transporte/v1/agencias") == [{"id": "2"}]


def test_criar_cte_via_nfe_usa_chaves_e_ignora_ids():
    with patch.object(settings, "bsoft_emissao_habilitada", True), \
         patch("requests.request", return_value=RespostaFalsa(200, {"codConhecimentos": "9"}, "{}")) as req:
        resposta = bsoft_fiscal.criar_cte_via_nfe(
            parametro_criacao_cte="16", ids_nfe=["1"], chaves_nfe=["9" * 44], valores={"valorFrete": "130.00"}
        )
    corpo = req.call_args.kwargs["json"]
    assert corpo["chavesNFe"] == ["9" * 44]
    assert "ids" not in corpo
    assert corpo["parametroCriacaoCTe"] == "16"
    assert corpo["valorFrete"] == "130.00"
    assert resposta == {"codConhecimentos": "9"}


def test_criar_cte_exige_nfe():
    with pytest.raises(ValueError):
        bsoft_fiscal.criar_cte_via_nfe(parametro_criacao_cte="16")


def test_importar_nfe_envia_xml_em_base64():
    with patch.object(settings, "bsoft_emissao_habilitada", True), \
         patch("requests.request", return_value=RespostaFalsa(200, {"codNFe": "4975"}, "{}")) as req:
        bsoft_fiscal.importar_nfe_por_xml(b"<nfe/>")
    assert req.call_args.kwargs["json"]["arquivo"] == "PG5mZS8+"


def test_xml_ctes_limita_50_chaves():
    with pytest.raises(ValueError):
        bsoft_fiscal.obter_xml_ctes_emitidos(["1" * 44] * 51)
