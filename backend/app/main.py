from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import router as auth_router
from .config import settings
from .database import Base, engine
from .routers.agendamentos import router as agendamentos_router
from .routers.documentos import router as documentos_router
from .routers.fretes import router as fretes_router

app = FastAPI(title="Atlantico Fertlog API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(documentos_router)
app.include_router(agendamentos_router)
app.include_router(fretes_router)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}
