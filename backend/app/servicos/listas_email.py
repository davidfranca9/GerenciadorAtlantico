"""Listas de e-mail do sistema: pra quem vai cada envio.

Antes ficavam fixas no codigo e trocar um endereco (o luan.santos que deixou
de existir na Fertimaxi) pedia deploy. Agora ficam no banco e se editam em
Configuracoes; enquanto ninguem mexe, vale o padrao daqui.
"""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import ListaEmail

LISTAS: dict[str, dict] = {
    "fertimaxi": {
        "nome": "Fertimaxi",
        "uso": "Autorização de agendamento pela tela de Contratos e pela Ordem de Coleta, e os e-mails de inclusão e substituição de motorista.",
        "padrao": ["agendamento@fertimaxi.com.br", "paulo.moura@fertimaxi.com.br"],
    },
    "fertimaxi_novo_agendamento": {
        "nome": "Fertimaxi · Novo agendamento",
        "uso": "Autorização enviada pelo botão Novo agendamento da aba Agendamentos.",
        "padrao": ["atlanticofertlog.comercial@gmail.com", "paulo.moura@fertimaxi.com.br"],
    },
    "heringer": {
        "nome": "Heringer",
        "uso": "Ordem de coleta e e-mails de inclusão e substituição de motorista da Heringer.",
        "padrao": ["expedicao.candeias@heringer.com.br", "faturamento.candeias@heringer.com.br"],
    },
    "abastecimento": {
        "nome": "Autorização de abastecimento",
        "uso": "Envio da autorização de abastecimento, na hora ou agendado.",
        "padrao": ["davilucassouzaribeiro@gmail.com", "marvidacaixa503@gmail.com", "crispinianocrys@gmail.com"],
    },
}

EMAIL_VALIDO = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[a-z]{2,}$")


class ListaInvalida(ValueError):
    pass


def _chave_conhecida(chave: str) -> dict:
    if chave not in LISTAS:
        raise KeyError(chave)
    return LISTAS[chave]


def limpar(emails: list[str]) -> list[str]:
    """Minusculo, sem espaco e sem repetir. Endereco invalido barra tudo."""
    limpos: list[str] = []
    invalidos: list[str] = []
    for bruto in emails or []:
        email = str(bruto or "").strip().lower()
        if not email:
            continue
        if not EMAIL_VALIDO.match(email):
            invalidos.append(str(bruto).strip())
        elif email not in limpos:
            limpos.append(email)
    if invalidos:
        raise ListaInvalida(f"E-mail inválido: {', '.join(invalidos)}")
    if not limpos:
        raise ListaInvalida("A lista precisa de pelo menos um e-mail.")
    return limpos


def destinatarios(db: Session, chave: str) -> list[str]:
    definicao = _chave_conhecida(chave)
    salva = db.get(ListaEmail, chave)
    emails = [e for e in (salva.emails.splitlines() if salva else []) if e.strip()]
    return emails or list(definicao["padrao"])


def _para_tela(db: Session, chave: str) -> dict:
    definicao = LISTAS[chave]
    salva = db.get(ListaEmail, chave)
    return {
        "chave": chave,
        "nome": definicao["nome"],
        "uso": definicao["uso"],
        "emails": destinatarios(db, chave),
        "padrao": list(definicao["padrao"]),
        "personalizada": salva is not None,
        "atualizado_em": salva.atualizado_em if salva else None,
        "atualizado_por": salva.atualizado_por if salva else "",
    }


def listar(db: Session) -> list[dict]:
    return [_para_tela(db, chave) for chave in LISTAS]


def salvar(db: Session, chave: str, emails: list[str], usuario: str = "") -> dict:
    _chave_conhecida(chave)
    limpos = limpar(emails)
    salva = db.get(ListaEmail, chave) or ListaEmail(chave=chave)
    salva.emails = "\n".join(limpos)
    salva.atualizado_em = datetime.utcnow()
    salva.atualizado_por = usuario or ""
    db.add(salva)
    db.commit()
    return _para_tela(db, chave)


def restaurar(db: Session, chave: str) -> dict:
    """Volta pra lista padrao."""
    _chave_conhecida(chave)
    salva = db.get(ListaEmail, chave)
    if salva is not None:
        db.delete(salva)
        db.commit()
    return _para_tela(db, chave)
