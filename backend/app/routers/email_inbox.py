from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..auth import get_current_user
from ..servicos import email_inbox
from ..servicos.comunicacao import send_email_message

router = APIRouter(prefix="/email", tags=["email"], dependencies=[Depends(get_current_user)])


@router.get("/mensagens")
async def listar_mensagens(
    pagina: int = Query(1, ge=1),
    tamanho_pagina: int = Query(25, ge=1, le=100),
    busca: str = Query("", description="Sintaxe de busca do Gmail: from:, subject:, newer_than:7d..."),
):
    try:
        return await run_in_threadpool(email_inbox.listar_mensagens, pagina, tamanho_pagina, busca)
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


@router.get("/mensagens/{msg_id}/thread")
async def obter_thread(msg_id: str):
    """Todas as mensagens da mesma conversa, ja com o conteudo de cada uma.

    Sem isso a tela mostrava so a mensagem aberta, mesmo quando o assunto
    tinha varias respostas trocadas.
    """
    try:
        ids = await run_in_threadpool(email_inbox.obter_thread, msg_id)
        mensagens = [await run_in_threadpool(email_inbox.obter_mensagem, i) for i in ids]
        return {"mensagens": mensagens}
    except email_inbox.InboxIndisponivel as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erro ao abrir a conversa: {exc}")


@router.get("/mensagens/{msg_id}/anexos/{indice}")
async def baixar_anexo(msg_id: str, indice: int):
    """Baixa um anexo da mensagem."""
    try:
        anexo = await run_in_threadpool(email_inbox.obter_anexo, msg_id, indice)
    except email_inbox.InboxIndisponivel as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erro ao baixar o anexo: {exc}")

    nome = anexo["nome"].replace('"', "")
    return Response(
        content=anexo["conteudo"],
        media_type=anexo["tipo"] or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.get("/novos")
async def contar_novos(desde: int = Query(0, ge=0, description="epoch em segundos")):
    """Quantas mensagens chegaram depois do instante informado.

    A tela guarda o momento da ultima visita e pergunta a partir dele, pra
    o contador zerar quando alguem abre a aba.
    """
    if not desde:
        return {"novos": 0}
    try:
        return {"novos": await run_in_threadpool(email_inbox.contar_desde, desde)}
    except Exception:
        # Contador e informativo: se o IMAP falhar, a tela nao pode quebrar.
        return {"novos": 0}


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
