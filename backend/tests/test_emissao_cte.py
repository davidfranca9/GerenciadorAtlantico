"""O caminho unico de emissao, usado pela tela e pelo rascunho automatico.

Tudo aqui roda sem banco e sem Bsoft: as buscas entram por parametro.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.servicos import cte_montagem, emissao_cte, rascunho_automatico  # noqa: E402
from tests.test_cte_5053 import NFE_158852, TARIFA_5053  # noqa: E402

ENDERECOS = {
    "9": [{"id": "1775", "codIBGE": "2908507", "cidade": "CONCEICAO DO JACUIPE", "cep": "44245000", "logradouro": "BR 324"}],
    "1269": [{"id": "2307", "codIBGE": "3143302", "cidade": "MONTES CLAROS", "cep": "39400000", "logradouro": "FAZENDA"}],
}
PESSOAS = {"08068476000176": {"id": "9", "razaoSocial": "FERTIMAXI"}, "36831417604": {"id": "1269", "nome": "ELTON"}}


def buscar_pessoa(doc):
    return PESSOAS.get("".join(c for c in doc if c.isdigit()))


def listar_enderecos(pessoa_id):
    return ENDERECOS.get(str(pessoa_id), [])


def veiculos_ok(agendamento, escolhas):
    return {"motorista_id": "2282", "veiculo_id": "1644", "carreta_id": "1700", "semireboque_id": None, "quarto_veiculo_id": None}


def seguro_ok():
    return {"seguradora_id": "2096", "apolice_id": "3"}


def espelho():
    return cte_montagem.derivar(NFE_158852, tarifa_por_tonelada=TARIFA_5053, embalagem="BIG BAG")


def montar(**mudancas):
    base = dict(
        escolhas={}, aliquota_icms="12", rascunho=True,
        buscar_pessoa=buscar_pessoa, listar_enderecos=listar_enderecos,
        resolver_veiculos_fn=veiculos_ok, resolver_apolice_fn=seguro_ok,
    )
    base.update(mudancas)
    return emissao_cte.montar(espelho(), None, **base)


# --------------------------------------------------------------------------
# montar: so leitura, com as mesmas conferencias da tela
# --------------------------------------------------------------------------


def test_montar_sem_pendencias_quando_tudo_resolve():
    m = montar()
    assert m["pendencias"] == []
    assert m["corpo"]["rascunho"] == "S"
    assert m["corpo"]["carreta_id"] == "1700"
    assert m["corpo"]["enderecoRemetente_id"] == "1775"
    assert m["cfops_id"] == settings.bsoft_cfops_id_interestadual  # BA -> MG


def test_montar_aponta_carreta_faltando():
    def sem_carreta(agendamento, escolhas):
        return {**veiculos_ok(agendamento, escolhas), "carreta_id": None}
    m = montar(resolver_veiculos_fn=sem_carreta)
    assert any("carreta_id" in p for p in m["pendencias"])


def test_montar_definitivo_quando_pedido():
    assert montar(rascunho=False)["corpo"]["rascunho"] == "N"


def test_falha_de_cadastro_vira_excecao_propria():
    from app.servicos.bsoft_client import BsoftError
    def quebra(doc):
        raise BsoftError("502 no Bsoft")
    with pytest.raises(emissao_cte.FalhaCadastros):
        montar(buscar_pessoa=quebra)


# --------------------------------------------------------------------------
# rascunho ou definitivo, lido do que foi enviado
# --------------------------------------------------------------------------


def operacao(**campos):
    base = dict(id=1, cte_chave="", ultimo_payload=json.dumps({"rascunho": "S"}),
                cod_conhecimento_bsoft="5120", cte_numero="", solicitado_por="automatico", status="CTE_CRIADO")
    base.update(campos)
    return SimpleNamespace(**base)


def test_rascunho_no_bsoft_le_o_payload():
    assert emissao_cte.rascunho_no_bsoft(operacao()) is True
    assert emissao_cte.rascunho_no_bsoft(operacao(ultimo_payload=json.dumps({"rascunho": "N"}))) is False


def test_autorizado_nunca_e_rascunho():
    assert emissao_cte.rascunho_no_bsoft(operacao(cte_chave="2" * 44)) is False


def test_ja_emitido_explica_o_rascunho_automatico():
    erro = emissao_cte.JaEmitido(operacao(), rascunho=True)
    assert "rascunho 5120" in str(erro) and "criado sozinho" in str(erro)


def test_ja_emitido_definitivo_nao_repete():
    erro = emissao_cte.JaEmitido(operacao(cte_numero="5041"), rascunho=False)
    assert "ja gerou o CT-e 5041" in str(erro)


# --------------------------------------------------------------------------
# decidir: quando o automatico NAO tenta
# --------------------------------------------------------------------------


def nota(**campos):
    base = dict(tem_cte=False, agendamento_id=108, rascunho_resultado="", xml="<xml/>", chave="1" * 44)
    base.update(campos)
    return SimpleNamespace(**base)


SUGESTAO = {"tarifa": "300.00", "destino": "Montes Claros", "embalagem": "BIG BAG"}


def test_tenta_quando_tudo_esta_pronto(monkeypatch):
    monkeypatch.setattr(settings, "rascunho_automatico", True)
    assert rascunho_automatico.decidir(nota(), SUGESTAO) == ""


@pytest.mark.parametrize("campos, trecho", [
    ({"tem_cte": True}, "ja tem CT-e"),
    ({"agendamento_id": None}, "sem agendamento"),
    ({"rascunho_resultado": "faltou: x"}, "ja tentou"),
    ({"xml": ""}, "sem XML"),
])
def test_nao_tenta_sem_o_basico(monkeypatch, campos, trecho):
    monkeypatch.setattr(settings, "rascunho_automatico", True)
    assert trecho in rascunho_automatico.decidir(nota(**campos), SUGESTAO)


def test_nao_tenta_sem_tarifa(monkeypatch):
    monkeypatch.setattr(settings, "rascunho_automatico", True)
    motivo = rascunho_automatico.decidir(nota(), {"tarifa": "", "destino": "Encruzilhada"})
    assert "nenhuma cotacao" in motivo and "Encruzilhada" in motivo


def test_nunca_depois_de_erro_do_bsoft(monkeypatch):
    # Pode ter criado do outro lado: a regra da casa e nao repetir.
    monkeypatch.setattr(settings, "rascunho_automatico", True)
    anterior = operacao(cod_conhecimento_bsoft="", erro="502 timeout", status="CTE_REJEITADO")
    assert "ja existe operacao" in rascunho_automatico.decidir(nota(), SUGESTAO, anterior)


def test_desligado_por_configuracao(monkeypatch):
    monkeypatch.setattr(settings, "rascunho_automatico", False)
    assert "desligado" in rascunho_automatico.decidir(nota(), SUGESTAO)
