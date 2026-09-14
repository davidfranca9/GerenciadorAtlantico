"""Monta o roteador de documentos pra teste, sem banco real e sem login.

O roteador importa o gerador de O.C. em HTML, que depende do WeasyPrint -
e o WeasyPrint nao carrega no Windows sem as bibliotecas do GTK. Quando o
import real falha, entra um substituto: nenhum teste daqui gera O.C.
"""
from __future__ import annotations

import sys
import types

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


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
    app.dependency_overrides[get_current_user] = lambda: None
    return TestClient(app), documentos
