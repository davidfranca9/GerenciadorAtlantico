"""Recuperar pedido apagado sem querer, relendo o PDF do WhatsApp.

A exclusao apaga a linha direto, sem lixeira - mas o PDF que o cliente
mandou fica guardado na mensagem. O risco aqui nao e deixar de recuperar: e
recriar em dobro o que nunca foi apagado.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.apoio_documentos import banco_em_memoria  # noqa: E402

from app.models import (Agendamento, AgendamentoItem, BaixaPedido, Cidade, Pedido,  # noqa: E402
                        WhatsAppMensagem)
from app.servicos import recuperar_pedidos  # noqa: E402

RECEBIDO_EM = datetime(2026, 9, 18, 14, 30)

PEDIDO_LIDO = {
    "produtos": [
        {"contrato": "042666", "produto": "MAP 11-52-00", "embalagem": "SACARIA", "cidade": "Jaíba-MG",
         "cliente": "AGRODANTAS PRODUTOS AGRICOLAS LTDA", "toneladas": 15},
        {"contrato": "042666", "produto": "KCL 00-00-60", "embalagem": "SACARIA", "cidade": "Jaíba-MG",
         "cliente": "AGRODANTAS PRODUTOS AGRICOLAS LTDA", "toneladas": 10},
    ],
    "cidades_candidatas": [],
}


@pytest.fixture
def db():
    sessao = banco_em_memoria(Pedido, BaixaPedido, Cidade, Agendamento, AgendamentoItem, WhatsAppMensagem)
    sessao.add(WhatsAppMensagem(
        id=1, numero="5538999990000", direcao="entrada", tipo="documento",
        nome_arquivo="pedido 042666.pdf", mime_type="application/pdf", midia=b"%PDF-falso",
        created_at=RECEBIDO_EM,
    ))
    sessao.commit()
    yield sessao
    sessao.close()


@pytest.fixture(autouse=True)
def leitura_simulada(monkeypatch):
    """O PDF guardado e falso: o que interessa aqui e o que vem depois da
    leitura, nao o pdfplumber."""
    monkeypatch.setattr(recuperar_pedidos.ocr, "parse_pdf_fields", lambda caminho, cidades: PEDIDO_LIDO)
    monkeypatch.setattr(recuperar_pedidos.ocr, "candidatas_do_item", lambda resultado, item: "")


def test_previa_mostra_o_que_voltaria_sem_gravar_nada(db):
    resultado = recuperar_pedidos.recuperar(db, aplicar=False)

    assert resultado["aplicado"] is False
    assert resultado["quantidade"] == 2
    assert [r["produto"] for r in resultado["recuperados"]] == ["MAP 11-52-00", "KCL 00-00-60"]
    assert db.query(Pedido).count() == 0


def test_aplicar_recria_os_pedidos_com_a_data_de_quando_chegaram(db):
    recuperar_pedidos.recuperar(db, aplicar=True)

    pedidos = db.query(Pedido).order_by(Pedido.produto).all()
    assert [(p.contrato, p.produto, p.toneladas_total) for p in pedidos] == [
        ("042666", "KCL 00-00-60", 10), ("042666", "MAP 11-52-00", 15),
    ]
    assert pedidos[0].cliente == "AGRODANTAS PRODUTOS AGRICOLAS LTDA"
    assert pedidos[0].cidade == "Jaíba-MG"
    # Volta pro lugar dele na lista, nao como pedido novo de hoje.
    assert pedidos[0].created_at == RECEBIDO_EM


def test_pedido_que_nao_foi_apagado_nao_volta_em_dobro(db):
    db.add(Pedido(contrato="042666", produto="MAP 11-52-00", cliente="AGRODANTAS PRODUTOS AGRICOLAS LTDA",
                  cidade="Jaíba-MG", toneladas_total=15))
    db.commit()

    resultado = recuperar_pedidos.recuperar(db, aplicar=True)

    assert resultado["quantidade"] == 1
    assert resultado["ja_estavam"] == 1
    assert [p.produto for p in db.query(Pedido).order_by(Pedido.produto).all()] == ["KCL 00-00-60", "MAP 11-52-00"]


def test_rodar_duas_vezes_nao_duplica(db):
    recuperar_pedidos.recuperar(db, aplicar=True)
    segunda = recuperar_pedidos.recuperar(db, aplicar=True)

    assert segunda["quantidade"] == 0 and segunda["ja_estavam"] == 2
    assert db.query(Pedido).count() == 2


def test_acento_e_caixa_diferentes_contam_como_o_mesmo_pedido(db):
    db.add(Pedido(contrato="042666", produto="map 11-52-00", cliente="agrodantas produtos agricolas ltda",
                  toneladas_total=15))
    db.commit()

    resultado = recuperar_pedidos.recuperar(db, aplicar=True)

    assert resultado["ja_estavam"] == 1 and resultado["quantidade"] == 1


def test_saldo_usado_volta_pelo_agendamento_em_vez_de_zerado(db):
    """Pedido recriado nasce com a barra zerada; o que ja foi agendado tem
    que voltar a ocupar, senao o saldo mentiria pra cima."""
    db.add(Agendamento(id=10, supplier="AFL", status="Agendado", itens=[
        AgendamentoItem(pedido="042666", produto="MAP 11-52-00",
                        cliente="AGRODANTAS PRODUTOS AGRICOLAS LTDA", toneladas=9),
    ]))
    db.commit()

    recuperar_pedidos.recuperar(db, aplicar=True)

    recriado = db.query(Pedido).filter(Pedido.produto == "MAP 11-52-00").first()
    assert recriado.toneladas_usadas == 9
    # E o item do agendamento volta a apontar pro pedido.
    item = db.query(AgendamentoItem).filter(AgendamentoItem.produto == "MAP 11-52-00").first()
    assert item.pedido_ref_id == recriado.id


def test_pedido_que_nao_veio_do_whatsapp_aparece_na_conferencia(db):
    """Agendamento cita um pedido que o WhatsApp nao tem: ele entrou por
    outro caminho e precisa ser refeito na mao."""
    db.add(Agendamento(id=11, supplier="AFL", status="Agendado", itens=[
        AgendamentoItem(pedido="041595", produto="UREIA", cliente="OUTRO CLIENTE", cidade="Janaúba-MG", toneladas=32),
    ]))
    db.commit()

    resultado = recuperar_pedidos.recuperar(db, aplicar=True)

    faltando = resultado["faltando_fora_do_whatsapp"]
    assert [f["pedido"] for f in faltando] == ["041595"]
    assert faltando[0]["toneladas"] == 32


def test_pdf_ilegivel_nao_derruba_a_recuperacao(db, monkeypatch):
    db.add(WhatsAppMensagem(id=2, numero="553899", direcao="entrada", tipo="documento",
                            nome_arquivo="rasgado.pdf", mime_type="application/pdf", midia=b"nada"))
    db.commit()

    def leitura(caminho, cidades):
        with open(caminho, "rb") as arquivo:
            if arquivo.read() == b"nada":
                raise ValueError("PDF sem texto")
        return PEDIDO_LIDO

    monkeypatch.setattr(recuperar_pedidos.ocr, "parse_pdf_fields", leitura)

    resultado = recuperar_pedidos.recuperar(db, aplicar=True)

    assert resultado["quantidade"] == 2
    assert [i["arquivo"] for i in resultado["ilegiveis"]] == ["rasgado.pdf"]


def test_mensagem_enviada_por_nos_e_arquivo_que_nao_e_pdf_ficam_de_fora(db):
    db.add_all([
        WhatsAppMensagem(id=3, numero="553899", direcao="saida", tipo="documento",
                         mime_type="application/pdf", midia=b"%PDF-falso"),
        WhatsAppMensagem(id=4, numero="553899", direcao="entrada", tipo="imagem",
                         mime_type="image/jpeg", midia=b"jpeg"),
    ])
    db.commit()

    resultado = recuperar_pedidos.recuperar(db, aplicar=False)

    assert resultado["mensagens_lidas"] == 1
