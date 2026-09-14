from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Cidade, Pedido
from ..servicos import ocr

router = APIRouter(prefix="/pedidos", tags=["pedidos"], dependencies=[Depends(get_current_user)])

# Um pedido e "novo" enquanto ninguem tirou carga dele e ele chegou ha pouco.
# Tres dias cobrem um fim de semana: o que chega na sexta a noite ainda
# aparece como novo na segunda.
JANELA_PEDIDO_NOVO = timedelta(days=3)


def _eh_novo(p: Pedido, agora: datetime | None = None) -> bool:
    if not p.created_at or (p.toneladas_usadas or 0) > 0:
        return False
    return (agora or datetime.utcnow()) - p.created_at <= JANELA_PEDIDO_NOVO


def _candidatas(p: Pedido) -> list[str]:
    try:
        valor = json.loads(getattr(p, "cidades_candidatas", "") or "[]")
    except ValueError:
        return []
    return valor if isinstance(valor, list) else []


def _to_dict(p: Pedido) -> dict:
    restante = round(p.toneladas_total - p.toneladas_usadas, 4)
    return {
        "id": p.id,
        "created_at": p.created_at,
        "contrato": p.contrato,
        "produto": p.produto,
        "embalagem": p.embalagem,
        "cidade": p.cidade,
        "cliente": p.cliente,
        "supplier": p.supplier,
        "toneladas_total": p.toneladas_total,
        "toneladas_usadas": p.toneladas_usadas,
        "toneladas_restante": max(0.0, restante),
        "novo": _eh_novo(p),
        "cidades_candidatas": _candidatas(p),
    }


@router.get("")
def listar_pedidos(mostrar_esgotados: bool = Query(False), db: Session = Depends(get_db)):
    query = db.query(Pedido).order_by(Pedido.created_at.desc())
    pedidos = [_to_dict(p) for p in query.all()]
    if not mostrar_esgotados:
        pedidos = [p for p in pedidos if p["toneladas_restante"] > 0.001]
    return pedidos


@router.post("/importar-pdf")
async def importar_pdf(file: UploadFile, supplier: str = "AFL", db: Session = Depends(get_db)):
    suffix = os.path.splitext(file.filename or "")[1] or ".pdf"
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(await file.read())
    try:
        cidades = [(c.nome, c.uf) for c in db.query(Cidade).all()]
        resultado = await run_in_threadpool(ocr.parse_pdf_fields, path, cidades)
    finally:
        os.remove(path)

    produtos = resultado.get("produtos") or []
    criados = []
    for item in produtos:
        toneladas = float(item.get("toneladas") or 0)
        if toneladas <= 0:
            continue
        pedido = Pedido(
            contrato=str(item.get("contrato") or ""),
            produto=str(item.get("produto") or ""),
            embalagem=str(item.get("embalagem") or ""),
            cidade=str(item.get("cidade") or ""),
            cliente=str(item.get("cliente") or ""),
            supplier=supplier.upper() if supplier.upper() in ("AFL", "HERINGER") else "AFL",
            cidades_candidatas="" if item.get("cidade") else ocr.candidatas_para_guardar(resultado),
            toneladas_total=toneladas,
            toneladas_usadas=0,
        )
        db.add(pedido)
        criados.append(pedido)

    db.commit()
    for pedido in criados:
        db.refresh(pedido)
    return {"pedidos": [_to_dict(p) for p in criados], "cidades_candidatas": resultado.get("cidades_candidatas") or []}


class DefinirCidadeIn(BaseModel):
    pedido_ids: list[int]
    cidade: str
    uf: str


@router.patch("/cidade")
def definir_cidade(payload: DefinirCidadeIn, db: Session = Depends(get_db)):
    """Define a cidade dos pedidos que a leitura do PDF deixou sem.

    So aceita cidade do cadastro, e grava no mesmo formato da leitura
    ("Nome-UF", com o acento do cadastro) - e o formato que a cotacao de
    frete usa pra achar a tarifa do destino.
    """
    ids = set(payload.pedido_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="Informe os pedidos")
    uf = payload.uf.strip().upper()
    procurada = ocr.normalizar_texto_sem_acento(payload.cidade)
    cidade = next(
        (c for c in db.query(Cidade).filter(Cidade.uf == uf).all()
         if ocr.normalizar_texto_sem_acento(c.nome) == procurada),
        None,
    )
    if cidade is None:
        raise HTTPException(
            status_code=400,
            detail=f"Cidade '{payload.cidade.strip()}' nao encontrada em {uf or '(sem UF)'} no cadastro de cidades.",
        )
    pedidos = db.query(Pedido).filter(Pedido.id.in_(ids)).all()
    if len(pedidos) != len(ids):
        raise HTTPException(status_code=404, detail="Algum dos pedidos nao foi encontrado")

    texto = ocr.formatar_cidade(cidade.nome, cidade.uf)
    for pedido in pedidos:
        pedido.cidade = texto
        pedido.cidades_candidatas = ""
    db.commit()
    return {"cidade": texto, "pedidos": [_to_dict(p) for p in pedidos]}


@router.delete("/{pedido_id}")
def excluir_pedido(pedido_id: int, db: Session = Depends(get_db)):
    pedido = db.get(Pedido, pedido_id)
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido nao encontrado")
    db.delete(pedido)
    db.commit()
    return {"ok": True}
