from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .auth import router as auth_router
from .config import settings
from .database import Base, engine
from .routers.admin import router as admin_router
from .routers.agendamentos import router as agendamentos_router
from .routers.bsoft import router as bsoft_router
from .routers.buonny import router as buonny_router
from .routers.clientes import router as clientes_router
from .routers.contrato import router as contrato_router
from .routers.dashboard import router as dashboard_router
from .routers.documentos import router as documentos_router
from .routers.email_inbox import router as email_inbox_router
from .routers.fretes import router as fretes_router
from .routers.pedidos import router as pedidos_router
from .routers.whatsapp import router as whatsapp_router

app = FastAPI(title="Atlantico Fertlog API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Agendamento-Id"],
)

app.include_router(auth_router)
app.include_router(documentos_router)
app.include_router(agendamentos_router)
app.include_router(fretes_router)
app.include_router(clientes_router)
app.include_router(admin_router)
app.include_router(contrato_router)
app.include_router(bsoft_router)
app.include_router(buonny_router)
app.include_router(email_inbox_router)
app.include_router(pedidos_router)
app.include_router(dashboard_router)
app.include_router(whatsapp_router)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS observacoes VARCHAR(2000) DEFAULT ''"))
            conn.execute(text("ALTER TABLE cidades ADD COLUMN IF NOT EXISTS ibge VARCHAR(16) DEFAULT ''"))
            conn.execute(text("ALTER TABLE agendamento_itens ADD COLUMN IF NOT EXISTS pedido_ref_id INTEGER"))
            conn.execute(text("ALTER TABLE cotacoes_frete ADD COLUMN IF NOT EXISTS cliente_id INTEGER"))
            conn.execute(text("ALTER TABLE cotacoes_frete ADD COLUMN IF NOT EXISTS cliente_nome VARCHAR(255) DEFAULT ''"))
            conn.execute(text("ALTER TABLE cotacoes_frete ADD COLUMN IF NOT EXISTS observacoes VARCHAR(1000) DEFAULT ''"))
            conn.execute(text("ALTER TABLE cotacoes_frete ADD COLUMN IF NOT EXISTS fabrica VARCHAR(255) DEFAULT ''"))
            conn.execute(text("ALTER TABLE whatsapp_mensagens ADD COLUMN IF NOT EXISTS mime_type VARCHAR(100) DEFAULT ''"))
            conn.execute(text("ALTER TABLE whatsapp_mensagens ADD COLUMN IF NOT EXISTS midia BYTEA"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS paginas_bloqueadas VARCHAR(1000) DEFAULT ''"))
            conn.execute(text("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS roteiro VARCHAR(2000) DEFAULT ''"))
            # operacoes_fiscais e tabela nova (criada pelo create_all); o indice
            # unico abaixo e a protecao contra emitir dois CT-e pra mesma carga.
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_operacao_agendamento_nfe "
                "ON operacoes_fiscais (agendamento_id, chave_nfe)"
            ))
    except Exception:
        pass

    try:
        from .database import SessionLocal
        from .import_cidades import backfill_ibge_codes

        db = SessionLocal()
        try:
            backfill_ibge_codes(db)
        finally:
            db.close()
    except Exception:
        pass


@app.get("/health")
def health():
    return {"status": "ok"}


