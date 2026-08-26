"""Recebimento de pedidos via WhatsApp (Meta Cloud API) + tela manual de conversas.

Fluxo automatico: cliente manda um PDF de pedido pro numero do WhatsApp
Business -> Meta chama nosso webhook -> baixamos o arquivo, extraimos os
produtos com o mesmo parser ja usado em /pedidos/importar-pdf, criamos os
Pedidos no banco e respondemos confirmando pro remetente.

Toda mensagem recebida (texto, documento, imagem) e toda mensagem enviada
(automatica ou manual pela tela) fica guardada em WhatsAppMensagem, pra dar
pra tela de "WhatsApp" no sistema mostrar o historico de conversas.

As rotas /webhook NAO exigem login (get_current_user) porque quem chama e a
propria Meta, nao um usuario logado no sistema. A seguranca ali e feita
validando a assinatura HMAC do corpo da requisicao (X-Hub-Signature-256)
contra o WHATSAPP_APP_SECRET. As rotas de conversas/envio manual exigem
login normalmente.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import tempfile

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import SessionLocal, get_db
from ..models import Cidade, Pedido, WhatsAppContato, WhatsAppMensagem
from ..servicos import ocr, whatsapp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

_EXT_POR_MIME = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

MENSAGEM_SEM_PRODUTOS = (
    "Recebi o arquivo, mas nao consegui identificar nenhum produto nele. "
    "Confira o pedido e envie novamente, ou entre em contato com nossa equipe."
)
MENSAGEM_ERRO = "Nao consegui processar o arquivo enviado agora. Nossa equipe vai verificar em breve."
MENSAGEM_FORMATO_INVALIDO = "No momento so consigo ler pedidos em PDF. Pode reenviar nesse formato?"


def _registrar_mensagem(
    db: Session,
    numero: str,
    direcao: str,
    tipo: str = "texto",
    conteudo: str = "",
    nome_arquivo: str = "",
    status: str = "",
    mime_type: str = "",
    midia: bytes | None = None,
) -> WhatsAppMensagem:
    mensagem = WhatsAppMensagem(
        numero=numero,
        direcao=direcao,
        tipo=tipo,
        conteudo=conteudo[:4000],
        nome_arquivo=nome_arquivo,
        mime_type=mime_type,
        midia=midia,
        status=status,
    )
    db.add(mensagem)
    db.commit()
    db.refresh(mensagem)
    return mensagem


def _enviar_e_registrar(db: Session, numero: str, texto: str) -> None:
    """Manda a mensagem e guarda no historico, com o status de erro se falhar
    (mas sem esconder a excecao - quem chamou decide o que fazer com ela)."""
    try:
        whatsapp.enviar_mensagem_texto(numero, texto)
        _registrar_mensagem(db, numero, "saida", "texto", texto, status="enviada")
    except Exception:
        _registrar_mensagem(db, numero, "saida", "texto", texto, status="erro")
        raise


@router.get("/webhook")
def verificar_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Chamado pela Meta uma unica vez, ao cadastrar a URL do webhook."""
    if hub_mode == "subscribe" and settings.whatsapp_verify_token and hub_verify_token == settings.whatsapp_verify_token:
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(status_code=403, detail="Token de verificacao invalido")


def _assinatura_valida(corpo: bytes, assinatura_recebida: str) -> bool:
    if not settings.whatsapp_app_secret:
        # Sem app secret configurado ainda nao da pra validar - permite
        # passar (usado so na fase inicial, antes do secret ser setado).
        return True
    esperado = "sha256=" + hmac.new(settings.whatsapp_app_secret.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, assinatura_recebida or "")


def _processar_arquivo_recebido(numero_remetente: str, mensagem_id: int, media_id: str, mime_type: str) -> None:
    """Roda em background (fora do request do webhook): baixa o arquivo (pra
    guardar e permitir tocar/ver depois na tela de conversas) e, se for PDF,
    extrai os produtos e cria os Pedidos. Sempre responde ao remetente quando
    o formato nao da pra processar como pedido, mesmo em caso de erro."""
    db = SessionLocal()
    try:
        conteudo = None
        try:
            url = whatsapp.obter_url_midia(media_id)
            conteudo = whatsapp.baixar_midia(url)
            mensagem = db.get(WhatsAppMensagem, mensagem_id)
            if mensagem:
                mensagem.mime_type = mime_type
                mensagem.midia = conteudo
                db.commit()
        except Exception:
            logger.exception("Falha ao baixar midia recebida do WhatsApp")

        if mime_type != "application/pdf":
            try:
                _enviar_e_registrar(db, numero_remetente, MENSAGEM_FORMATO_INVALIDO)
            except Exception:
                logger.exception("Falha ao responder remetente sobre formato invalido")
            return

        if conteudo is None:
            try:
                _enviar_e_registrar(db, numero_remetente, MENSAGEM_ERRO)
            except Exception:
                logger.exception("Falha ao responder remetente sobre erro de processamento")
            return

        path = None
        try:
            suffix = _EXT_POR_MIME.get(mime_type, ".pdf")
            fd, path = tempfile.mkstemp(suffix=suffix)
            with os.fdopen(fd, "wb") as f:
                f.write(conteudo)

            cidades = [(c.nome, c.uf) for c in db.query(Cidade).all()]
            resultado = ocr.parse_pdf_fields(path, cidades)
            produtos = resultado.get("produtos") or []

            criados = 0
            contratos_criados: set[str] = set()
            for item in produtos:
                toneladas = float(item.get("toneladas") or 0)
                if toneladas <= 0:
                    continue
                contrato = str(item.get("contrato") or "")
                db.add(
                    Pedido(
                        contrato=contrato,
                        produto=str(item.get("produto") or ""),
                        embalagem=str(item.get("embalagem") or ""),
                        cidade=str(item.get("cidade") or ""),
                        cliente=str(item.get("cliente") or ""),
                        supplier=settings.whatsapp_supplier_padrao or "AFL",
                        toneladas_total=toneladas,
                        toneladas_usadas=0,
                    )
                )
                criados += 1
                contratos_criados.add(contrato or f"__sem-numero-{criados}")
            db.commit()

            if criados:
                total_pedidos = len(contratos_criados)
                texto_confirmacao = f"Pedido recebido! {criados} produto(s) de {total_pedidos} pedido(s) cadastrado(s) no sistema."
            else:
                texto_confirmacao = MENSAGEM_SEM_PRODUTOS
            _enviar_e_registrar(db, numero_remetente, texto_confirmacao)
        except Exception:
            logger.exception("Falha ao processar pedido recebido via WhatsApp")
            try:
                _enviar_e_registrar(db, numero_remetente, MENSAGEM_ERRO)
            except Exception:
                logger.exception("Falha ao responder remetente sobre erro de processamento")
        finally:
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
    finally:
        db.close()


@router.post("/webhook")
async def receber_webhook(request: Request, background_tasks: BackgroundTasks):
    corpo = await request.body()
    if not _assinatura_valida(corpo, request.headers.get("X-Hub-Signature-256", "")):
        raise HTTPException(status_code=403, detail="Assinatura invalida")

    try:
        payload = json.loads(corpo)
    except ValueError:
        return {"status": "ok"}

    db = SessionLocal()
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                valor = change.get("value", {})
                for msg in valor.get("messages") or []:
                    numero = msg.get("from")
                    if not numero:
                        continue
                    tipo_msg = msg.get("type")
                    anexo = msg.get("document") or msg.get("image") or msg.get("audio") or msg.get("video")
                    tipo_pt = {"image": "imagem", "video": "video", "audio": "audio", "document": "documento"}.get(tipo_msg, tipo_msg)

                    if tipo_msg == "text":
                        _registrar_mensagem(db, numero, "entrada", "texto", msg.get("text", {}).get("body", ""))
                    elif anexo:
                        mensagem_registrada = _registrar_mensagem(
                            db,
                            numero,
                            "entrada",
                            tipo_pt,
                            anexo.get("caption", ""),
                            nome_arquivo=anexo.get("filename", ""),
                        )
                        if anexo.get("id"):
                            background_tasks.add_task(
                                _processar_arquivo_recebido,
                                numero,
                                mensagem_registrada.id,
                                anexo["id"],
                                anexo.get("mime_type", "application/pdf"),
                            )
                    else:
                        _registrar_mensagem(db, numero, "entrada", tipo_pt or "desconhecido")
    finally:
        db.close()

    # Responde 200 rapido - a Meta reenvia o webhook se demorar ou falhar.
    return {"status": "ok"}


class EnviarMensagemIn(BaseModel):
    numero: str
    texto: str


@router.get("/conversas", dependencies=[Depends(get_current_user)])
def listar_conversas(db: Session = Depends(get_db)):
    subquery = (
        db.query(WhatsAppMensagem.numero, func.max(WhatsAppMensagem.created_at).label("ultima_em"))
        .group_by(WhatsAppMensagem.numero)
        .subquery()
    )
    ultimas = (
        db.query(WhatsAppMensagem)
        .join(subquery, (WhatsAppMensagem.numero == subquery.c.numero) & (WhatsAppMensagem.created_at == subquery.c.ultima_em))
        .order_by(WhatsAppMensagem.created_at.desc())
        .all()
    )
    contatos = {c.numero: c.nome for c in db.query(WhatsAppContato).all()}
    return [
        {
            "numero": m.numero,
            "nome": contatos.get(m.numero, ""),
            "ultima_mensagem": m.conteudo or m.nome_arquivo or m.tipo,
            "ultima_direcao": m.direcao,
            "ultima_em": m.created_at,
        }
        for m in ultimas
    ]


class ContatoIn(BaseModel):
    numero: str
    nome: str


@router.get("/contatos", dependencies=[Depends(get_current_user)])
def listar_contatos(db: Session = Depends(get_db)):
    return [{"numero": c.numero, "nome": c.nome} for c in db.query(WhatsAppContato).all()]


@router.post("/contatos", dependencies=[Depends(get_current_user)])
def salvar_contato(payload: ContatoIn, db: Session = Depends(get_db)):
    numero = payload.numero.strip()
    if not numero:
        raise HTTPException(status_code=400, detail="Informe o numero")
    contato = db.query(WhatsAppContato).filter(WhatsAppContato.numero == numero).first()
    if contato is None:
        contato = WhatsAppContato(numero=numero, nome=payload.nome.strip())
        db.add(contato)
    else:
        contato.nome = payload.nome.strip()
    db.commit()
    return {"numero": numero, "nome": contato.nome}


@router.get("/conversas/{numero}/mensagens", dependencies=[Depends(get_current_user)])
def listar_mensagens_da_conversa(numero: str, db: Session = Depends(get_db)):
    mensagens = (
        db.query(WhatsAppMensagem)
        .filter(WhatsAppMensagem.numero == numero)
        .order_by(WhatsAppMensagem.created_at.asc())
        .all()
    )
    return [
        {
            "id": m.id,
            "direcao": m.direcao,
            "tipo": m.tipo,
            "conteudo": m.conteudo,
            "nome_arquivo": m.nome_arquivo,
            "mime_type": m.mime_type,
            "tem_midia": m.midia is not None,
            "status": m.status,
            "created_at": m.created_at,
        }
        for m in mensagens
    ]


@router.get("/mensagens/{mensagem_id}/midia", dependencies=[Depends(get_current_user)])
def obter_midia_mensagem(mensagem_id: int, db: Session = Depends(get_db)):
    mensagem = db.get(WhatsAppMensagem, mensagem_id)
    if mensagem is None or not mensagem.midia:
        raise HTTPException(status_code=404, detail="Midia nao encontrada")
    return Response(content=mensagem.midia, media_type=mensagem.mime_type or "application/octet-stream")


@router.post("/enviar", dependencies=[Depends(get_current_user)])
def enviar_mensagem_manual(payload: EnviarMensagemIn, db: Session = Depends(get_db)):
    numero = payload.numero.strip()
    if not numero or not payload.texto.strip():
        raise HTTPException(status_code=400, detail="Informe o numero e o texto da mensagem")
    try:
        _enviar_e_registrar(db, numero, payload.texto)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao enviar mensagem: {exc}")
    return {"ok": True}


@router.post("/enviar-arquivo", dependencies=[Depends(get_current_user)])
async def enviar_arquivo_manual(
    numero: str = Form(...),
    legenda: str = Form(""),
    arquivo: UploadFile = None,
    db: Session = Depends(get_db),
):
    numero = numero.strip()
    if not numero or arquivo is None:
        raise HTTPException(status_code=400, detail="Informe o numero e o arquivo")

    conteudo = await arquivo.read()
    mime_type = arquivo.content_type or "application/octet-stream"
    nome_arquivo = arquivo.filename or "arquivo"
    tipo_registrado = {"image": "imagem", "video": "video", "audio": "audio", "document": "documento"}[
        whatsapp.tipo_mensagem_para_mime(mime_type)
    ]

    try:
        conteudo_enviado, mime_enviado, nome_enviado = await run_in_threadpool(
            whatsapp.enviar_arquivo, numero, conteudo, mime_type, nome_arquivo, legenda
        )
        _registrar_mensagem(
            db, numero, "saida", tipo_registrado, legenda,
            nome_arquivo=nome_enviado, status="enviada", mime_type=mime_enviado, midia=conteudo_enviado,
        )
    except Exception as exc:
        _registrar_mensagem(
            db, numero, "saida", tipo_registrado, legenda,
            nome_arquivo=nome_arquivo, status="erro", mime_type=mime_type, midia=conteudo,
        )
        raise HTTPException(status_code=502, detail=f"Falha ao enviar arquivo: {exc}")
    return {"ok": True}
