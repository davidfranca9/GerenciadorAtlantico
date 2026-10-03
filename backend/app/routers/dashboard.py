from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import exigir_tela
from ..database import get_db
from ..models import Agendamento, Pedido

# O resumo da semana existe so pro Dashboard (DashboardPage).
router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(exigir_tela("/dashboard"))])

DIAS_LABEL = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado"]


def _dias_da_semana(base: date) -> list[date]:
    """Segunda a sabado da semana de `base` (a operacao nao carrega aos domingos)."""
    segunda = base - timedelta(days=base.weekday())
    return [segunda + timedelta(days=i) for i in range(6)]


@router.get("/resumo")
def resumo_dashboard(
    semana: str = Query("", description="Qualquer dia (AAAA-MM-DD) da semana a mostrar; vazio = semana atual"),
    db: Session = Depends(get_db),
):
    hoje = date.today()
    if semana:
        try:
            base = date.fromisoformat(semana)
        except ValueError:
            raise HTTPException(status_code=400, detail="Data da semana invalida; use AAAA-MM-DD")
    else:
        base = hoje
    dias = _dias_da_semana(base)
    datas_str = [d.strftime("%d/%m/%Y") for d in dias]

    agendamentos = db.query(Agendamento).filter(Agendamento.loading_date.in_(datas_str)).all()
    peso_por_dia = {ds: 0.0 for ds in datas_str}
    pedidos_por_dia = {ds: 0 for ds in datas_str}
    for a in agendamentos:
        peso_por_dia[a.loading_date] = peso_por_dia.get(a.loading_date, 0) + (a.total_tons or 0)
        pedidos_por_dia[a.loading_date] = pedidos_por_dia.get(a.loading_date, 0) + 1

    dias_semana = [
        {
            "dia": DIAS_LABEL[i],
            "data": datas_str[i],
            "toneladas": round(peso_por_dia[datas_str[i]], 2),
            "agendamentos": pedidos_por_dia[datas_str[i]],
        }
        for i in range(6)
    ]

    todos_pedidos = db.query(Pedido).all()
    saldo_total_pedidos = sum(max(0.0, p.toneladas_total - p.toneladas_usadas) for p in todos_pedidos)
    total_geral_pedidos = sum(p.toneladas_total for p in todos_pedidos)

    total_agendamentos_abertos = (
        db.query(Agendamento).filter(Agendamento.status != "Carregou", Agendamento.status != "Cancelado").count()
    )

    return {
        "semana": {
            "inicio": datas_str[0],
            "fim": datas_str[5],
            "inicio_iso": dias[0].isoformat(),
            "fim_iso": dias[5].isoformat(),
            "anterior": (dias[0] - timedelta(days=7)).isoformat(),
            "proxima": (dias[0] + timedelta(days=7)).isoformat(),
            "eh_semana_atual": dias[0] == hoje - timedelta(days=hoje.weekday()),
            "toneladas_total": round(sum(peso_por_dia.values()), 2),
            "agendamentos_total": sum(pedidos_por_dia.values()),
            "dias": dias_semana,
        },
        "pedidos": {
            "saldo_total": round(saldo_total_pedidos, 2),
            "total_geral": round(total_geral_pedidos, 2),
            "quantidade": len(todos_pedidos),
        },
        "agendamentos_em_aberto": total_agendamentos_abertos,
    }
