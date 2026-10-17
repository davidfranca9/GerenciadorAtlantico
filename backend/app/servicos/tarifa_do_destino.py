"""A tarifa por tonelada de um destino, pelo que ja foi cobrado la.

O CT-e automatico precisa de tarifa. A fonte de verdade e a cotacao
registrada - mas nunca houve cotacao cadastrada, e sem ela o automatico
nunca disparava, mesmo com nota, XML e agendamento prontos. A equipe ja
cobra o mesmo valor por destino (Taiobeiras: R$ 240/t nas cinco cargas
de outubro), entao quando nao ha cotacao vale o do ultimo CT-e emitido
pro mesmo destino.

O rascunho sai com essa origem escrita, e quem confere no Bsoft ve de
onde veio o numero antes de transmitir.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..models import CarregamentoFinanceiro


def _tarifa_da_carga(carga: CarregamentoFinanceiro) -> Optional[float]:
    """Tarifa que essa carga cobrou, em R$/t.

    Parte do TOTAL DO SERVICO quando ele existe: em carga CIF com ICMS ST o
    "frete cobrado" e o valor a receber, ja sem o imposto retido, e a tarifa
    do CT-e e a do servico. Complemento e acrescimo de valor, nao de
    viagem: sai da conta, senao a tarifa de uma carga com complemento
    ficaria maior que a real.
    """
    peso = float(carga.peso or 0)
    if peso <= 0:
        return None
    total = carga.frete_servico_total if carga.frete_servico_total is not None else carga.frete_empresa_total
    if total is None:
        return None
    base = float(total) - float(carga.complemento_total or 0)
    return round(base / peso, 2) if base > 0 else None


def do_ultimo_cte(db: Session, destino: str, cliente: str = "") -> Optional[dict]:
    """{"tarifa": 240.0, "cte": "5337", "data": date, "destino": ..., "do_cliente": bool}.

    Do mesmo cliente vale mais; sem cliente, o ultimo CT-e do destino. Linha de
    complemento (so acrescimo) e carga cancelada nao contam.
    """
    cidade = (destino or "").split("-")[0].split("/")[0].strip()
    if not cidade:
        return None
    base = (
        db.query(CarregamentoFinanceiro)
        .filter(
            CarregamentoFinanceiro.cancelado.is_(False),
            CarregamentoFinanceiro.destino.ilike(f"%{cidade}%"),
            CarregamentoFinanceiro.peso > 0,
            CarregamentoFinanceiro.complemento_de == "",
        )
        .order_by(CarregamentoFinanceiro.data_emissao.desc(), CarregamentoFinanceiro.id.desc())
    )
    escolhas = []
    if cliente.strip():
        escolhas.append((True, base.filter(CarregamentoFinanceiro.cliente.ilike(f"%{cliente.split()[0]}%"))))
    escolhas.append((False, base))
    for do_cliente, consulta in escolhas:
        for carga in consulta.limit(8).all():
            tarifa = _tarifa_da_carga(carga)
            if tarifa:
                return {
                    "tarifa": tarifa, "cte": carga.ctes, "data": carga.data_emissao,
                    "destino": carga.destino, "do_cliente": do_cliente,
                }
    return None
