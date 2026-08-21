from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..auth import get_current_user
from ..servicos import email_inbox
from ..servicos.comunicacao import send_email_message

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


@router.post("/enviar")
async def enviar_email(
    destinatarios: str = Form(...),
    assunto: str = Form(""),
    corpo: str = Form(""),
    anexos: list[UploadFile] = File(default=[]),
):
    lista_destinatarios = [d.strip() for d in destinatarios.split(",") if d.strip()]
    if not lista_destinatarios:
        raise HTTPException(status_code=400, detail="Informe ao menos um destinatario")

    tmp_dir = None
    caminhos_temp: list[str] = []
    try:
        arquivos_validos = [a for a in anexos if a.filename]
        if arquivos_validos:
            tmp_dir = tempfile.mkdtemp()
        for arquivo in arquivos_validos:
            # Salva com o nome original (nao um nome aleatorio) pra que o
            # anexo chegue ao destinatario com o nome de arquivo correto.
            path = os.path.join(tmp_dir, os.path.basename(arquivo.filename))
            with open(path, "wb") as f:
                f.write(await arquivo.read())
            caminhos_temp.append(path)

        try:
            await run_in_threadpool(send_email_message, lista_destinatarios, assunto, corpo, caminhos_temp)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Falha ao enviar e-mail: {exc}")
    finally:
        for path in caminhos_temp:
            try:
                os.remove(path)
            except OSError:
                pass
        if tmp_dir:
            try:
                os.rmdir(tmp_dir)
            except OSError:
                pass

    return {"ok": True}
