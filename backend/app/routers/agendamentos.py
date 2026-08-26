from __future__ import annotations

import logging
import tempfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import STATUS_AGENDAMENTO, Agendamento, AgendamentoItem, Pedido
from ..servicos.comunicacao import imagem_assinatura_inline, montar_autorizacao_agendamento, send_email_message
from .documentos import Produto, OrdemColetaRequest, _gerar_oc_arquivos

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agendamentos", tags=["agendamentos"], dependencies=[Depends(get_current_user)])

RECIPIENTES_AUTORIZACAO_FERTIMAXI = [
    "atlanticofertlog.comercial@gmail.com",
    "luan.santos@fertimaxi.com.br",
    "paulo.moura@fertimaxi.com.br",
]


def _eh_fertimaxi(supplier: str) -> bool:
    return (supplier or "").strip().lower() in {"afl", "fertimaxi", "fertimax"}


def _gerar_anexos_oc(agendamento: Agendamento) -> list[str]:
    """Gera a O.C. em PDF (e a Autorizacao de Coleta em xlsx, quando nao for
    Heringer) do agendamento, pra anexar no e-mail - mesmo documento que sai
    quando a O.C. e emitida pela tela de Ordem de Coleta."""
    template = "HERINGER" if agendamento.supplier.strip().lower() == "heringer" else "AFL"
    payload = OrdemColetaRequest(
        template=template,
        produtos=[
            Produto(
                contrato=item.pedido,
                produto=item.produto,
                embalagem=item.embalagem,
                toneladas=str(item.toneladas),
                cidade=item.cidade,
                cliente=item.cliente,
                pedido_id=item.pedido_ref_id,
            )
            for item in agendamento.itens
        ],
        cpf=agendamento.driver_cpf,
        nome=agendamento.driver_name,
        cnh=agendamento.cnh,
        fone=agendamento.driver_phone,
        placa1=agendamento.plate_cavalo,
        placa2=agendamento.plate_carreta1,
        placa3=agendamento.plate_carreta2,
        data_carregamento=agendamento.loading_date,
        observacoes=agendamento.observacoes,
    )
    arquivos = _gerar_oc_arquivos(payload, tempfile.mkdtemp())
    anexos = [arquivos["pdf"]]
    if arquivos.get("xlsx"):
        anexos.append(arquivos["xlsx"])
    return anexos


def _enviar_autorizacoes_agendamento_fertimaxi(agendamento: Agendamento) -> None:
    """Pra cada pedido/cliente distinto do agendamento, manda um e-mail pra
    Fertimaxi solicitando a autorizacao de agendamento, com a O.C. anexada.
    Falha no envio nao derruba a criacao do agendamento - so fica
    registrada no log."""
    try:
        anexos = _gerar_anexos_oc(agendamento)
    except Exception:
        logger.exception("Falha ao gerar anexos da O.C. pro e-mail de autorizacao - enviando sem anexo")
        anexos = []

    vistos: set[tuple[str, str]] = set()
    for item in agendamento.itens:
        cliente, pedido = item.cliente.strip(), item.pedido.strip()
        if not cliente or not pedido or (cliente, pedido) in vistos:
            continue
        vistos.add((cliente, pedido))

        titulo, corpo = montar_autorizacao_agendamento(cliente, pedido, agendamento.loading_date)
        try:
            send_email_message(
                RECIPIENTES_AUTORIZACAO_FERTIMAXI,
                titulo,
                corpo,
                anexos,
                imagens_inline=imagem_assinatura_inline(),
            )
        except Exception:
            logger.exception("Falha ao enviar e-mail de autorizacao de agendamento pra Fertimaxi (pedido %s)", pedido)


class AgendamentoItemIn(BaseModel):
    pedido: str = ""
    cliente: str = ""
    produto: str = ""
    cidade: str = ""
    embalagem: str = ""
    toneladas: float = 0
    pedido_id: Optional[int] = None


class AgendamentoIn(BaseModel):
    status: str = STATUS_AGENDAMENTO[0]
    supplier: str = ""
    loading_date: str = ""
    driver_name: str = ""
    driver_cpf: str = ""
    driver_phone: str = ""
    cnh: str = ""
    plate_cavalo: str = ""
    plate_carreta1: str = ""
    plate_carreta2: str = ""
    roteiro: str = ""
    localizador: str = ""
    contato_cliente: str = ""
    observacoes: str = ""
    itens: list[AgendamentoItemIn] = []


class AgendamentoStatusIn(BaseModel):
    status: str


def _to_dict(a: Agendamento) -> dict:
    return {
        "id": a.id,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
        "status": a.status,
        "supplier": a.supplier,
        "loading_date": a.loading_date,
        "driver_name": a.driver_name,
        "driver_cpf": a.driver_cpf,
        "driver_phone": a.driver_phone,
        "cnh": a.cnh,
        "plate_cavalo": a.plate_cavalo,
        "plate_carreta1": a.plate_carreta1,
        "plate_carreta2": a.plate_carreta2,
        "total_items": a.total_items,
        "total_tons": a.total_tons,
        "roteiro": a.roteiro,
        "localizador": a.localizador,
        "contato_cliente": a.contato_cliente,
        "observacoes": a.observacoes,
        "itens": [
            {
                "id": it.id,
                "pedido": it.pedido,
                "cliente": it.cliente,
                "produto": it.produto,
                "cidade": it.cidade,
                "embalagem": it.embalagem,
                "toneladas": it.toneladas,
            }
            for it in a.itens
        ],
    }


@router.get("")
def listar_agendamentos(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Agendamento)
    if status:
        query = query.filter(Agendamento.status == status)
    agendamentos = query.order_by(Agendamento.created_at.desc()).all()
    return [_to_dict(a) for a in agendamentos]


@router.post("")
def criar_agendamento(payload: AgendamentoIn, db: Session = Depends(get_db)):
    itens = payload.itens
    agendamento = Agendamento(
        **payload.model_dump(exclude={"itens"}),
        total_items=len(itens),
        total_tons=sum(i.toneladas for i in itens),
    )
    agendamento.itens = [
        AgendamentoItem(**i.model_dump(exclude={"pedido_id"}), pedido_ref_id=i.pedido_id) for i in itens
    ]
    db.add(agendamento)

    # Desconta o saldo dos pedidos vinculados, igual acontece quando a O.C.
    # e gerada pelo fluxo normal (Pedidos -> Ordem de Coleta).
    for item in itens:
        if not item.pedido_id:
            continue
        pedido = db.get(Pedido, item.pedido_id)
        if pedido is None:
            continue
        pedido.toneladas_usadas = min(pedido.toneladas_total, pedido.toneladas_usadas + item.toneladas)

    db.commit()
    db.refresh(agendamento)

    if _eh_fertimaxi(agendamento.supplier):
        _enviar_autorizacoes_agendamento_fertimaxi(agendamento)

    return _to_dict(agendamento)


@router.get("/{agendamento_id}")
def obter_agendamento(agendamento_id: int, db: Session = Depends(get_db)):
    agendamento = db.get(Agendamento, agendamento_id)
    if agendamento is None:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado")
    return _to_dict(agendamento)


@router.delete("/{agendamento_id}")
def excluir_agendamento(agendamento_id: int, db: Session = Depends(get_db)):
    agendamento = db.get(Agendamento, agendamento_id)
    if agendamento is None:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado")

    # Devolve o saldo pros pedidos vinculados antes de apagar - excluir uma
    # O.C. libera de volta a tonelada que tinha sido descontada dela.
    for item in agendamento.itens:
        if not item.pedido_ref_id:
            continue
        pedido = db.get(Pedido, item.pedido_ref_id)
        if pedido is None:
            continue
        pedido.toneladas_usadas = max(0.0, pedido.toneladas_usadas - item.toneladas)

    db.delete(agendamento)
    db.commit()
    return {"ok": True}


@router.patch("/{agendamento_id}/status")
def atualizar_status(agendamento_id: int, payload: AgendamentoStatusIn, db: Session = Depends(get_db)):
    agendamento = db.get(Agendamento, agendamento_id)
    if agendamento is None:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado")
    if payload.status not in STATUS_AGENDAMENTO:
        raise HTTPException(status_code=400, detail=f"Status invalido. Use um de: {STATUS_AGENDAMENTO}")
    agendamento.status = payload.status
    agendamento.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(agendamento)
    return _to_dict(agendamento)
