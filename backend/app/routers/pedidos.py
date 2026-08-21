from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Cidade, Pedido
from ..servicos import ocr

router = APIRouter(prefix="/pedidos", tags=["pedidos"], dependencies=[Depends(get_current_user)])


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
            toneladas_total=toneladas,
            toneladas_usadas=0,
        )
        db.add(pedido)
        criados.append(pedido)

    db.commit()
    for pedido in criados:
        db.refresh(pedido)
    return {"pedidos": [_to_dict(p) for p in criados], "cidades_candidatas": resultado.get("cidades_candidatas") or []}


@router.delete("/{pedido_id}")
def excluir_pedido(pedido_id: int, db: Session = Depends(get_db)):
    pedido = db.get(Pedido, pedido_id)
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido nao encontrado")
    db.delete(pedido)
    db.commit()
    return {"ok": True}
