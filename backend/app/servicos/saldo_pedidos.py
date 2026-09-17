"""O saldo do pedido (a barra da tela de Pedidos) acompanha os agendamentos.

A barra e toneladas_usadas / toneladas_total. Ate aqui ela so andava quando
o item do agendamento trazia o id do pedido, e varios caminhos nao traziam:
a autorizacao gerada na tela de Contratos (o caminho sem motorista), o
"Salvar e regerar" da tela de Agendamentos (que reescrevia os itens sem o
vinculo) e pedido carregado pela tela de Contratos. Resultado: agendamento
feito e barra parada - e agendamento apagado sem devolver o saldo.

Regras daqui:

  * item sem id acha o pedido pelo numero + produto, que e o que a pessoa
    ve na tela. Havendo mais de uma linha igual (pedido importado duas
    vezes), vai pra que ainda tem saldo.
  * gravar um agendamento aplica a DIFERENCA entre o que ele ocupava e o
    que passa a ocupar. Criar, editar e regerar em sequencia nao descontam
    duas vezes, e mudar a tonelada na edicao ajusta a barra.
  * cancelado nao ocupa saldo: cancelar devolve, reabrir desconta de novo.
    Excluir devolve.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from ..models import Agendamento, AgendamentoItem, BaixaPedido, Pedido

STATUS_QUE_NAO_OCUPA = {"Cancelado"}


def _numero(texto) -> str:
    """'040947' e '40947' sao o mesmo pedido."""
    return str(texto or "").strip().lstrip("0")


def _produto(texto) -> str:
    return " ".join(str(texto or "").upper().split())


def resolver_pedido(
    db: Session,
    pedido_id=None,
    contrato="",
    produto="",
    *,
    reservado: dict | None = None,
    considerar_usadas: bool = True,
    pedidos: list | None = None,
) -> Pedido | None:
    """O pedido de um item: pelo id quando vem, senao pelo numero + produto."""
    if pedido_id:
        pedido = db.get(Pedido, pedido_id)
        if pedido is not None:
            return pedido

    numero, nome = _numero(contrato), _produto(produto)
    if not numero or not nome:
        return None
    lista = pedidos if pedidos is not None else db.query(Pedido).all()
    candidatos = [p for p in lista if _numero(p.contrato) == numero and _produto(p.produto) == nome]
    if not candidatos:
        return None

    reservado = reservado or {}

    def saldo(p: Pedido) -> float:
        usado = (p.toneladas_usadas or 0.0) if considerar_usadas else 0.0
        return (p.toneladas_total or 0.0) - usado - reservado.get(p.id, 0.0)

    # Mais saldo primeiro; empate, a linha mais antiga.
    return max(candidatos, key=lambda p: (saldo(p), -p.id))


def uso_por_pedido(agendamento: Agendamento) -> dict[int, float]:
    """Quanto o agendamento ocupa de cada pedido, pelos vinculos gravados."""
    uso: dict[int, float] = defaultdict(float)
    if agendamento.status in STATUS_QUE_NAO_OCUPA:
        return uso
    for item in agendamento.itens:
        if item.pedido_ref_id:
            uso[item.pedido_ref_id] += float(item.toneladas or 0)
    return uso


def aplicar_diferenca(db: Session, antes: dict, depois: dict) -> None:
    """Move a barra de cada pedido pela diferenca, sem sair de 0..total."""
    for pedido_id in set(antes) | set(depois):
        delta = depois.get(pedido_id, 0.0) - antes.get(pedido_id, 0.0)
        if abs(delta) < 1e-9:
            continue
        pedido = db.get(Pedido, pedido_id)
        if pedido is None:
            continue
        novo = (pedido.toneladas_usadas or 0.0) + delta
        pedido.toneladas_usadas = min(pedido.toneladas_total or 0.0, max(0.0, novo))


def montar_itens(db: Session, itens: list[dict], anteriores=()) -> list[AgendamentoItem]:
    """Itens com o vinculo ao pedido resolvido.

    `itens` sao dicts com pedido (o numero), cliente, produto, cidade,
    embalagem, toneladas e, quando a tela manda, pedido_id. Na edicao, item
    sem id herda o vinculo do item anterior de mesmo numero + produto.
    """
    herdado = {
        (_numero(i.pedido), _produto(i.produto)): i.pedido_ref_id
        for i in anteriores if i.pedido_ref_id
    }
    reservado: dict[int, float] = defaultdict(float)
    novos = []
    for it in itens:
        toneladas = float(it.get("toneladas") or 0)
        numero, produto = it.get("pedido") or "", it.get("produto") or ""
        pedido_id = it.get("pedido_id") or herdado.get((_numero(numero), _produto(produto)))
        pedido = resolver_pedido(db, pedido_id, numero, produto, reservado=reservado)
        if pedido is not None:
            reservado[pedido.id] += toneladas
        novos.append(AgendamentoItem(
            pedido=numero,
            cliente=it.get("cliente") or "",
            produto=produto,
            cidade=it.get("cidade") or "",
            embalagem=it.get("embalagem") or "",
            toneladas=toneladas,
            pedido_ref_id=pedido.id if pedido is not None else None,
        ))
    return novos


def gravar_itens(db: Session, agendamento: Agendamento, itens: list[dict]) -> None:
    """Troca os itens do agendamento e acerta a barra pela diferenca."""
    antes = uso_por_pedido(agendamento)
    agendamento.itens = montar_itens(db, itens, list(agendamento.itens))
    aplicar_diferenca(db, antes, uso_por_pedido(agendamento))


def mudar_status(db: Session, agendamento: Agendamento, status: str) -> None:
    antes = uso_por_pedido(agendamento)
    agendamento.status = status
    aplicar_diferenca(db, antes, uso_por_pedido(agendamento))


def liberar(db: Session, agendamento: Agendamento) -> None:
    """Antes de excluir: devolve o que o agendamento ocupava."""
    aplicar_diferenca(db, uso_por_pedido(agendamento), {})


def conciliar(db: Session, aplicar: bool = False) -> dict:
    """Recalcula a barra de todos os pedidos a partir dos agendamentos.

    Liga os itens antigos que ficaram sem vinculo (numero + produto, os mais
    antigos primeiro) e compara o que cada pedido deveria ter usado com o
    que a barra mostra. Sem `aplicar`, so mostra - nada e gravado.
    """
    pedidos = db.query(Pedido).all()
    agendamentos = db.query(Agendamento).order_by(Agendamento.created_at.asc(), Agendamento.id.asc()).all()

    esperado: dict[int, float] = defaultdict(float)
    reservado: dict[int, float] = defaultdict(float)
    # Baixa manual tambem ocupa saldo: a conciliacao nao pode apagar.
    for pedido_id, toneladas in db.query(BaixaPedido.pedido_id, BaixaPedido.toneladas).all():
        esperado[pedido_id] += float(toneladas or 0)
        reservado[pedido_id] += float(toneladas or 0)
    ligar = []
    for agendamento in agendamentos:
        ocupa = agendamento.status not in STATUS_QUE_NAO_OCUPA
        for item in agendamento.itens:
            pedido_id = item.pedido_ref_id
            if not pedido_id:
                pedido = resolver_pedido(
                    db, None, item.pedido, item.produto,
                    reservado=reservado, considerar_usadas=False, pedidos=pedidos,
                )
                if pedido is not None:
                    pedido_id = pedido.id
                    ligar.append((item, pedido_id))
            if pedido_id and ocupa:
                esperado[pedido_id] += float(item.toneladas or 0)
                reservado[pedido_id] += float(item.toneladas or 0)

    mudancas = []
    for pedido in sorted(pedidos, key=lambda p: (p.contrato or "", p.id)):
        correto = round(min(pedido.toneladas_total or 0.0, esperado.get(pedido.id, 0.0)), 4)
        atual = round(pedido.toneladas_usadas or 0.0, 4)
        if abs(correto - atual) > 0.001:
            mudancas.append({
                "pedido_id": pedido.id,
                "contrato": pedido.contrato,
                "cliente": pedido.cliente,
                "produto": pedido.produto,
                "toneladas_total": pedido.toneladas_total,
                "barra_atual": atual,
                "barra_correta": correto,
            })
            if aplicar:
                pedido.toneladas_usadas = correto

    if aplicar:
        for item, pedido_id in ligar:
            item.pedido_ref_id = pedido_id
        db.commit()

    return {"aplicado": aplicar, "mudancas": mudancas, "itens_sem_vinculo_ligados": len(ligar)}
