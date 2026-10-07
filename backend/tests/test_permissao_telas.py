"""Permissao por tela: quem ve cada aba, e quem so olha sem poder gravar.

O caso que puxou isso: dar ao gerente acesso de VISUALIZACAO do financeiro sem
dar a mao de lancar, pagar ou excluir. Entao aqui se confere as duas pontas -
leitura liberada pela aba e gravacao so de administrador - e tambem que a lista
de telas do backend e a do menu continuam sendo a mesma lista.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import (GRUPOS_TELAS, ROTAS_TELAS, TELAS_LIBERAVEIS, exigir_tela, get_current_user,  # noqa: E402
                      migrar_para_lista_de_permissao, require_admin, telas_liberadas, tem_tela)
from app.database import get_db  # noqa: E402
from app.models import (CarregamentoFinanceiro, CartaFreteEnviada, ContaAvulsa, ContaBancaria, Despesa, Divida,  # noqa: E402
                        DividaPagamento, LancamentoCaixa, MetaMensal, PagamentoAgenda, PagamentoComissao,
                        PagamentoFaturaAbastecimento, User)
from app.routers import admin as rotas_admin  # noqa: E402
from app.routers import financeiro as rotas_fin  # noqa: E402
from tests.apoio_documentos import banco_em_memoria  # noqa: E402

TABELAS_FIN = (ContaBancaria, LancamentoCaixa, MetaMensal, CarregamentoFinanceiro, CartaFreteEnviada, Despesa,
               ContaAvulsa, PagamentoAgenda, PagamentoComissao, PagamentoFaturaAbastecimento, Divida, DividaPagamento)
DIA = "2026-09-15"


@pytest.fixture
def db():
    sessao = banco_em_memoria(*TABELAS_FIN)
    yield sessao
    sessao.close()


def cliente_fin(db, *, papel="user", telas=()):
    """Financeiro com um usuario de mentira: papel e abas liberadas na mao."""
    app = FastAPI()
    app.include_router(rotas_fin.router)
    usuario = SimpleNamespace(email="gleidson@atlantico", role=papel, paginas_liberadas=",".join(telas))
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: usuario
    return TestClient(app)


def gravacoes_do_financeiro():
    """Toda rota de gravacao do financeiro (metodo, endereco com id ja no lugar).

    Vem do proprio router pra rota nova entrar no teste sozinha."""
    for rota in rotas_fin.router.routes:
        for metodo in sorted(rota.methods - {"HEAD", "OPTIONS"}):
            if metodo != "GET":
                yield metodo, re.sub(r"\{[^}]+\}", "1", rota.path)


# --------------------------------------------------------------------------
# Financeiro: leitura pela aba, gravacao so de administrador
# --------------------------------------------------------------------------


def test_sem_a_aba_liberada_nao_le_nem_grava(db):
    """Quem nao tem a aba toma 403 tanto no GET quanto no POST."""
    http = cliente_fin(db, telas=("/pedidos", "/whatsapp"))
    assert http.get("/financeiro/caixa", params={"inicio": DIA}).status_code == 403
    assert http.get("/financeiro/contas").status_code == 403
    assert http.get("/financeiro/dividas").status_code == 403
    assert http.post("/financeiro/contas", json={"nome": "X", "saldo_inicial_em": DIA}).status_code == 403
    assert http.post("/financeiro/lancamentos", json={"tipo": "entrada", "data": DIA, "valor": 10, "conta_id": 1}).status_code == 403
    assert db.query(ContaBancaria).count() == 0


def test_com_a_aba_do_caixa_liberada_le_mas_nao_grava(db):
    """Acesso de visualizacao: o GET da aba passa, a gravacao nao."""
    http = cliente_fin(db, telas=("/financeiro/caixa",))
    assert http.get("/financeiro/caixa", params={"inicio": DIA}).status_code == 200
    # O Caixa precisa das contas bancarias pra mostrar saldo.
    assert http.get("/financeiro/contas").status_code == 200
    # ... e nada do que grava, mesmo com a aba liberada.
    assert http.post("/financeiro/contas", json={"nome": "Nubank", "saldo_inicial_em": DIA}).status_code == 403
    assert http.post("/financeiro/lancamentos", json={"tipo": "entrada", "data": DIA, "valor": 10, "conta_id": 1}).status_code == 403
    assert http.delete("/financeiro/lancamentos/1").status_code == 403
    assert db.query(ContaBancaria).count() == 0 and db.query(LancamentoCaixa).count() == 0


def test_nenhuma_gravacao_do_financeiro_escapa(db):
    """Com TODAS as abas do financeiro liberadas, nada que grava passa.

    Varre o router inteiro, entao rota nova de gravacao ja entra protegida."""
    todas = [t["rota"] for g in GRUPOS_TELAS if g["titulo"] == "Financeiro" for t in g["telas"]]
    http = cliente_fin(db, telas=todas)
    conferidas = 0
    for metodo, endereco in gravacoes_do_financeiro():
        resposta = http.request(metodo, endereco, json={})
        assert resposta.status_code == 403, f"{metodo} {endereco} deixou passar ({resposta.status_code})"
        conferidas += 1
    assert conferidas > 20, "o teste parou de encontrar as rotas de gravacao"


def test_a_aba_liberada_nao_abre_as_outras(db):
    """Quem so tem Carregamentos nao ve saldo de banco, divida nem gasto."""
    http = cliente_fin(db, telas=("/financeiro/carregamentos",))
    assert http.get("/financeiro/carregamentos").status_code == 200
    assert http.get("/financeiro/contas").status_code == 403
    assert http.get("/financeiro/dividas").status_code == 403
    assert http.get("/financeiro/despesas", params={"competencia": "2026-09"}).status_code == 403
    assert http.get("/financeiro/caixa", params={"inicio": DIA}).status_code == 403


def test_administrador_le_e_grava_tudo(db):
    http = cliente_fin(db, papel="admin")
    conta = http.post("/financeiro/contas", json={"nome": "Nubank", "saldo_inicial": 1000, "saldo_inicial_em": DIA})
    assert conta.status_code == 200
    assert http.get("/financeiro/contas").status_code == 200
    assert http.get("/financeiro/caixa", params={"inicio": DIA}).status_code == 200
    assert http.get("/financeiro/dividas").status_code == 200
    lancamento = http.post("/financeiro/lancamentos", json={"tipo": "entrada", "data": DIA, "valor": 250,
                                                            "conta_id": conta.json()["id"], "forma": "pix"})
    assert lancamento.status_code == 200
    assert db.query(LancamentoCaixa).count() == 1


def test_todo_get_do_financeiro_tem_aba_conhecida():
    """GET sem aba mapeada ficaria so pra administrador sem ninguem perceber."""
    for rota in rotas_fin.router.routes:
        if "GET" not in rota.methods:
            continue
        assert rota.path in rotas_fin.TELAS_DE_LEITURA, f"{rota.path} nao diz de qual aba e"
        for tela in rotas_fin.TELAS_DE_LEITURA[rota.path]:
            assert tela in ROTAS_TELAS, f"{rota.path} aponta pra tela inexistente {tela}"


# --------------------------------------------------------------------------
# A lista de telas e uma so
# --------------------------------------------------------------------------


def telas_do_menu():
    """Le os grupos e as abas do menu da barra lateral (Layout.jsx)."""
    arquivo = Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "Layout.jsx"
    texto = arquivo.read_text(encoding="utf-8")
    bloco = texto.split("export const NAV_SECTIONS = [", 1)[1].split("\n];", 1)[0]
    grupos: list[tuple[str, list[tuple[str, str]]]] = []
    for achado in re.finditer(r'title: "([^"]+)"|to: "([^"]+)", label: "([^"]+)"', bloco):
        titulo, rota, nome = achado.groups()
        if titulo:
            grupos.append((titulo, []))
        else:
            grupos[-1][1].append((rota, nome))
    return grupos


def test_menu_e_backend_falam_da_mesma_lista_de_telas():
    """Aba nova tem que entrar nos dois lugares - senao a suite reclama aqui."""
    do_backend = [(g["titulo"], [(t["rota"], t["nome"]) for t in g["telas"]]) for g in GRUPOS_TELAS]
    assert telas_do_menu() == do_backend


def test_tela_so_de_administrador_nao_entra_na_marcacao():
    assert "/admin" not in TELAS_LIBERAVEIS and "/configuracoes" not in TELAS_LIBERAVEIS
    # A propria senha e de todo mundo, nao se marca por usuario.
    assert "/trocar-senha" not in TELAS_LIBERAVEIS
    assert tem_tela(SimpleNamespace(role="user", paginas_liberadas=""), "/trocar-senha")
    assert not tem_tela(SimpleNamespace(role="user", paginas_liberadas="/admin"), "/admin")


def test_exigir_tela_protege_rota_de_outra_area():
    """exigir_tela e a dependencia pronta pras outras areas (Pedidos, WhatsApp,
    Clientes...) seguirem o mesmo caminho do financeiro."""
    app = FastAPI()

    @app.get("/pedidos/teste", dependencies=[Depends(exigir_tela("/pedidos"))])
    def _rota():
        return {"ok": True}

    def como(papel, liberadas):
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=papel, paginas_liberadas=liberadas)
        return TestClient(app).get("/pedidos/teste").status_code

    assert como("user", "/pedidos") == 200
    assert como("user", "/whatsapp") == 403
    assert como("admin", "") == 200


def test_administrador_ve_todas_as_telas():
    admin = SimpleNamespace(role="admin", paginas_liberadas="")
    assert telas_liberadas(admin) == set(ROTAS_TELAS)


def test_rota_que_nao_existe_mais_nao_vira_permissao_solta():
    usuario = SimpleNamespace(role="user", paginas_liberadas="/pedidos,/carta-frete,/nada")
    assert telas_liberadas(usuario) == {"/pedidos", "/trocar-senha"}


# --------------------------------------------------------------------------
# Tela de Administracao: marcar as abas de cada usuario
# --------------------------------------------------------------------------


@pytest.fixture
def db_usuarios():
    sessao = banco_em_memoria(User)
    yield sessao
    sessao.close()


def cliente_admin(db):
    app = FastAPI()
    app.include_router(rotas_admin.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(email="dono@atlantico", role="admin")
    return TestClient(app)


def usuario(db, email="gleidson@atlantico", liberadas=""):
    u = User(email=email, name="Gleidson", role="user", hashed_password="x", paginas_liberadas=liberadas)
    db.add(u)
    db.commit()
    return u


def test_marcar_as_abas_do_financeiro_para_um_usuario(db_usuarios):
    http = cliente_admin(db_usuarios)
    gleidson = usuario(db_usuarios, liberadas="/pedidos")
    financeiro = [t["rota"] for g in GRUPOS_TELAS if g["titulo"] == "Financeiro" for t in g["telas"]]
    resposta = http.patch(f"/admin/usuarios/{gleidson.id}", json={"paginas_liberadas": ",".join(["/pedidos"] + financeiro)})
    assert resposta.status_code == 200
    db_usuarios.refresh(gleidson)
    assert "/financeiro/caixa" in gleidson.paginas_liberadas.split(",")
    assert tem_tela(gleidson, "/financeiro/dividas")


def test_tela_inventada_na_marcacao_da_erro(db_usuarios):
    http = cliente_admin(db_usuarios)
    gleidson = usuario(db_usuarios, liberadas="/pedidos")
    resposta = http.patch(f"/admin/usuarios/{gleidson.id}", json={"paginas_liberadas": "/pedidos,/financeiro/tesouro"})
    assert resposta.status_code == 400 and "tesouro" in resposta.json()["detail"]
    db_usuarios.refresh(gleidson)
    assert gleidson.paginas_liberadas == "/pedidos"


def test_a_tela_de_administracao_recebe_os_grupos_do_backend(db_usuarios):
    grupos = cliente_admin(db_usuarios).get("/admin/usuarios/telas").json()["grupos"]
    assert [g["titulo"] for g in grupos] == [g["titulo"] for g in GRUPOS_TELAS]
    financeiro = next(g for g in grupos if g["titulo"] == "Financeiro")
    assert {"rota": "/financeiro/caixa", "nome": "Caixa", "somente_admin": False, "sempre_liberada": False} in financeiro["telas"]


def test_usuario_novo_nasce_sem_nenhuma_aba(db_usuarios):
    http = cliente_admin(db_usuarios)
    criado = http.post("/admin/usuarios", json={"email": "novo@atlantico.com.br", "password": "12345678", "name": "Novo"}).json()
    assert criado["paginas_liberadas"] == ""
    novo = db_usuarios.get(User, criado["id"])
    assert telas_liberadas(novo) == {"/trocar-senha"}


# --------------------------------------------------------------------------
# Migracao: lista negra -> lista de permissao
# --------------------------------------------------------------------------


def nao_migrado(db, email, bloqueadas):
    """Usuario como ele fica no banco de producao logo depois do ALTER TABLE:
    com a lista negra antiga preenchida e a coluna nova em NULL."""
    u = User(email=email, hashed_password="x", role="user", paginas_bloqueadas=bloqueadas)
    db.add(u)
    db.commit()
    db.execute(text("UPDATE users SET paginas_liberadas = NULL WHERE id = :id"), {"id": u.id})
    db.commit()
    db.expire_all()
    return u


def test_migracao_mantem_o_que_cada_um_ja_via(db_usuarios):
    so_operacao = nao_migrado(db_usuarios, "a@x", "/whatsapp,/emails,/clientes,/bsoft")
    tudo = nao_migrado(db_usuarios, "b@x", "")

    assert migrar_para_lista_de_permissao(db_usuarios) == 2

    liberadas_a = telas_liberadas(so_operacao)
    assert "/pedidos" in liberadas_a and "/dashboard" in liberadas_a
    assert "/whatsapp" not in liberadas_a and "/emails" not in liberadas_a
    # O financeiro era so de administrador: ninguem ganha isso na migracao.
    assert not [r for r in liberadas_a if r.startswith("/financeiro/")]
    assert not [r for r in telas_liberadas(tudo) if r.startswith("/financeiro/")]
    assert "/clientes" in telas_liberadas(tudo)


def test_migracao_nao_desfaz_o_que_o_dono_marcou_depois(db_usuarios):
    gleidson = usuario(db_usuarios, liberadas="/financeiro/caixa")
    assert migrar_para_lista_de_permissao(db_usuarios) == 0
    db_usuarios.refresh(gleidson)
    assert gleidson.paginas_liberadas == "/financeiro/caixa"


def test_quem_nao_via_nada_continua_sem_ver_nada(db_usuarios):
    bloqueado = nao_migrado(db_usuarios, "c@x", ",".join(TELAS_LIBERAVEIS))
    migrar_para_lista_de_permissao(db_usuarios)
    assert telas_liberadas(bloqueado) == {"/trocar-senha"}


def test_coluna_nula_vale_a_lista_antiga_se_a_migracao_nao_rodou():
    """A migracao roda no startup dentro de try/except: se falhar calada, ler
    NULL como "nao ve nada" deixaria quem trabalha sem menu nenhum."""
    from types import SimpleNamespace

    from app import auth

    nunca_migrado = SimpleNamespace(role="operador", paginas_liberadas=None, paginas_bloqueadas="/pedidos")
    telas = auth.telas_liberadas(nunca_migrado)

    assert "/pedidos" not in telas
    assert "/agendamentos" in telas
    # Financeiro nunca esteve na lista antiga: ninguem ganha de brinde.
    assert "/financeiro/caixa" not in telas
    # Coluna vazia continua sendo "nenhuma aba" - usuario novo.
    novo = SimpleNamespace(role="operador", paginas_liberadas="", paginas_bloqueadas="")
    assert auth.telas_liberadas(novo) == set(auth.TELAS_SEMPRE_LIBERADAS)


def test_administrador_troca_a_senha_de_quem_esqueceu(db_usuarios):
    """Quem perde a senha nao tem como informar a atual, que e o que a troca
    normal pede - antes so mexendo no banco."""
    from app.auth import verify_password

    http = cliente_admin(db_usuarios)
    alvo = http.post("/admin/usuarios", json={
        "email": "gleidson@atlanticofertlog.com.br", "password": "senhaantiga1", "name": "Gleidson", "role": "user",
    }).json()

    resposta = http.post(f"/admin/usuarios/{alvo['id']}/senha", json={"password": "senhanova123"})

    assert resposta.status_code == 200
    # A senha nova nao volta na resposta.
    assert "senhanova123" not in resposta.text
    usuario = db_usuarios.query(User).filter(User.id == alvo["id"]).first()
    assert verify_password("senhanova123", usuario.hashed_password)
    assert not verify_password("senhaantiga1", usuario.hashed_password)


def test_senha_curta_e_usuario_inexistente_sao_recusados(db_usuarios):
    http = cliente_admin(db_usuarios)
    alvo = http.post("/admin/usuarios", json={
        "email": "curta@atlanticofertlog.com.br", "password": "senhaantiga1", "role": "user",
    }).json()

    assert http.post(f"/admin/usuarios/{alvo['id']}/senha", json={"password": "1234"}).status_code == 400
    assert http.post("/admin/usuarios/9999/senha", json={"password": "senhanova123"}).status_code == 404
