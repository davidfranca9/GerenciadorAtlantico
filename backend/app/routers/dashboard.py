from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Agendamento, Pedido

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)])

DIAS_LABEL = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado"]


def _dias_da_semana_atual() -> list[date]:
    """Segunda a sabado da semana atual (a operacao nao carrega aos domingos)."""
    hoje = date.today()
    segunda = hoje - timedelta(days=hoje.weekday())
    return [segunda + timedelta(days=i) for i in range(6)]


@router.get("/resumo")
def resumo_dashboard(db: Session = Depends(get_db)):
    dias = _dias_da_semana_atual()
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
