from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.database import get_db
from app.models import Cliente
from app.routers import clientes
from tests.apoio_documentos import banco_em_memoria, usuario_de_teste


def test_cliente_guarda_localizacao_contatos_formatados_e_observacao_multilinha():
    db = banco_em_memoria(Cliente)
    app = FastAPI()
    app.include_router(clientes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: usuario_de_teste("/clientes")
    http = TestClient(app)

    criado = http.post("/clientes", json={
        "nome": "Fazenda Singular", "cnpj_cpf": "08.334.416/0001-10", "cidade": "Ninheira", "uf": "MG",
        "contato": "(39) 9 9563-2810", "telefone": "(38) 9 9000-0000", "email": "fazenda@example.com",
        "roteiro": "Rodovia principal, km 12", "localizacao": "https://maps.google.com/example",
        "observacoes": "Entrada pela porteira azul\nAvisar antes de chegar",
    })

    assert criado.status_code == 200
    dados = criado.json()
    assert dados["localizacao"] == "https://maps.google.com/example"
    assert dados["contato"] == "(39) 9 9563-2810"
    assert dados["observacoes"] == "Entrada pela porteira azul\nAvisar antes de chegar"
    assert http.get("/clientes").json()[0]["cnpj_cpf"] == "08.334.416/0001-10"
    db.close()
