from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from ..auth import get_current_user
from ..servicos import email_inbox

router = APIRouter(prefix="/email", tags=["email"], dependencies=[Depends(get_current_user)])


@router.get("/mensagens")
async def listar_mensagens(pagina: int = Query(1, ge=1), tamanho_pagina: int = Query(25, ge=1, le=100)):
    try:
        return await run_in_threadpool(email_inbox.listar_mensagens, pagina, tamanho_pagina)
    except email_inbox.InboxIndisponivel as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erro ao acessar a caixa de entrada: {exc}")


@router.get("/mensagens/{msg_id}")
async def obter_mensagem(msg_id: str):
    try:
        return await run_in_threadpool(email_inbox.obter_mensagem, msg_id)
    except email_inbox.InboxIndisponivel as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erro ao abrir a mensagem: {exc}")
