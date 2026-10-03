"""O RNTRC tem que ir no corpo do cadastro de motorista no Bsoft.

Bug real visto na tela "Bsoft TMS": "Cadastrar Tudo na Bsoft" respondia
400 `Atributo obrigatorio [RNTRC] nao especificado no corpo do conteudo`.
O payload tinha a chave RNTRC, mas com string vazia - e o Bsoft trata vazio
como ausente nos campos que exigem valor de verdade (mesmo comportamento ja
conhecido de `carreta_id`). A pessoa fisica entra como transportadora, e no
grupo proprietariosVeiculos quando e dona do caminhao: os dois exigem RNTRC.

Tudo com mock: nenhum teste toca a API do Bsoft nem cadastra de verdade.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.servicos import bsoft_api, bsoft_orquestracao  # noqa: E402

# Mensagem de erro do Bsoft como ela chega de verdade: JSON com os acentos
# escapados, que era o que aparecia cru na tela.
CORPO_400_RNTRC = (
    '{"message":"Atributo obrigat\\u00f3rio [RNTRC] n\\u00e3o especificado no corpo do conte\\u00fado","metadata":[]}'
)


class RespostaFalsa:
    def __init__(self, status_code=200, corpo=None, texto=None):
        self.status_code = status_code
        self._corpo = corpo
        self.text = texto if texto is not None else ("" if corpo is None else "{}")

    def json(self):
        if self._corpo is not None:
            return self._corpo
        import json as _json

        return _json.loads(self.text)  # levanta ValueError quando nao e JSON


@pytest.fixture(autouse=True)
def credenciais():
    with patch.object(settings, "bsoft_api_user", "usuario"), \
         patch.object(settings, "bsoft_api_password", "senha"), \
         patch.object(settings, "bsoft_rntrc_padrao", ""), \
         patch.object(settings, "bsoft_api_base_url", "https://exemplo.bsoft.app/services/index.php"):
        yield


def motorista_base(**extra):
    dados = {
        "nome": "Carlos Alberto Dias",
        "cpf": "82780854715",
        "fone": "(77) 99999-0000",
        "rntrc": "12345678",
        "cnh": {"numero": "123", "categoria": "E"},
    }
    dados.update(extra)
    return dados


def payload_cadastro(**extra):
    """Payload da tela que para no passo do motorista: sem endereco e sem
    veiculo, pra o teste nao precisar de banco nem de lookup de IBGE."""
    base = {
        "motorista": motorista_base(),
        "endereco": {},
        "motorista_e_proprietario": True,
        "proprietario": {},
        "permitir_sem_veiculo": True,
    }
    base.update(extra)
    return base


# --------------------------------------------------------------------------
# O RNTRC vai no corpo
# --------------------------------------------------------------------------


def test_rntrc_vai_no_corpo_do_put_do_motorista():
    """Era o 400: o PUT de atualizacao precisa levar RNTRC com valor."""
    with patch("requests.put", return_value=RespostaFalsa(200, {"codPessoa": "99"})) as put:
        bsoft_api.atualizar_pessoa_fisica_bsoft("82780854715", motorista_base())
    corpo = put.call_args.kwargs["json"]
    assert corpo["RNTRC"] == "12345678"


def test_rntrc_vai_no_corpo_do_post_do_motorista():
    with patch("requests.post", return_value=RespostaFalsa(201, {"codPessoa": "99"})) as post:
        bsoft_api.cadastrar_pessoa_fisica_bsoft(motorista_base())
    assert post.call_args.kwargs["json"]["RNTRC"] == "12345678"


def test_rntrc_vai_so_com_digitos():
    """O OCR e a digitacao trazem pontuacao; o Bsoft quer o numero."""
    with patch("requests.post", return_value=RespostaFalsa(201, {"codPessoa": "99"})) as post:
        bsoft_api.cadastrar_pessoa_fisica_bsoft(motorista_base(rntrc=" 123.456-78 "))
    assert post.call_args.kwargs["json"]["RNTRC"] == "12345678"


def test_rntrc_do_proprietario_pj_tambem_vai_so_com_digitos():
    with patch("requests.post", return_value=RespostaFalsa(201, {"codPessoa": "7"})) as post:
        bsoft_api.cadastrar_pessoa_juridica_bsoft({
            "cnpj": "08187322000101", "razao_social": "JFN TRANSPORTES",
            "tipoTransportadora": "E", "rntrc": "123.456-78",
        })
    assert post.call_args.kwargs["json"]["RNTRC"] == "12345678"


def test_rntrc_da_frota_propria_entra_quando_a_tela_nao_mandou():
    """Caminhao da casa, motorista empregado: o RNTRC vem da variavel de
    ambiente, nao do codigo."""
    with patch.object(settings, "bsoft_rntrc_padrao", "87654321"), \
         patch("requests.post", return_value=RespostaFalsa(201, {"codPessoa": "99"})) as post:
        bsoft_api.cadastrar_pessoa_fisica_bsoft(motorista_base(rntrc=""))
    assert post.call_args.kwargs["json"]["RNTRC"] == "87654321"


# --------------------------------------------------------------------------
# De onde o RNTRC vem
# --------------------------------------------------------------------------


def test_rntrc_do_motorista_manda_sobre_o_do_proprietario():
    resolvido = bsoft_orquestracao.resolver_rntrc_motorista(
        {"rntrc": "11111111"}, {"rntrc": "22222222"}, motorista_e_proprietario=False
    )
    assert resolvido == "11111111"


def test_motorista_empregado_usa_o_rntrc_do_proprietario():
    resolvido = bsoft_orquestracao.resolver_rntrc_motorista(
        {"rntrc": ""}, {"rntrc": "22222222"}, motorista_e_proprietario=False
    )
    assert resolvido == "22222222"


def test_motorista_empregado_sem_pj_cai_na_frota_propria():
    with patch.object(settings, "bsoft_rntrc_padrao", "87654321"):
        resolvido = bsoft_orquestracao.resolver_rntrc_motorista(
            {"rntrc": ""}, {}, motorista_e_proprietario=False
        )
    assert resolvido == "87654321"


def test_dono_do_caminhao_nao_herda_rntrc_de_ninguem():
    """RNTRC de outro no cadastro do dono sairia errado no CT-e."""
    with patch.object(settings, "bsoft_rntrc_padrao", "87654321"):
        resolvido = bsoft_orquestracao.resolver_rntrc_motorista(
            {"rntrc": ""}, {"rntrc": "22222222"}, motorista_e_proprietario=True
        )
    assert resolvido == ""


# --------------------------------------------------------------------------
# Faltando o RNTRC, a mensagem diz o que preencher
# --------------------------------------------------------------------------


def test_sem_rntrc_nao_chama_o_bsoft_e_diz_qual_campo_preencher():
    with patch.object(bsoft_api, "buscar_pessoa_fisica_por_cpf") as busca, \
         patch.object(bsoft_api, "atualizar_pessoa_fisica_bsoft") as atualiza, \
         patch.object(bsoft_api, "cadastrar_pessoa_fisica_bsoft") as cadastra:
        resultado = bsoft_orquestracao.executar_cadastro_completo(
            None, payload_cadastro(motorista=motorista_base(rntrc=""))
        )

    assert resultado["ok"] is False
    assert "RNTRC do Motorista" in resultado["mensagem"]
    assert "proprietário do veículo" in resultado["mensagem"]
    # Nenhuma chamada ao Bsoft: a falta e detectada antes.
    assert busca.call_count == 0 and atualiza.call_count == 0 and cadastra.call_count == 0


def test_motorista_empregado_sem_nenhum_rntrc_explica_as_duas_opcoes():
    with patch.object(bsoft_api, "buscar_pessoa_fisica_por_cpf") as busca:
        resultado = bsoft_orquestracao.executar_cadastro_completo(
            None,
            payload_cadastro(
                motorista=motorista_base(rntrc=""),
                motorista_e_proprietario=False,
                proprietario={"cnpj": "08187322000101", "razao_social": "JFN", "tipo": "ETC", "rntrc": ""},
            ),
        )
    assert resultado["ok"] is False
    assert "RNTRC do Motorista" in resultado["mensagem"]
    assert "RNTRC do Proprietário" in resultado["mensagem"]
    assert busca.call_count == 0


def test_proprietario_pj_sem_rntrc_diz_o_campo_que_falta():
    """Aqui o motorista tem RNTRC proprio, entao o cadastro dele passa - o que
    falta e o RNTRC da empresa dona do caminhao."""
    with patch.object(bsoft_api, "buscar_pessoa_fisica_por_cpf", return_value="99"), \
         patch.object(bsoft_api, "atualizar_pessoa_fisica_bsoft", return_value={"codPessoa": "99"}):
        resultado = bsoft_orquestracao.executar_cadastro_completo(
            None,
            payload_cadastro(
                motorista_e_proprietario=False,
                proprietario={"cnpj": "08187322000101", "razao_social": "JFN", "tipo": "ETC", "rntrc": ""},
            ),
        )
    assert resultado["ok"] is False
    assert "RNTRC do Proprietário" in resultado["mensagem"]


# --------------------------------------------------------------------------
# E se o Bsoft reclamar mesmo assim, a mensagem chega legivel
# --------------------------------------------------------------------------


def test_erro_do_bsoft_nao_mostra_json_escapado():
    with patch("requests.put", return_value=RespostaFalsa(400, texto=CORPO_400_RNTRC)):
        with pytest.raises(bsoft_api.BsoftApiError) as exc:
            bsoft_api.atualizar_pessoa_fisica_bsoft("82780854715", motorista_base(rntrc=""))
    mensagem = str(exc.value)
    assert "\\u00f3" not in mensagem and "metadata" not in mensagem
    assert "Atributo obrigatório [RNTRC] não especificado" in mensagem
    # E diz qual campo da tela preencher, nao so o nome do campo da API.
    assert "RNTRC do Motorista" in mensagem


def test_erro_sem_json_ainda_aparece():
    with patch("requests.put", return_value=RespostaFalsa(500, texto="<html>Erro interno</html>")):
        with pytest.raises(bsoft_api.BsoftApiError) as exc:
            bsoft_api.atualizar_pessoa_fisica_bsoft("82780854715", motorista_base())
    assert "Erro interno" in str(exc.value)
