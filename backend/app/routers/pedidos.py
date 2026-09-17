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
from ..models import AgendamentoItem, BaixaPedido, Cidade, Pedido
from ..servicos import ocr, saldo_pedidos

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


def _restante(p: Pedido) -> float:
    return max(0.0, round(p.toneladas_total - p.toneladas_usadas, 4))


def _fechado(p: Pedido) -> bool:
    """Todo o saldo ja foi agendado."""
    return (p.toneladas_total or 0) > 0 and _restante(p) <= 0.001


def _to_dict(p: Pedido) -> dict:
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
        "toneladas_restante": _restante(p),
        "novo": _eh_novo(p),
        "cidades_candidatas": _candidatas(p),
        "fechado": _fechado(p),
        "retirado_em": getattr(p, "retirado_em", None),
        "baixas": [
            {
                "id": b.id,
                "toneladas": b.toneladas,
                "motivo": b.motivo,
                "criado_em": b.criado_em,
                "criado_por": b.criado_por,
            }
            for b in getattr(p, "baixas", [])
        ],
    }


@router.get("")
def listar_pedidos(
    mostrar_esgotados: bool = Query(False),
    ocultar_retirados: bool = Query(False),
    db: Session = Depends(get_db),
):
    """ocultar_retirados: a tela de Pedidos mostra os fechados, menos os que
    alguem ja tirou da lista. Se o saldo voltar (agendamento cancelado), o
    pedido tirado reaparece - tem carga pra agendar de novo."""
    query = db.query(Pedido).order_by(Pedido.created_at.desc())
    pedidos = [_to_dict(p) for p in query.all()]
    if not mostrar_esgotados:
        pedidos = [p for p in pedidos if p["toneladas_restante"] > 0.001]
    if ocultar_retirados:
        pedidos = [p for p in pedidos if not (p["retirado_em"] and p["toneladas_restante"] <= 0.001)]
    return pedidos


class PedidosIn(BaseModel):
    pedido_ids: list[int]


def _pedidos_do_payload(db: Session, payload: PedidosIn) -> list[Pedido]:
    ids = set(payload.pedido_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="Informe os pedidos")
    pedidos = db.query(Pedido).filter(Pedido.id.in_(ids)).all()
    if len(pedidos) != len(ids):
        raise HTTPException(status_code=404, detail="Algum dos pedidos nao foi encontrado")
    return pedidos


@router.post("/retirar")
def retirar_da_lista(payload: PedidosIn, db: Session = Depends(get_db)):
    """Tira da tela de Pedidos um pedido com o carregamento fechado. Nao apaga:
    o pedido continua ligado aos agendamentos e pode voltar."""
    pedidos = _pedidos_do_payload(db, payload)
    abertos = sorted({p.contrato or str(p.id) for p in pedidos if not _fechado(p)})
    if abertos:
        raise HTTPException(
            status_code=400,
            detail=f"So sai da lista pedido com o carregamento fechado. Ainda tem saldo: {', '.join(abertos)}",
        )
    agora = datetime.utcnow()
    for pedido in pedidos:
        pedido.retirado_em = agora
    db.commit()
    return {"pedidos": [_to_dict(p) for p in pedidos]}


@router.post("/devolver")
def devolver_para_lista(payload: PedidosIn, db: Session = Depends(get_db)):
    """Desfaz o "tirar da lista"."""
    pedidos = _pedidos_do_payload(db, payload)
    for pedido in pedidos:
        pedido.retirado_em = None
    db.commit()
    return {"pedidos": [_to_dict(p) for p in pedidos]}


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
    # O agendamento guarda uma copia da cidade do pedido. A copia que ainda e
    # a cidade antiga acompanha a correcao - senao o 041594, lido como
    # Capitao-RS, continuava RS nos agendamentos ja criados. Se alguem mudou
    # a cidade direto no agendamento, fica como esta.
    antigas = {p.id: (p.cidade or "").strip() for p in pedidos}
    itens_corrigidos = 0
    for item in db.query(AgendamentoItem).filter(AgendamentoItem.pedido_ref_id.in_(ids)).all():
        if (item.cidade or "").strip() == antigas[item.pedido_ref_id] and item.cidade != texto:
            item.cidade = texto
            itens_corrigidos += 1
    for pedido in pedidos:
        pedido.cidade = texto
        pedido.cidades_candidatas = ""
    db.commit()
    return {"cidade": texto, "pedidos": [_to_dict(p) for p in pedidos], "agendamento_itens_corrigidos": itens_corrigidos}


class BaixaIn(BaseModel):
    toneladas: float
    motivo: str = ""


@router.post("/{pedido_id}/baixa")
def dar_baixa(pedido_id: int, payload: BaixaIn, db: Session = Depends(get_db), usuario=Depends(get_current_user)):
    """Baixa manual: tonelada carregada fora do sistema (ou cortada pela
    fabrica) que precisa sair do saldo sem ter agendamento."""
    pedido = db.get(Pedido, pedido_id)
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido nao encontrado")
    toneladas = round(float(payload.toneladas or 0), 4)
    if toneladas <= 0:
        raise HTTPException(status_code=400, detail="Informe quantas toneladas dar baixa")
    livre = _restante(pedido)
    if toneladas > livre + 0.001:
        raise HTTPException(status_code=400, detail=f"Esse produto tem só {livre:.4f}".rstrip("0").rstrip(".") + " t livres")
    db.add(BaixaPedido(
        pedido_id=pedido.id, toneladas=toneladas, motivo=(payload.motivo or "").strip()[:255],
        criado_por=getattr(usuario, "email", "") or "",
    ))
    pedido.toneladas_usadas = round((pedido.toneladas_usadas or 0.0) + toneladas, 4)
    db.commit()
    db.refresh(pedido)
    return _to_dict(pedido)


@router.delete("/baixas/{baixa_id}")
def desfazer_baixa(baixa_id: int, db: Session = Depends(get_db)):
    """Desfaz a baixa manual e devolve as toneladas pro saldo."""
    baixa = db.get(BaixaPedido, baixa_id)
    if baixa is None:
        raise HTTPException(status_code=404, detail="Baixa nao encontrada")
    pedido = db.get(Pedido, baixa.pedido_id)
    if pedido is not None:
        pedido.toneladas_usadas = round(max(0.0, (pedido.toneladas_usadas or 0.0) - float(baixa.toneladas or 0)), 4)
    db.delete(baixa)
    db.commit()
    if pedido is None:
        return {"ok": True}
    db.refresh(pedido)
    return _to_dict(pedido)


@router.get("/conciliacao")
def ver_conciliacao(db: Session = Depends(get_db)):
    """LEITURA. Barras que nao batem com os agendamentos, e como ficariam."""
    return saldo_pedidos.conciliar(db, aplicar=False)


@router.post("/conciliacao")
def aplicar_conciliacao(db: Session = Depends(get_db)):
    """Acerta a barra de todos os pedidos pelos agendamentos e liga os itens
    antigos que ficaram sem vinculo."""
    return saldo_pedidos.conciliar(db, aplicar=True)


@router.delete("/{pedido_id}")
def excluir_pedido(pedido_id: int, db: Session = Depends(get_db)):
    pedido = db.get(Pedido, pedido_id)
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido nao encontrado")
    db.delete(pedido)
    db.commit()
    return {"ok": True}
