"""Recuperar pedidos apagados sem querer, relendo os PDFs do WhatsApp.

A exclusao de pedido apaga a linha direto, sem lixeira. Mas o PDF que o
cliente mandou fica guardado na mensagem do WhatsApp, entao da pra ler de
novo e recriar o que sumiu - e, como a leitura e a mesma do recebimento, o
pedido volta igual ao que era.

Duas coisas tornam isso seguro de rodar:

- pedido que ainda existe nao e recriado. A conferencia e por numero +
  produto + cliente, contando quantos de cada ja estao la: PDF com duas
  linhas do mesmo produto recria so o que falta;
- sem `aplicar`, nada e gravado - a tela mostra antes o que entraria.

Depois de gravar, a conciliacao refaz a barra de cada pedido pelos
agendamentos: o saldo usado nao volta zerado e os itens antigos voltam a
apontar pro pedido certo.
"""
from __future__ import annotations

import os
import tempfile
import unicodedata
from collections import Counter

from sqlalchemy.orm import Session

from ..models import Agendamento, AgendamentoItem, Cidade, Pedido, WhatsAppMensagem
from . import ocr, saldo_pedidos
from ..config import settings


def _chave(contrato, produto, cliente) -> tuple[str, str, str]:
    """Identidade do produto do pedido, sem acento e sem caixa: o mesmo PDF
    lido duas vezes tem que dar a mesma chave."""
    def limpar(texto) -> str:
        bruto = unicodedata.normalize("NFKD", str(texto or ""))
        return "".join(c for c in bruto if not unicodedata.combining(c)).strip().upper()

    return (limpar(contrato), limpar(produto), limpar(cliente))


def _produtos_do_pdf(conteudo: bytes, cidades: list[tuple[str, str]]) -> tuple[list[dict], dict]:
    """Le o PDF guardado na mensagem com o mesmo parser do recebimento."""
    caminho = None
    try:
        fd, caminho = tempfile.mkstemp(suffix=".pdf")
        with os.fdopen(fd, "wb") as arquivo:
            arquivo.write(conteudo)
        resultado = ocr.parse_pdf_fields(caminho, cidades)
        return list(resultado.get("produtos") or []), resultado
    finally:
        if caminho:
            try:
                os.remove(caminho)
            except OSError:
                pass


def _pedidos_citados_em_agendamentos(db: Session) -> list[dict]:
    """Pedidos que os agendamentos citam e que nao existem mais.

    Serve de conferencia: o que foi agendado deixou rastro no item, entao se
    algum pedido continuar faltando depois da recuperacao, ele aparece aqui -
    veio por outro caminho que nao o WhatsApp.
    """
    existentes = {_chave(p.contrato, p.produto, p.cliente) for p in db.query(Pedido).all()}
    faltando: dict[tuple, dict] = {}
    for item in db.query(AgendamentoItem).join(Agendamento).all():
        chave = _chave(item.pedido, item.produto, item.cliente)
        if not any(chave) or chave in existentes or chave in faltando:
            continue
        faltando[chave] = {
            "pedido": item.pedido, "produto": item.produto, "cliente": item.cliente,
            "cidade": item.cidade, "toneladas": float(item.toneladas or 0),
        }
    return list(faltando.values())


def recuperar(db: Session, *, aplicar: bool = False) -> dict:
    """Relê os PDFs recebidos no WhatsApp e recria o que foi apagado."""
    cidades = [(c.nome, c.uf) for c in db.query(Cidade).all()]
    # Conta quantos de cada produto ja existem: PDF com duas linhas iguais
    # recria so a que falta.
    ja_tem: Counter = Counter(_chave(p.contrato, p.produto, p.cliente) for p in db.query(Pedido).all())

    mensagens = (
        db.query(WhatsAppMensagem)
        .filter(
            WhatsAppMensagem.direcao == "entrada",
            WhatsAppMensagem.midia.isnot(None),
            WhatsAppMensagem.mime_type == "application/pdf",
        )
        .order_by(WhatsAppMensagem.id.asc())
        .all()
    )

    recuperados: list[dict] = []
    ja_estavam = 0
    ilegiveis: list[dict] = []
    novos: list[Pedido] = []

    for mensagem in mensagens:
        try:
            produtos, resultado = _produtos_do_pdf(mensagem.midia, cidades)
        except Exception as exc:  # PDF corrompido ou formato que nao lemos
            ilegiveis.append({
                "mensagem_id": mensagem.id, "numero": mensagem.numero,
                "arquivo": mensagem.nome_arquivo or "", "erro": f"{type(exc).__name__}: {exc}"[:200],
            })
            continue

        for item in produtos:
            toneladas = float(item.get("toneladas") or 0)
            if toneladas <= 0:
                continue
            chave = _chave(item.get("contrato"), item.get("produto"), item.get("cliente"))
            if ja_tem[chave] > 0:
                ja_tem[chave] -= 1
                ja_estavam += 1
                continue
            pedido = Pedido(
                contrato=str(item.get("contrato") or ""),
                produto=str(item.get("produto") or ""),
                embalagem=str(item.get("embalagem") or ""),
                cidade=str(item.get("cidade") or ""),
                cliente=str(item.get("cliente") or ""),
                supplier=str(item.get("supplier") or "") or settings.whatsapp_supplier_padrao or "AFL",
                cidades_candidatas="" if item.get("cidade") else ocr.candidatas_do_item(resultado, item),
                toneladas_total=toneladas,
                toneladas_usadas=0,
                # A data de recebimento no WhatsApp e mais fiel que "agora":
                # o pedido volta pro lugar dele na lista, e nao como novo.
                created_at=mensagem.created_at or None,
            )
            novos.append(pedido)
            db.add(pedido)
            recuperados.append({
                "mensagem_id": mensagem.id, "numero": mensagem.numero,
                "recebido_em": mensagem.created_at.isoformat() if mensagem.created_at else None,
                "contrato": pedido.contrato, "produto": pedido.produto, "cliente": pedido.cliente,
                "cidade": pedido.cidade, "toneladas": toneladas,
            })

    conciliacao = None
    if novos:
        db.flush()
        # Pedido recriado volta com a barra zerada. A conciliacao refaz o uso
        # pelos agendamentos e religa os itens que ficaram orfaos.
        conciliacao = saldo_pedidos.conciliar(db, aplicar=aplicar)

    faltando = _pedidos_citados_em_agendamentos(db)

    if aplicar:
        db.commit()
    else:
        db.rollback()

    return {
        "aplicado": aplicar,
        "mensagens_lidas": len(mensagens),
        "recuperados": recuperados,
        "quantidade": len(recuperados),
        "ja_estavam": ja_estavam,
        "ilegiveis": ilegiveis,
        # Citados em agendamento e ainda sem pedido: vieram por outro caminho
        # (importados na tela, por exemplo) e o WhatsApp nao tem como trazer.
        "faltando_fora_do_whatsapp": faltando,
        "conciliacao": conciliacao,
    }
