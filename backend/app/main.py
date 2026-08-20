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
from .routers.documentos import router as documentos_router
from .routers.email_inbox import router as email_inbox_router
from .routers.fretes import router as fretes_router

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


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS observacoes VARCHAR(2000) DEFAULT ''"))
            conn.execute(text("ALTER TABLE cidades ADD COLUMN IF NOT EXISTS ibge VARCHAR(16) DEFAULT ''"))
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


