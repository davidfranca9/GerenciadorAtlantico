"""Monta o roteador de documentos pra teste, sem banco real e sem login.

O roteador importa o gerador de O.C. em HTML, que depende do WeasyPrint -
e o WeasyPrint nao carrega no Windows sem as bibliotecas do GTK. Quando o
import real falha, entra um substituto: nenhum teste daqui gera O.C.
"""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def usuario_de_teste(*telas: str, email: str = "operador@atlantico.com", papel: str = "user"):
    """Usuario de mentira com as abas que a tela do teste usa.

    Os routers agora exigem a tela (app/auth.py, exigir_tela): chamar a rota
    sem a aba liberada da 403, igual ao usuario de verdade. Por isso cada teste
    diz de qual tela ele esta falando - e, se o mapa de telas de um router
    estiver errado, e aqui que a suite reclama."""
    return SimpleNamespace(email=email, role=papel, paginas_liberadas=",".join(telas))


def roteador_documentos():
    try:
        import app.servicos.oc_html  # noqa: F401
    except (OSError, ImportError):
        falso = types.ModuleType("app.servicos.oc_html")
        falso.gerar_oc_pdf_html = lambda *args, **kwargs: None
        sys.modules["app.servicos.oc_html"] = falso
    from app.routers import documentos
    return documentos


def banco_em_memoria(*modelos):
    """Sessao SQLite com so as tabelas pedidas."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for modelo in modelos:
        modelo.__table__.create(engine)
    return sessionmaker(bind=engine, autoflush=False)()


def cliente_http(db):
    from app.auth import get_current_user
    from app.database import get_db

    documentos = roteador_documentos()
    app = FastAPI()
    app.include_router(documentos.router)
    app.dependency_overrides[get_db] = lambda: db
    # O router de documentos serve as abas que geram O.C. e autorizacao.
    app.dependency_overrides[get_current_user] = lambda: usuario_de_teste("/ordem-coleta", "/contrato")
    return TestClient(app), documentos
