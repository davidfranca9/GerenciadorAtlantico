"""Permissao por tela nos outros routers: sem a aba, a API nao atende.

Antes so o financeiro conferia a tela. Nos demais o menu escondia a aba, mas
quem chamasse /pedidos ou /whatsapp direto (pelo endereco, pelo Swagger, por
um script) era atendido normalmente - a permissao era so maquiagem.

O cuidado aqui e o contrario do obvio: uma tela usa varios routers (o
Dashboard le agendamentos, a Ordem de coleta usa documentos e pedidos) e um
router serve varias telas (/bsoft/cidades e o autocomplete de cidade de
Pedidos, Clientes e Analise de fretes). Fechar errado tira do ar quem hoje
trabalha normalmente, e isso e pior que o problema. Entao aqui se confere as
duas pontas: quem nao tem a aba toma 403, e quem tem a aba consegue usar
TODAS as rotas daquela tela, mesmo as que moram em outro router.

Login, troca de senha e o webhook que a Meta chama nao sao tela de ninguem e
seguem abertos - tambem tem teste.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.apoio_documentos import banco_em_memoria, roteador_documentos, usuario_de_teste  # noqa: E402

roteador_documentos()  # substitui o gerador de O.C. em HTML quando o WeasyPrint nao carrega

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import auth as rotas_auth  # noqa: E402
from app.auth import ROTAS_TELAS, exigir_tela, get_current_user, hash_password  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models import (Agendamento, AgendamentoEmail, AgendamentoItem, BaixaPedido, CartaFreteEnviada,  # noqa: E402
                        Cidade, Cliente, CotacaoFrete, ListaEmail, NotaFiscalRecebida, OperacaoFiscal,
                        Pedido, RespostaFabrica, User, WhatsAppContato, WhatsAppMensagem)
from app.routers import agendamentos as rotas_agendamentos  # noqa: E402
from app.routers import bsoft as rotas_bsoft  # noqa: E402
from app.routers import buonny as rotas_buonny  # noqa: E402
from app.routers import clientes as rotas_clientes  # noqa: E402
from app.routers import contrato as rotas_contrato  # noqa: E402
from app.routers import dashboard as rotas_dashboard  # noqa: E402
from app.routers import documentos as rotas_documentos  # noqa: E402
from app.routers import email_inbox as rotas_email  # noqa: E402
from app.routers import financeiro as rotas_financeiro  # noqa: E402
from app.routers import fiscal as rotas_fiscal  # noqa: E402
from app.routers import fretes as rotas_fretes  # noqa: E402
from app.routers import pedidos as rotas_pedidos  # noqa: E402
from app.routers import whatsapp as rotas_whatsapp  # noqa: E402

TABELAS = (Pedido, BaixaPedido, Cidade, Agendamento, AgendamentoItem, AgendamentoEmail, RespostaFabrica,
           ListaEmail, Cliente, CotacaoFrete, CartaFreteEnviada, NotaFiscalRecebida, OperacaoFiscal,
           WhatsAppMensagem, WhatsAppContato, User)

# Os routers fechados neste trabalho, do jeito que o main.py os monta.
ROUTERS = (
    rotas_agendamentos.router, rotas_bsoft.router, rotas_buonny.router, rotas_clientes.router,
    rotas_contrato.router, rotas_dashboard.router, rotas_documentos.router, rotas_email.router,
    rotas_fiscal.router, rotas_fretes.router, rotas_pedidos.router, rotas_whatsapp.router,
)

# Rota que nao e de tela nenhuma: quem chama e a Meta, nao um usuario logado
# (a seguranca dela e a assinatura HMAC do corpo).
ROTAS_PUBLICAS = {("GET", "/whatsapp/webhook"), ("POST", "/whatsapp/webhook")}

# O levantamento que guiou o fechamento: cada aba e TUDO o que ela chama no
# backend (lido em frontend/src/api/client.js e em quem usa cada funcao).
# Se faltar uma linha aqui, a tela correspondente quebra em producao.
ROTAS_DE_CADA_TELA: dict[str, tuple[tuple[str, str], ...]] = {
    # DashboardPage: o resumo da semana e a lista de agendamentos do dia.
    "/dashboard": (("GET", "/dashboard/resumo"), ("GET", "/agendamentos")),
    # PedidosPage: a lista, as acoes do pedido e o autocomplete de cidade.
    "/pedidos": (("GET", "/pedidos"), ("POST", "/pedidos/retirar"), ("PATCH", "/pedidos/cidade"),
                 ("GET", "/bsoft/cidades")),
    # ContratoPage: le o PDF do pedido e gera/envia a autorizacao de coleta.
    "/contrato": (("POST", "/contrato/parse-pdf"), ("POST", "/ordens-coleta/gerar-autorizacao"),
                  ("POST", "/ordens-coleta/enviar-autorizacao-email")),
    # OrdemColetaPage: OCR da CNH e do CRLV + os documentos da carga.
    "/ordem-coleta": (("POST", "/contrato/ocr/cnh"), ("POST", "/contrato/ocr/crlv"),
                      ("POST", "/ordens-coleta/gerar"), ("POST", "/ordens-coleta/enviar-email")),
    # CartaFretePage.
    "/autorizacao-abastecimento": (("GET", "/cartas-frete"), ("POST", "/cartas-frete/gerar"),
                                   ("POST", "/cartas-frete/agendar")),
    # AgendamentosPage (com o painel de e-mail do motorista): agendamento,
    # pedidos pra montar a carga e os documentos gerados dali mesmo.
    "/agendamentos": (("GET", "/agendamentos"), ("POST", "/agendamentos"),
                      ("GET", "/agendamentos/email-motorista/config"), ("GET", "/pedidos"),
                      ("POST", "/ordens-coleta/gerar")),
    # AnaliseFretesPage: cotacoes, clientes e cidades.
    "/analise-fretes": (("GET", "/cotacoes-frete"), ("POST", "/cotacoes-frete"), ("GET", "/clientes"),
                        ("GET", "/bsoft/cidades")),
    # DocumentosFiscaisPage: notas e CT-e, os documentos do Bsoft e o
    # agendamento pra casar com a nota.
    "/documentos-fiscais": (("GET", "/fiscal/notas"), ("GET", "/fiscal/notas/contagem"),
                            ("GET", "/fiscal/conjuntos"), ("GET", "/bsoft/documentos-fiscais"),
                            ("GET", "/agendamentos")),
    # ClientesPage.
    "/clientes": (("GET", "/clientes"), ("POST", "/clientes"), ("GET", "/bsoft/cidades")),
    # EmailsPage e o contador de novos da barra lateral.
    "/emails": (("GET", "/email/mensagens"), ("GET", "/email/novos")),
    # WhatsAppPage.
    "/whatsapp": (("GET", "/whatsapp/conversas"), ("POST", "/whatsapp/enviar")),
    # BsoftPage: cadastro de motorista e veiculo.
    "/bsoft": (("GET", "/bsoft/lookups"), ("GET", "/bsoft/cidades"), ("POST", "/bsoft/cadastrar-completo")),
}


@pytest.fixture
def db():
    sessao = banco_em_memoria(*TABELAS)
    sessao.add_all([
        Pedido(id=1, contrato="040947", cliente="ACACIO TORATTI", produto="UREIA", embalagem="BIG BAG",
               toneladas_total=100, toneladas_usadas=0, supplier="HERINGER", cidade="Uberaba - MG"),
        Cidade(nome="Uberaba", uf="MG", ibge="3170107"),
        Cliente(nome="ACACIO TORATTI", cidade="Uberaba", uf="MG"),
        CotacaoFrete(data_cotacao="2026-09-15", destino="Uberaba - MG", fabrica="Heringer", valor_tonelada=120),
    ])
    sessao.commit()
    yield sessao
    sessao.close()


def http(db, *telas, papel="user"):
    """Todos os routers fechados num app so, com um usuario de mentira."""
    app = FastAPI()
    for router in ROUTERS:
        app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: usuario_de_teste(*telas, papel=papel)
    return TestClient(app)


def todas_as_rotas():
    """(metodo, endereco com o id ja no lugar) de todo router fechado.

    Vem dos proprios routers: rota nova entra no teste sozinha."""
    for router in ROUTERS:
        for rota in router.routes:
            for metodo in sorted(rota.methods - {"HEAD", "OPTIONS"}):
                yield metodo, re.sub(r"\{[^}]+\}", "1", rota.path)


def telas_do_porteiro(rota) -> tuple[str, ...] | None:
    """As telas que a rota exige, lidas da propria dependencia exigir_tela.

    None quer dizer "rota sem porteiro de tela" - e o que o teste procura."""
    for dependencia in getattr(rota, "dependencies", ()):
        funcao = dependencia.dependency
        if getattr(funcao, "__qualname__", "").startswith("exigir_tela"):
            return funcao.__closure__[0].cell_contents
    return None


# --------------------------------------------------------------------------
# Sem a aba, nada passa
# --------------------------------------------------------------------------


def test_usuario_de_outra_area_toma_403_em_todas_as_rotas(db):
    """O caso real: o Gleidson so tem o financeiro.

    Varre TODA rota dos routers fechados - menos o webhook, que nao e tela."""
    cliente = http(db, "/financeiro/caixa", "/financeiro/dividas")
    conferidas = 0
    for metodo, endereco in todas_as_rotas():
        if (metodo, endereco) in ROTAS_PUBLICAS:
            continue
        resposta = cliente.request(metodo, endereco, json={})
        assert resposta.status_code == 403, f"{metodo} {endereco} deixou passar ({resposta.status_code})"
        conferidas += 1
    assert conferidas > 50, "o teste parou de encontrar as rotas dos routers"


def test_aba_de_uma_area_nao_abre_a_de_outra(db):
    """Quem cuida de cliente nao mexe em WhatsApp, nem em nota fiscal."""
    cliente = http(db, "/clientes")
    assert cliente.get("/clientes").status_code == 200
    assert cliente.get("/whatsapp/conversas").status_code == 403
    assert cliente.get("/fiscal/notas").status_code == 403
    assert cliente.get("/email/mensagens").status_code == 403
    assert cliente.get("/dashboard/resumo").status_code == 403
    assert cliente.get("/agendamentos").status_code == 403


# --------------------------------------------------------------------------
# Com a aba, a tela inteira funciona - inclusive o que mora em outro router
# --------------------------------------------------------------------------


@pytest.mark.parametrize("tela", sorted(ROTAS_DE_CADA_TELA))
def test_a_aba_liberada_abre_tudo_o_que_a_tela_chama(db, tela):
    """Uma aba, varios routers: nenhuma rota da tela pode responder 403.

    Nao se confere o 200 aqui porque boa parte dessas rotas fala com o Bsoft,
    com o Gmail ou espera um arquivo - o que importa e que a porta abriu (um
    422 de corpo vazio, por exemplo, ja prova que passou do porteiro)."""
    cliente = http(db, tela)
    for metodo, endereco in ROTAS_DE_CADA_TELA[tela]:
        resposta = cliente.request(metodo, endereco, json={})
        assert resposta.status_code != 403, f"{tela} perdeu {metodo} {endereco}"


def test_dashboard_le_agendamento_de_outro_router(db):
    """Tela com dois routers: o resumo e a lista de agendamentos da semana."""
    cliente = http(db, "/dashboard")
    assert cliente.get("/dashboard/resumo").status_code == 200
    assert cliente.get("/agendamentos").status_code == 200
    # ... e nada alem disso: a aba do Dashboard nao e passe livre.
    assert cliente.get("/pedidos").status_code == 403
    assert cliente.get("/clientes").status_code == 403


def test_agendamentos_le_pedidos_de_outro_router(db):
    cliente = http(db, "/agendamentos")
    assert cliente.get("/agendamentos").status_code == 200
    assert cliente.get("/pedidos").status_code == 200


def test_cidade_do_bsoft_serve_as_telas_que_sugerem_cidade(db):
    """Um router, varias telas: /bsoft/cidades e o autocomplete de cidade."""
    for tela in ("/bsoft", "/pedidos", "/clientes", "/analise-fretes"):
        assert http(db, tela).get("/bsoft/cidades").status_code == 200, tela
    # Quem nao tem nenhuma dessas abas nao le a lista.
    assert http(db, "/whatsapp").get("/bsoft/cidades").status_code == 403


def test_leituras_principais_respondem_200(db):
    """Prova que as rotas acima respondem de verdade, nao so "nao 403"."""
    assert http(db, "/pedidos").get("/pedidos").status_code == 200
    assert http(db, "/clientes").get("/clientes").status_code == 200
    assert http(db, "/analise-fretes").get("/cotacoes-frete").status_code == 200
    assert http(db, "/autorizacao-abastecimento").get("/cartas-frete").status_code == 200
    assert http(db, "/documentos-fiscais").get("/fiscal/notas/contagem").status_code == 200
    assert http(db, "/whatsapp").get("/whatsapp/conversas").status_code == 200
    assert http(db, "/bsoft").get("/bsoft/lookups").status_code == 200


def test_administrador_entra_em_tudo(db):
    """Administrador tem todas as telas, sem precisar de marcacao."""
    cliente = http(db, papel="admin")
    for endereco in ("/pedidos", "/agendamentos", "/clientes", "/dashboard/resumo",
                     "/cotacoes-frete", "/cartas-frete", "/whatsapp/conversas", "/bsoft/lookups"):
        assert cliente.get(endereco).status_code == 200, endereco


# --------------------------------------------------------------------------
# Nenhum router ficou de fora, e nenhuma tela inventada entrou
# --------------------------------------------------------------------------


def test_toda_rota_fechada_pede_tela_que_existe():
    """Porteiro em todas as rotas (menos o webhook) apontando pra tela real.

    Rota nova nasce coberta: se alguem acrescentar uma sem exigir_tela, e aqui
    que a suite reclama, em vez de a rota ficar aberta em producao."""
    for router in ROUTERS:
        for rota in router.routes:
            metodos = sorted(rota.methods - {"HEAD", "OPTIONS"})
            publica = all((m, rota.path) in ROTAS_PUBLICAS for m in metodos)
            telas = telas_do_porteiro(rota)
            if publica:
                assert telas is None, f"{rota.path} e publica e nao pode exigir tela"
                continue
            assert telas, f"{metodos} {rota.path} ficou sem exigir_tela"
            for tela in telas:
                assert tela in ROTAS_TELAS, f"{rota.path} aponta pra tela inexistente {tela}"


def test_o_financeiro_segue_com_o_porteiro_dele():
    """O financeiro usa o porteiro proprio (le a tela pela rota e so deixa
    administrador gravar): este teste existe pra ninguem trocar por engano."""
    porteiro = rotas_financeiro.router.dependencies[0].dependency
    assert porteiro is rotas_financeiro.permissao_financeiro
    assert telas_do_porteiro(rotas_financeiro.router.routes[0]) is None


def test_exigir_tela_aceita_qualquer_uma_das_telas():
    """O porteiro de router com varias telas passa com uma delas, nao todas."""
    checar = exigir_tela("/pedidos", "/agendamentos")
    assert checar(usuario_de_teste("/agendamentos")).role == "user"
    with pytest.raises(Exception):
        checar(usuario_de_teste("/clientes"))


# --------------------------------------------------------------------------
# O que nao e tela de ninguem segue aberto
# --------------------------------------------------------------------------


def cliente_auth(db):
    app = FastAPI()
    app.include_router(rotas_auth.router)
    app.include_router(rotas_whatsapp.router)
    app.dependency_overrides[get_db] = lambda: db
    return app


def test_login_funciona_para_quem_nao_tem_aba_nenhuma(db):
    """Login nao e tela: sem isto, usuario novo nao conseguiria nem entrar."""
    db.add(User(email="gleidson@atlantico.com", name="Gleidson", role="user",
                hashed_password=hash_password("12345678"), paginas_liberadas=""))
    db.commit()
    http_auth = TestClient(cliente_auth(db))
    entrada = http_auth.post("/auth/login", data={"username": "gleidson@atlantico.com", "password": "12345678"})
    assert entrada.status_code == 200 and entrada.json()["access_token"]
    senha_errada = http_auth.post("/auth/login", data={"username": "gleidson@atlantico.com", "password": "errada"})
    assert senha_errada.status_code == 401


def test_trocar_a_propria_senha_nao_pede_aba(db):
    gleidson = User(email="gleidson@atlantico.com", name="Gleidson", role="user",
                    hashed_password=hash_password("12345678"), paginas_liberadas="")
    db.add(gleidson)
    db.commit()
    app = cliente_auth(db)
    app.dependency_overrides[get_current_user] = lambda: gleidson
    resposta = TestClient(app).post("/auth/change-password",
                                    json={"current_password": "12345678", "new_password": "87654321"})
    assert resposta.status_code == 200


def test_webhook_da_meta_segue_sem_login_e_sem_aba(db, monkeypatch):
    """Quem chama o webhook e a Meta: nao tem token, nem aba, nem usuario."""
    monkeypatch.setattr(settings, "whatsapp_verify_token", "segredo-da-meta")
    sem_ninguem_logado = TestClient(cliente_auth(db))
    conferencia = sem_ninguem_logado.get("/whatsapp/webhook", params={
        "hub.mode": "subscribe", "hub.verify_token": "segredo-da-meta", "hub.challenge": "12345",
    })
    assert conferencia.status_code == 200 and conferencia.text == "12345"
    # E a mensagem que chega continua entrando (corpo vazio da 200 "ignorado").
    monkeypatch.setattr(settings, "whatsapp_app_secret", "")
    assert sem_ninguem_logado.post("/whatsapp/webhook", json={"entry": []}).status_code == 200


def test_health_nao_pede_aba():
    """O /health existe pra saber se o servidor esta de pe: nao e tela."""
    from app.main import app as aplicacao

    rota_health = next(r for r in aplicacao.routes if getattr(r, "path", "") == "/health")
    assert telas_do_porteiro(rota_health) is None
    assert TestClient(aplicacao).get("/health").json()["status"] == "ok"
