"""Resolucao de remetente e destinatario no cadastro do Bsoft.

O CT-e referencia as partes por id, e uma pessoa pode ter varios enderecos.
A escolha e pelo codigo IBGE do municipio da NF-e, que e exato.

Nenhum teste toca a rede: as buscas entram por parametro.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos.cte_montagem import resolver_parte, resolver_partes  # noqa: E402

FERTIMAXI = {"id": "101", "razaoSocial": "FERTIMAXI"}
ELTON = {"id": "202", "nome": "ELTON CALDEIRA DA SILVA"}

# Conceicao do Jacuipe/BA e Montes Claros/MG, os municipios do CT-e 5053.
END_JACUIPE = {"id": "9001", "codIBGE": "2908507", "cidade": "CONCEICAO DO JACUIPE"}
END_MONTES = {"id": "9002", "codIBGE": "3143302", "cidade": "MONTES CLAROS"}
END_SALVADOR = {"id": "9003", "codIBGE": "2927408", "cidade": "SALVADOR"}


def busca_fixa(pessoa):
    return lambda documento: pessoa


def enderecos_fixos(*enderecos):
    return lambda pessoa_id: list(enderecos)


def test_resolve_pessoa_e_endereco_pelo_ibge():
    resultado = resolver_parte(
        "08068476000176", "2908507",
        buscar_pessoa=busca_fixa(FERTIMAXI),
        listar_enderecos=enderecos_fixos(END_SALVADOR, END_JACUIPE),
    )
    assert resultado["pessoa_id"] == "101"
    assert resultado["endereco_id"] == "9001"  # o de Conceicao do Jacuipe
    assert resultado["aviso"] == ""


def test_pessoa_fisica_resolve_igual():
    resultado = resolver_parte(
        "36831417604", "3143302",
        buscar_pessoa=busca_fixa(ELTON),
        listar_enderecos=enderecos_fixos(END_MONTES),
    )
    assert resultado["pessoa_id"] == "202"
    assert resultado["nome"] == "ELTON CALDEIRA DA SILVA"


def test_pessoa_nao_cadastrada_vira_aviso():
    resultado = resolver_parte(
        "36831417604", "3143302",
        buscar_pessoa=lambda doc: None,
        listar_enderecos=enderecos_fixos(),
    )
    assert resultado["pessoa_id"] is None
    assert "nao esta cadastrado" in resultado["aviso"]


def test_nenhum_endereco_no_municipio_da_nota_nao_escolhe_outro():
    # O erro grave seria pegar o endereco errado em silencio.
    resultado = resolver_parte(
        "08068476000176", "2908507",
        buscar_pessoa=busca_fixa(FERTIMAXI),
        listar_enderecos=enderecos_fixos(END_SALVADOR),
    )
    assert resultado["endereco_id"] is None
    assert "Nenhum endereco cadastrado no municipio" in resultado["aviso"]
    assert "SALVADOR" in resultado["aviso"]


def test_empate_no_municipio_usa_o_preferencial():
    outro = {"id": "9004", "codIBGE": "2908507", "cidade": "CONCEICAO DO JACUIPE"}
    preferencial = dict(END_JACUIPE, enderecoPreferencial="S")
    resultado = resolver_parte(
        "08068476000176", "2908507",
        buscar_pessoa=busca_fixa(FERTIMAXI),
        listar_enderecos=enderecos_fixos(outro, preferencial),
    )
    assert resultado["endereco_id"] == "9001"
    assert resultado["aviso"] == ""


def test_empate_sem_preferencial_pede_escolha_e_lista_as_opcoes():
    outro = {"id": "9004", "codIBGE": "2908507", "cidade": "CONCEICAO DO JACUIPE"}
    resultado = resolver_parte(
        "08068476000176", "2908507",
        buscar_pessoa=busca_fixa(FERTIMAXI),
        listar_enderecos=enderecos_fixos(END_JACUIPE, outro),
    )
    assert resultado["endereco_id"] is None
    assert "escolha qual" in resultado["aviso"]
    assert {e["id"] for e in resultado["enderecos"]} == {"9001", "9004"}


def test_cep_da_nota_desempata_enderecos_do_mesmo_municipio():
    # Os dois ficam no municipio da nota; so o CEP separa.
    certo = dict(END_JACUIPE, cep="44245-000")
    outro = {"id": "9004", "codIBGE": "2908507", "cep": "44245999"}
    resultado = resolver_parte(
        "08068476000176", "2908507",
        buscar_pessoa=busca_fixa(FERTIMAXI),
        listar_enderecos=enderecos_fixos(outro, certo),
        cep="44245000",
    )
    assert resultado["endereco_id"] == "9001"
    assert resultado["aviso"] == ""


def test_escolha_manual_vence_a_automatica():
    outro = {"id": "9004", "codIBGE": "2908507"}
    resultado = resolver_parte(
        "08068476000176", "2908507",
        buscar_pessoa=busca_fixa(FERTIMAXI),
        listar_enderecos=enderecos_fixos(END_JACUIPE, outro),
        endereco_id="9004",
    )
    assert resultado["endereco_id"] == "9004"
    assert resultado["aviso"] == ""


def test_pessoa_sem_endereco_avisa():
    resultado = resolver_parte(
        "08068476000176", "2908507",
        buscar_pessoa=busca_fixa(FERTIMAXI),
        listar_enderecos=enderecos_fixos(),
    )
    assert "sem endereco cadastrado" in resultado["aviso"]


def test_resolve_as_duas_partes_do_5053():
    espelho = {
        "remetente_doc": "08068476000176",
        "ibge_origem": "2908507",
        "destinatario_doc": "36831417604",
        "ibge_destino": "3143302",
    }
    pessoas = {"08068476000176": FERTIMAXI, "36831417604": ELTON}
    enderecos = {"101": [END_JACUIPE], "202": [END_MONTES]}
    resultado = resolver_partes(
        espelho,
        buscar_pessoa=lambda doc: pessoas.get(doc),
        listar_enderecos=lambda pessoa_id: enderecos.get(pessoa_id, []),
    )
    assert resultado["completo"] is True
    assert resultado["pendencias"] == []
    assert resultado["remetente"]["endereco_id"] == "9001"
    assert resultado["destinatario"]["endereco_id"] == "9002"


def test_uma_parte_faltando_deixa_incompleto():
    espelho = {
        "remetente_doc": "08068476000176",
        "ibge_origem": "2908507",
        "destinatario_doc": "36831417604",
        "ibge_destino": "3143302",
    }
    resultado = resolver_partes(
        espelho,
        buscar_pessoa=lambda doc: FERTIMAXI if doc.startswith("08") else None,
        listar_enderecos=lambda pessoa_id: [END_JACUIPE],
    )
    assert resultado["completo"] is False
    assert any(p.startswith("Destinatario:") for p in resultado["pendencias"])


def test_enderecos_identicos_nao_travam_a_emissao():
    """Duplicata de cadastro nao e ambiguidade.

    O cadastro da Fertimaxi tem quatro enderecos iguais no mesmo municipio,
    com a mesma rua e o mesmo CEP. Escolher entre iguais nao muda o
    documento, entao pedir escolha ali so travava a emissao a toa.
    """
    a = {"id": "1775", "codIBGE": "2908507", "logradouro": "BR 324", "numero": "KM 537", "cep": "44245000"}
    b = {"id": "1422", "codIBGE": "2908507", "logradouro": "BR 324", "numero": "KM 537", "cep": "44245000"}
    resultado = resolver_parte(
        "08068476000176", "2908507",
        buscar_pessoa=busca_fixa(FERTIMAXI),
        listar_enderecos=enderecos_fixos(a, b),
    )
    assert resultado["endereco_id"] == "1775"
    assert resultado["aviso"] == ""


def test_enderecos_diferentes_continuam_pedindo_escolha():
    # Aqui a escolha muda o documento, entao continua bloqueando.
    a = {"id": "1", "codIBGE": "2908507", "logradouro": "BR 324", "cep": "44245000"}
    b = {"id": "2", "codIBGE": "2908507", "logradouro": "RUA OUTRA", "cep": "44245000"}
    resultado = resolver_parte(
        "08068476000176", "2908507",
        buscar_pessoa=busca_fixa(FERTIMAXI),
        listar_enderecos=enderecos_fixos(a, b),
    )
    assert resultado["endereco_id"] is None
    assert "escolha qual" in resultado["aviso"]


def test_endereco_de_outra_pessoa_e_recusado():
    """Escolha manual so vale entre os enderecos da propria pessoa.

    Sem essa checagem, um id de outra empresa passava direto: foi assim que
    o rascunho 5072 saiu com o endereco da Fertimaxi numa nota de outro
    emitente - remetente de um, endereco de outro.
    """
    resultado = resolver_parte(
        "08068476000176", "2908507",
        buscar_pessoa=busca_fixa(FERTIMAXI),
        listar_enderecos=enderecos_fixos(END_JACUIPE),
        endereco_id="99999",
    )
    assert resultado["endereco_id"] is None
    assert "nao pertence a este cadastro" in resultado["aviso"]


def test_endereco_da_propria_pessoa_continua_valendo():
    outro = {"id": "9004", "codIBGE": "2908507", "logradouro": "OUTRA RUA"}
    resultado = resolver_parte(
        "08068476000176", "2908507",
        buscar_pessoa=busca_fixa(FERTIMAXI),
        listar_enderecos=enderecos_fixos(END_JACUIPE, outro),
        endereco_id="9004",
    )
    assert resultado["endereco_id"] == "9004"
    assert resultado["aviso"] == ""
