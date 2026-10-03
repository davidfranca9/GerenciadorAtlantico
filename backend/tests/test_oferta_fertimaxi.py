"""O "De acordo" da Fertimaxi lido como pedido.

Quando a Fertimaxi aceita o lance de uma oferta ela manda esse documento, e
nao o contrato de pedido de sempre - e ele chega pelos dois caminhos que ja
existem: a importacao de PDF da tela de Pedidos e o WhatsApp. Os campos aqui
sao os da oferta 493582 real (lance 2174230), com o texto linha por linha como
o pdfplumber le o PDF: inclusive o telefone que sobra pra linha de baixo e o
rodape "1 of 1", que antes colavam no valor do campo anterior.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.servicos import ocr  # noqa: E402
from tests.apoio_documentos import banco_em_memoria, usuario_de_teste  # noqa: E402

CIDADES = [
    ("Monjolos", "MG"), ("Montes Claros", "MG"), ("Águas Vermelhas", "MG"),
    ("Conceição do Jacuípe", "BA"), ("Salvador", "BA"), ("Feira de Santana", "BA"),
]

OFERTA_493582 = [
    "De acordo 493582 - ATLANTICO FERTLOG TRASPORTES",
    "E SERVICOS DE CARGAS LTDA",
    "(oferta id: 493582 - lance id: 2174230)",
    "Estamos confirmando o embarque da carga abaixo com as seguintes condições:",
    "1) Descrição da Oferta: CASA DO PRODUTOR MONJOLOS LTDA",
    "1.1 - Número do Contrato: --",
    "- Obs: 43184",
    "2) Rotas:",
    "2.1 - Conceição do Jacuípe/BA - Monjolos/MG",
    "- Data para Carregamento: 28/09/2026 a --",
    "- Local de Carregamento: Rodovia Salvador/Feira de Santana Br 324, Km 537",
    "- Local de Descarga: RUA NATALINO FRANCISCO 225, CENTRO, CEP 39215000 - (38)",
    "99564768",
    "- Quantidade: 32,00 TON",
    "- Frete Fechado: R$ 350,00/TON",
    "- Produtos: 08.28.16",
    "- Embalagem: SACARIA",
    "- Cadência: --",
    "3) Frete Total Fechado: R$ 350,00/TON. Trate-se de Frete Empresa, portanto, no",
    "valor acertado deve estar incluso os impostos inerentes ao transporte",
    "1 of 1",
]

# Mesma oferta com duas rotas - uma por carregamento, como a Fertimaxi manda
# quando o lance cobre mais de um destino.
OFERTA_DUAS_ROTAS = [
    "De acordo 493999 - ATLANTICO FERTLOG TRASPORTES",
    "(oferta id: 493999 - lance id: 2174999)",
    "1) Descrição da Oferta: CASA DO PRODUTOR MONJOLOS LTDA",
    "1.1 - Número do Contrato: --",
    "- Obs: 43200",
    "2) Rotas:",
    "2.1 - Conceição do Jacuípe/BA - Monjolos/MG",
    "- Data para Carregamento: 28/09/2026 a --",
    "- Quantidade: 32,00 TON",
    "- Produtos: 08.28.16",
    "- Embalagem: SACARIA",
    "- Cadência: --",
    "2.2 - Conceição do Jacuípe/BA - Montes Claros/MG",
    "- Data para Carregamento: 30/09/2026 a --",
    "- Quantidade: 1.080,00 TON",
    "- Produtos: KCL GRANULADO",
    "- Embalagem: BIG BAG",
    "- Cadência: --",
    "3) Frete Total Fechado: R$ 350,00/TON",
    "- Quantidade: 9,00 TON",
    "1 of 1",
]


def _pdf(tmp_path, linhas, nome="oferta.pdf"):
    import fitz

    doc = fitz.open()
    pagina = doc.new_page(width=595, height=842)
    for i, linha in enumerate(linhas):
        pagina.insert_text((40, 60 + i * 14), linha, fontsize=8)
    caminho = tmp_path / nome
    doc.save(str(caminho))
    doc.close()
    return str(caminho)


def _contrato_de_pedido(tmp_path):
    """O PDF de pedido de sempre, o formato que ja era lido antes da oferta."""
    return _pdf(tmp_path, [
        "CLIENTE: WAGMAR JOSE DE OLIVEIRA",
        "End: FAZENDA BOA VISTA, ZONA RURAL, CEP 39560000, Cidade AGUAS VERMELHAS - MG",
        "CNPJ/CPF: 000.000.000-00 / INSCRICAO ESTADUAL:",
        "Nr. Pedido 041555",
        "70010005: SUPER SIMPLES GR 19% P2O5 10% S 16% CA BIG BAG 24,0000 2.000,00 48.000,00",
    ], nome="contrato.pdf")


def test_campos_da_oferta_real(tmp_path):
    resultado = ocr.parse_pdf_fields(_pdf(tmp_path, OFERTA_493582), CIDADES)
    assert resultado["produtos"] == [
        {
            "cliente": "CASA DO PRODUTOR MONJOLOS LTDA",
            # Sem numero de contrato, o pedido e a observacao: 43184 e o
            # numero pelo qual a Fertimaxi acha essa carga.
            "contrato": "43184",
            "produto": "08.28.16",
            "toneladas": 32.0,
            "embalagem": "SACARIA",
            "cidade": "Monjolos-MG",
            "supplier": "AFL",
            "cidades_candidatas": [{"cidade": "Monjolos", "uf": "MG"}],
        }
    ]


def test_oferta_e_reconhecida_sozinha(tmp_path):
    import pdfplumber

    for caminho, esperado in [(_pdf(tmp_path, OFERTA_493582), True), (_contrato_de_pedido(tmp_path), False)]:
        with pdfplumber.open(caminho) as pdf:
            texto = "\n".join((p.extract_text() or "") for p in pdf.pages)
        assert ocr.eh_oferta_fertimaxi(texto) is esperado


def test_cidade_da_rota_e_o_destino_nao_a_fabrica(tmp_path):
    # A rota comeca em Conceicao do Jacuipe (a fabrica) e o pedido tem que
    # sair pro destino, no formato "Nome-UF" do cadastro.
    resultado = ocr.parse_pdf_fields(_pdf(tmp_path, OFERTA_493582), CIDADES)
    assert resultado["produtos"][0]["cidade"] == "Monjolos-MG"
    assert resultado["cidades_candidatas"] == [{"cidade": "Monjolos", "uf": "MG"}]


def test_duas_rotas_viram_dois_produtos(tmp_path):
    resultado = ocr.parse_pdf_fields(_pdf(tmp_path, OFERTA_DUAS_ROTAS), CIDADES)
    produtos = resultado["produtos"]
    assert len(produtos) == 2
    assert [(p["cidade"], p["produto"], p["toneladas"], p["embalagem"]) for p in produtos] == [
        ("Monjolos-MG", "08.28.16", 32.0, "SACARIA"),
        ("Montes Claros-MG", "KCL GRANULADO", 1080.0, "BIG BAG"),
    ]
    # Mesmo cliente e mesmo numero: as duas rotas sao do mesmo pedido.
    assert {p["cliente"] for p in produtos} == {"CASA DO PRODUTOR MONJOLOS LTDA"}
    assert {p["contrato"] for p in produtos} == {"43200"}
    # A quantidade solta depois da secao 3 nao e de rota nenhuma.
    assert 9.0 not in [p["toneladas"] for p in produtos]


def test_cada_rota_leva_a_sua_cidade_possivel(tmp_path):
    # Destino fora do cadastro fica sem cidade - e sem herdar a cidade da
    # outra rota, senao o pedido sairia pro lugar errado calado.
    linhas = [l.replace("Montes Claros/MG", "Taiobeiras/MG") for l in OFERTA_DUAS_ROTAS]
    produtos = ocr.parse_pdf_fields(_pdf(tmp_path, linhas), CIDADES)["produtos"]
    assert [p["cidade"] for p in produtos] == ["Monjolos-MG", ""]
    assert json.loads(ocr.candidatas_do_item({}, produtos[0])) == ["Monjolos-MG"]
    assert json.loads(ocr.candidatas_do_item({}, produtos[1])) == []


def test_numero_do_contrato_vence_a_observacao(tmp_path):
    linhas = [l.replace("Número do Contrato: --", "Número do Contrato: 7788") for l in OFERTA_493582]
    assert ocr.parse_pdf_fields(_pdf(tmp_path, linhas), CIDADES)["produtos"][0]["contrato"] == "7788"


def test_contrato_de_pedido_continua_lido_como_antes(tmp_path):
    resultado = ocr.parse_pdf_fields(_contrato_de_pedido(tmp_path), CIDADES)
    assert resultado["produtos"] == [
        {
            "cliente": "WAGMAR JOSE DE OLIVEIRA",
            "contrato": "041555",
            "produto": "SUPER SIMPLES GR 19% P2O5 10% S 16% CA",
            "toneladas": 24.0,
            "embalagem": "BIG BAG",
            "cidade": "Águas Vermelhas-MG",
        }
    ]
    assert resultado["cidades_candidatas"] == [{"cidade": "Águas Vermelhas", "uf": "MG"}]
    # Sem lista propria no item, o que vale pro pedido e a do documento.
    assert json.loads(ocr.candidatas_do_item(resultado, resultado["produtos"][0])) == ["Águas Vermelhas-MG"]


@pytest.fixture
def db():
    from app.models import Agendamento, AgendamentoItem, BaixaPedido, Cidade, Pedido, WhatsAppMensagem

    sessao = banco_em_memoria(Pedido, BaixaPedido, Cidade, Agendamento, AgendamentoItem, WhatsAppMensagem)
    sessao.add_all([
        Cidade(nome="Monjolos", uf="MG", ibge="3143104"),
        Cidade(nome="Conceição do Jacuípe", uf="BA", ibge="2908408"),
    ])
    sessao.commit()
    yield sessao
    sessao.close()


def test_importacao_pela_tela_cria_o_pedido_da_fertimaxi(tmp_path, db):
    from app.auth import get_current_user
    from app.database import get_db
    from app.models import Pedido
    from app.routers import pedidos

    app = FastAPI()
    app.include_router(pedidos.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: usuario_de_teste("/pedidos")
    cliente = TestClient(app)

    with open(_pdf(tmp_path, OFERTA_493582), "rb") as arquivo:
        # Botao da tela na outra fabrica: a oferta e da Fertimaxi de qualquer
        # jeito, e o documento e que diz isso.
        resposta = cliente.post(
            "/pedidos/importar-pdf",
            params={"supplier": "HERINGER"},
            files={"file": ("oferta_493582.pdf", arquivo, "application/pdf")},
        )
    assert resposta.status_code == 200, resposta.text
    assert len(resposta.json()["pedidos"]) == 1

    pedido = db.query(Pedido).one()
    assert (pedido.contrato, pedido.cliente, pedido.cidade) == ("43184", "CASA DO PRODUTOR MONJOLOS LTDA", "Monjolos-MG")
    assert (pedido.produto, pedido.embalagem, pedido.toneladas_total) == ("08.28.16", "SACARIA", 32.0)
    assert pedido.supplier == "AFL"


def test_oferta_recebida_pelo_whatsapp_cria_o_pedido(tmp_path, db, monkeypatch):
    from app.models import Pedido, WhatsAppMensagem
    from app.routers import whatsapp as rota_whatsapp
    from app.servicos import whatsapp as servico_whatsapp

    mensagem = WhatsAppMensagem(numero="5575999990000", direcao="entrada", tipo="documento")
    db.add(mensagem)
    db.commit()

    conteudo = open(_pdf(tmp_path, OFERTA_493582), "rb").read()
    enviadas: list[str] = []
    monkeypatch.setattr(rota_whatsapp, "SessionLocal", lambda: db)
    monkeypatch.setattr(servico_whatsapp, "obter_url_midia", lambda media_id: "https://midia/teste")
    monkeypatch.setattr(servico_whatsapp, "baixar_midia", lambda url: conteudo)
    monkeypatch.setattr(servico_whatsapp, "enviar_mensagem_texto", lambda numero, texto: enviadas.append(texto))
    # Padrao do WhatsApp na outra fabrica: a oferta diz de quem ela e.
    monkeypatch.setattr(rota_whatsapp.settings, "whatsapp_supplier_padrao", "HERINGER")

    rota_whatsapp._processar_arquivo_recebido("5575999990000", mensagem.id, "media-1", "application/pdf")

    pedido = db.query(Pedido).one()
    assert (pedido.contrato, pedido.cidade, pedido.toneladas_total) == ("43184", "Monjolos-MG", 32.0)
    assert pedido.supplier == "AFL"
    assert enviadas and "1 produto(s) de 1 pedido(s)" in enviadas[0]
