"""A nota que entra na mao tem que dar o mesmo CT-e da que entra por XML.

O caminho manual existe porque a nota nem sempre chega: tem fabrica que nao
manda o arquivo e tem hora que a SEFAZ ainda nao liberou o documento. Se o
espelho digitado divergir do espelho do XML, o CT-e sai diferente do que sai
hoje - e e exatamente isso que estes testes travam.

O par usado e o mesmo do teste dourado: NF-e 158852 -> CT-e 5053.
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos import cte_montagem, nfe_xml  # noqa: E402
from tests.test_cte_5053 import NFE_158852, TARIFA_5053  # noqa: E402

CHAVE_158852 = "29260908068476000176550010001588521343374682"

# O DANFE na mao: so o que a chave nao carrega.
NOTA_DIGITADA = {
    "chave": CHAVE_158852,
    "emissao": "2026-09-05",
    "destinatario_doc": "368.314.176-04",
    "modalidade_frete": "1",
    "produto": "UREIA PRILL MICROGRANULADA 46% N Emb.: SACO DE 50 KG",
    "peso_kg": "27000",
    "valor_nota": "68850.00",
    "quantidade": "540",
}


def digitada(**mudancas):
    return cte_montagem.derivar_manual(
        {**NOTA_DIGITADA, **mudancas}, tarifa_por_tonelada=TARIFA_5053, embalagem="BIG BAG"
    )


# --------------------------------------------------------------------------
# A chave de acesso preenche metade do formulario sozinha
# --------------------------------------------------------------------------


def test_a_chave_entrega_emitente_serie_e_numero():
    # Posicoes fixas do layout da NF-e, conferidas na nota 158852 real.
    aberta = nfe_xml.dados_da_chave(CHAVE_158852)
    assert aberta["emitente_cnpj"] == "08068476000176"   # FERTIMAXI
    assert aberta["serie"] == "1"
    assert aberta["numero"] == "158852"
    assert aberta["uf"] == "BA"
    assert aberta["ano"] == "2026" and aberta["mes"] == "09"


def test_chave_com_digito_errado_nao_passa():
    # Errar um digito ao copiar do DANFE e o acidente mais provavel aqui.
    trocada = CHAVE_158852[:-1] + ("0" if CHAVE_158852[-1] != "0" else "1")
    with pytest.raises(nfe_xml.NFeInvalida):
        nfe_xml.dados_da_chave(trocada)


def test_chave_curta_nao_passa():
    with pytest.raises(nfe_xml.NFeInvalida):
        nfe_xml.dados_da_chave("2926090806847600017655")


# --------------------------------------------------------------------------
# Digitada ou por XML, o documento tem que sair igual
# --------------------------------------------------------------------------


def test_o_espelho_digitado_bate_com_o_do_xml():
    do_xml = cte_montagem.derivar(
        NFE_158852, tarifa_por_tonelada=TARIFA_5053, embalagem="BIG BAG"
    )
    na_mao = digitada()
    for campo in (
        "chaves_nfe", "numero_nfe", "remetente_doc", "destinatario_doc",
        "destinatario_tipo", "tomador", "tomador_doc", "uf_origem",
        "valor_mercadoria", "quantidade", "especie",
        "tarifa_por_tonelada", "valor_frete", "base_calculo",
    ):
        assert na_mao[campo] == do_xml[campo], campo
    # O peso so difere na forma de escrever: "27000" e "27000.000" sao a
    # mesma carga, e e o numero que vai pro campo quantKg.
    assert Decimal(na_mao["peso_kg"]) == Decimal(do_xml["peso_kg"])


def test_o_peso_digitado_e_em_kg_e_nao_e_convertido():
    # No XML os 27.000 estavam em tonelada e viraram 27000 kg. Digitado, o
    # numero ja e o final: converter de novo daria uma carga mil vezes maior.
    na_mao = digitada()
    assert na_mao["peso_kg"] == "27000"
    assert na_mao["peso_convertido_de_tonelada"] is False


def test_avisa_que_ninguem_conferiu_contra_um_xml():
    assert any("digitada na mao" in aviso.lower() for aviso in digitada()["avisos"])


def test_nota_digitada_nao_tem_pendencia_propria():
    # Com tarifa, embalagem e modalidade informadas, nada mais impede.
    assert digitada()["pendencias"] == []


@pytest.mark.parametrize("faltando", list(cte_montagem.CAMPOS_MANUAIS_OBRIGATORIOS))
def test_recusa_sem_os_campos_que_ninguem_adivinha(faltando):
    campos = {k: v for k, v in NOTA_DIGITADA.items() if k != faltando}
    with pytest.raises(cte_montagem.DadosInsuficientes):
        cte_montagem.derivar_manual(campos, tarifa_por_tonelada=TARIFA_5053, embalagem="BIG BAG")


def test_destinatario_pessoa_fisica_pelo_tamanho_do_documento():
    assert digitada()["destinatario_tipo"] == "fisica"
    assert digitada(destinatario_doc="08.068.476/0001-76")["destinatario_tipo"] == "juridica"


# --------------------------------------------------------------------------
# O municipio do trecho vem do endereco escolhido no Bsoft
# --------------------------------------------------------------------------


def test_percurso_sai_do_endereco_escolhido():
    # Ninguem sabe de cabeca que Conceicao do Jacuipe e 2908507. Quem sabe e
    # o cadastro - e e o mesmo endereco que o CT-e vai usar.
    espelho = digitada()
    assert espelho["ibge_origem"] == ""

    partes = {
        "remetente": {"endereco": {"codIBGE": "2908507", "cidade": "CONCEICAO DO JACUIPE", "uf": "BA"}},
        "destinatario": {"endereco": {"codIBGE": "3143302", "cidade": "MONTES CLAROS", "uf": "MG"}},
    }
    cte_montagem.completar_percurso(espelho, partes)
    assert espelho["ibge_origem"] == "2908507"
    assert espelho["uf_destino"] == "MG"
    assert espelho["municipio_destino"] == "MONTES CLAROS"


def test_percurso_nao_sobrescreve_o_que_veio_da_nota():
    do_xml = cte_montagem.derivar(NFE_158852, tarifa_por_tonelada=TARIFA_5053)
    cte_montagem.completar_percurso(do_xml, {
        "remetente": {"endereco": {"codIBGE": "9999999", "cidade": "OUTRA", "uf": "SP"}},
        "destinatario": {"endereco": {}},
    })
    assert do_xml["ibge_origem"] == "2908507"


def test_uf_sai_do_ibge_quando_o_cadastro_nao_informa():
    # Os dois primeiros digitos do codigo de municipio sao o codigo da UF.
    assert nfe_xml.uf_do_ibge("2908507") == "BA"
    assert nfe_xml.uf_do_ibge("3143302") == "MG"
    assert nfe_xml.uf_do_ibge("") == ""
