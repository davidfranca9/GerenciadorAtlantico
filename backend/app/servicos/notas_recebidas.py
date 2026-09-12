"""Junta as NF-e que chegam por qualquer caminho num lugar so.

Sao duas fontes, e elas se completam:

    e-mail  - chega na hora, quando o fornecedor manda o anexo
    SEFAZ   - de hora em hora, pega o que ninguem mandou

A segunda existe porque a primeira falha: as fabricas nem sempre enviam.
A chave e unica na tabela, entao a mesma nota vinda pelos dois caminhos
nao vira duas.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..models import NotaFiscalRecebida, OperacaoFiscal
from . import nfe_xml

logger = logging.getLogger(__name__)


def guardar(db: Session, xml: str, origem: str) -> NotaFiscalRecebida | None:
    """Guarda uma NF-e, se ainda nao estiver guardada.

    XML ilegivel e ignorado sem quebrar a sincronizacao: numa leva de
    dezenas de documentos, um arquivo ruim nao pode derrubar o resto.
    """
    try:
        dados = nfe_xml.extrair_dados(xml.encode() if isinstance(xml, str) else xml)
    except Exception as exc:
        logger.info("XML ignorado na origem %s: %s", origem, str(exc)[:120])
        return None

    existente = (
        db.query(NotaFiscalRecebida)
        .filter(NotaFiscalRecebida.chave == dados["chave"])
        .one_or_none()
    )
    if existente is not None:
        # Ja conhecida. Se antes so tinhamos o resumo e agora veio o XML
        # completo, vale atualizar.
        if len(xml) > len(existente.xml or ""):
            existente.xml = xml
            db.commit()
        return existente

    nota = NotaFiscalRecebida(
        chave=dados["chave"],
        origem=origem,
        numero=dados["numero"],
        serie=dados["serie"],
        emissao=dados["emissao"],
        emitente_nome=dados["emitente_nome"][:255],
        destinatario_nome=dados["destinatario_nome"][:255],
        municipio_destino=dados["municipio_destino"][:120],
        uf_destino=dados["uf_destino"][:2],
        valor_nota=dados["valor_nota"],
        peso_bruto=dados["peso_bruto"],
        xml=xml,
    )
    db.add(nota)
    db.commit()
    return nota


def marcar_com_cte(db: Session, chave: str, numero_cte: str = "") -> None:
    """Registra que a nota ja virou CT-e, pra ela sair da fila."""
    nota = (
        db.query(NotaFiscalRecebida)
        .filter(NotaFiscalRecebida.chave == chave)
        .one_or_none()
    )
    if nota is None:
        return
    nota.tem_cte = True
    nota.cte_numero = numero_cte or nota.cte_numero
    db.commit()


def pendentes(db: Session, limite: int = 50) -> list[NotaFiscalRecebida]:
    """Notas que ainda nao viraram CT-e, das mais novas pras mais antigas.

    Considera tambem as operacoes fiscais ja registradas: uma nota pode ter
    virado CT-e antes desta tabela existir.
    """
    ja_usadas = {
        chave for (chave,) in db.query(OperacaoFiscal.chave_nfe)
        .filter(OperacaoFiscal.cod_conhecimento_bsoft != "").all()
    }
    consulta = (
        db.query(NotaFiscalRecebida)
        .filter(NotaFiscalRecebida.tem_cte.is_(False))
        .order_by(NotaFiscalRecebida.emissao.desc(), NotaFiscalRecebida.id.desc())
        .limit(limite * 2)
    )
    return [n for n in consulta.all() if n.chave not in ja_usadas][:limite]
