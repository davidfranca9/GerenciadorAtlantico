"""A Autorizacao de Carregamento sai no modelo que a Fertimaxi mandou.

O modelo e um cartao vertical - rotulo em B, valor em C - e o arquivo traz
dois blocos de exemplo. O caminhao inteiro sai num bloco so: cada campo
junta os pedidos com " / ", sempre na mesma ordem. Os testes travam que o
primeiro bloco do modelo e copiado fielmente (rotulos, bordas, cores,
mesclagens), que nada do segundo bloco de exemplo sobra e que a ordem dos
campos se corresponde.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos.documentos import gerar_autorizacao_xlsx  # noqa: E402

MODELO = Path(__file__).resolve().parents[1] / "dados" / "Autorizacao de Carregamento FERTIMAXI.xlsx"

ROTULOS = ["Cliente:", "Pedido:", "Quantidade:", "Produto:", "Embalagem:", "Transportador:",
           "Motorista:", "CPF:", "Modelo Veiculo:", "Placa:", "Telefone:"]

PEDIDO_WAGMAR = {
    "cliente": "WAGMAR JOSE DE OLIVEIRA", "contrato": "41556", "toneladas": "32",
    "produto": "UREIA PRILL MICROGRANULADA 46% N", "embalagem": "SACARIA", "cidade": "Montes Claros",
}


def gerar(tmp_path, produtos, **motorista):
    destino = tmp_path / "autorizacao.xlsx"
    base = dict(motorista="TALISSON JUNIOR GUIMARAES RIBEIRO", cpf="12159781622",
                telefone="(38) 99999-0000", placas=("PFJ2I64", "nzb4h89", ""), modelo_veiculo="SIDER")
    base.update(motorista)
    gerar_autorizacao_xlsx(str(MODELO), str(destino), produtos, **base)
    return load_workbook(destino).active


def valores(ws, topo):
    """{rotulo: valor} de um bloco que comeca na linha `topo`."""
    return {ws[f"B{topo + 3 + i}"].value: ws[f"C{topo + 3 + i}"].value for i in range(len(ROTULOS))}


def test_um_pedido_preenche_o_bloco_do_modelo(tmp_path):
    ws = gerar(tmp_path, [PEDIDO_WAGMAR])
    assert ws["B2"].value == "FERTIMAXI"
    assert ws["B3"].value == "Autorização De Carregamento"
    assert valores(ws, 2) == {
        "Cliente:": "WAGMAR JOSE DE OLIVEIRA",
        "Pedido:": 41556,
        "Quantidade:": "32 t",
        "Produto:": "UREIA PRILL MICROGRANULADA 46% N",
        "Embalagem:": "SACARIA",
        "Transportador:": "ATLÂNTICO FERTLOG",
        "Motorista:": "TALISSON JUNIOR GUIMARAES RIBEIRO",
        "CPF:": "121.597.816-22",
        "Modelo Veiculo:": "SIDER",
        "Placa:": "PFJ-2I64 / NZB-4H89",
        "Telefone:": "(38) 99999-0000",
    }


def test_um_pedido_nao_deixa_sobra_do_segundo_bloco_de_exemplo(tmp_path):
    ws = gerar(tmp_path, [PEDIDO_WAGMAR])
    assert all(ws[f"{c}{r}"].value is None for r in range(16, 31) for c in "BC")
    assert sorted(str(m) for m in ws.merged_cells.ranges) == ["B2:C2", "B3:C3"]
    assert ws.print_area == "'Planilha1'!$B$2:$C$15"


def test_varios_pedidos_cabem_num_bloco_so(tmp_path):
    """O caminhao com dois clientes, como a fabrica le: cada campo na mesma
    ordem, e o pedido com mais de um produto entre parenteses."""
    ws = gerar(tmp_path, [
        {"cliente": "CLIENTE 1", "contrato": "40000", "produto": "PRODUTO 1", "toneladas": "1", "embalagem": "SACO"},
        {"cliente": "CLIENTE 1", "contrato": "40000", "produto": "PRODUTO 1-2", "toneladas": "1", "embalagem": "SACO"},
        {"cliente": "CLIENTE 2", "contrato": "40001", "produto": "PRODUTO 2", "toneladas": "2", "embalagem": "BIGBAG"},
        {"cliente": "CLIENTE 2", "contrato": "40001", "produto": "PRODUTO 2-2", "toneladas": "2", "embalagem": "BIGBAG"},
    ])
    campos = valores(ws, 2)
    assert campos["Cliente:"] == "CLIENTE 1 / CLIENTE 2"
    assert campos["Pedido:"] == "40000 / 40001"
    assert campos["Quantidade:"] == "(1 t / 1 t) / (2 t / 2 t)"
    assert campos["Produto:"] == "(PRODUTO 1 / PRODUTO 1-2) / (PRODUTO 2 / PRODUTO 2-2)"
    assert campos["Embalagem:"] == "SACO / BIGBAG"
    # Um bloco so: nada do segundo bloco de exemplo sobra.
    assert all(ws[f"{c}{r}"].value is None for r in range(16, 31) for c in "BC")
    assert ws.print_area == "'Planilha1'!$B$2:$C$15"


def test_um_pedido_com_dois_produtos_nao_leva_parenteses(tmp_path):
    """Com um pedido so nao ha o que separar: parenteses so atrapalhariam."""
    ws = gerar(tmp_path, [
        dict(PEDIDO_WAGMAR, produto="UREIA", toneladas="20"),
        dict(PEDIDO_WAGMAR, produto="KCL", toneladas="12", embalagem="BIG BAG"),
    ])
    campos = valores(ws, 2)
    assert campos["Cliente:"] == "WAGMAR JOSE DE OLIVEIRA"
    assert campos["Pedido:"] == 41556
    assert campos["Produto:"] == "UREIA / KCL"
    assert campos["Quantidade:"] == "20 t / 12 t"
    assert campos["Embalagem:"] == "SACARIA / BIG BAG"


def test_mesmo_cliente_em_dois_pedidos_aparece_nas_duas_posicoes(tmp_path):
    """A fabrica le pela posicao: tirar o nome repetido desalinharia tudo."""
    ws = gerar(tmp_path, [
        dict(PEDIDO_WAGMAR, contrato="41556", produto="UREIA"),
        dict(PEDIDO_WAGMAR, contrato="40778", produto="KCL", embalagem="BIG BAG"),
    ])
    campos = valores(ws, 2)
    assert campos["Cliente:"] == "WAGMAR JOSE DE OLIVEIRA / WAGMAR JOSE DE OLIVEIRA"
    assert campos["Pedido:"] == "41556 / 40778"
    assert campos["Produto:"] == "UREIA / KCL"
    assert campos["Embalagem:"] == "SACARIA / BIG BAG"


def test_o_estilo_do_modelo_e_copiado_pro_bloco(tmp_path):
    ws = gerar(tmp_path, [PEDIDO_WAGMAR] * 3)
    modelo = load_workbook(MODELO).active
    for linha in (3, 5, 15):
        for col in "BC":
            original, copia = modelo[f"{col}{linha}"], ws[f"{col}{linha}"]
            assert copia.font.b == original.font.b and copia.font.sz == original.font.sz
            assert copia.border.left.style == original.border.left.style
            assert copia.border.bottom.style == original.border.bottom.style
            assert copia.fill.fgColor.rgb == original.fill.fgColor.rgb
        assert ws.row_dimensions[linha].height == modelo.row_dimensions[linha].height


def test_caminhao_cheio_nao_quebra_pagina(tmp_path):
    """Cinco pedidos continuam num bloco so, numa pagina so."""
    ws = gerar(tmp_path, [dict(PEDIDO_WAGMAR, contrato=f"4100{i}") for i in range(5)])
    assert [b.id for b in ws.row_breaks.brk] == []
    assert ws.print_area == "'Planilha1'!$B$2:$C$15"


def test_sem_pedido_ainda_sai_um_bloco_com_o_motorista(tmp_path):
    ws = gerar(tmp_path, [])
    assert valores(ws, 2)["Motorista:"] == "TALISSON JUNIOR GUIMARAES RIBEIRO"
    assert valores(ws, 2)["Cliente:"] in (None, "")


@pytest.mark.parametrize("escolhido, impresso", [
    ("GRANELEIRO", "GRANELEIRO"),
    ("grade baixa", "GRADE BAIXA"),
    ("SIDER", "SIDER"),
])
def test_modelo_do_veiculo_e_o_escolhido_na_ordem_de_coleta(tmp_path, escolhido, impresso):
    assert valores(gerar(tmp_path, [PEDIDO_WAGMAR], modelo_veiculo=escolhido), 2)["Modelo Veiculo:"] == impresso


def test_sem_modelo_escolhido_fica_em_branco_mesmo_com_placas(tmp_path):
    # Nao deduz pelas placas: cavalo + carreta pode ser qualquer carroceria.
    ws = gerar(tmp_path, [PEDIDO_WAGMAR], modelo_veiculo="", placas=("PFJ2I64", "NZB4H89", ""))
    assert (valores(ws, 2)["Modelo Veiculo:"] or "") == ""


def test_cpf_e_placa_sem_mascara_valida_saem_como_vieram(tmp_path):
    ws = gerar(tmp_path, [PEDIDO_WAGMAR], cpf="123", placas=("TESTE", "", ""))
    assert valores(ws, 2)["CPF:"] == "123"
    assert valores(ws, 2)["Placa:"] == "TESTE"
