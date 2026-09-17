"""E-mails de inclusao e substituicao de motorista num agendamento.

INCLUSAO: o agendamento foi pedido a fabrica sem motorista - o e-mail de
autorizacao saiu so com cliente e pedido. Quando o motorista e definido,
um e-mail NOVO pede a inclusao das placas.

SUBSTITUICAO: o agendamento ja tinha motorista e ele muda. Um e-mail NOVO
avisa a troca, dizendo quem sai e quem entra.

Nos dois, quem opera escreve o recado (a tela traz um texto pronto) e o
sistema acrescenta as tabelas do motorista e dos pedidos - a fabrica nao
depende do texto estar completo.

Modo teste: com settings.emails_motorista_em_teste ligado (ou teste=True
na chamada), o e-mail vai so pro endereco de teste, com [TESTE] no assunto
e um aviso de pra quem iria de verdade.
"""
from __future__ import annotations

import html
import re

from ..config import settings

TIPOS = {
    "inclusao": "INCLUSÃO DE PLACAS",
    "substituicao": "SUBSTITUIÇÃO DE MOTORISTA",
}

# Texto pronto de cada tipo. A tela preenche os mesmos marcadores, entao o
# texto que a pessoa ve e o mesmo que sai quando ela nao mexe.
MODELOS_MENSAGEM = {
    "inclusao": (
        "Prezados,\n\n"
        "Solicitamos, por gentileza, a inclusão das placas do motorista abaixo no agendamento "
        "do(s) pedido(s) {pedidos}{data_carregamento}.\n\n"
        "Ficamos no aguardo da confirmação."
    ),
    "substituicao": (
        "Prezados,\n\n"
        "Informamos a substituição do motorista no agendamento do(s) pedido(s) {pedidos}: "
        "sai {motorista_anterior} e entra o motorista abaixo.\n\n"
        "Por gentileza, atualizem a autorização de carregamento. Ficamos no aguardo da confirmação."
    ),
}

_TD = "border:1px solid #cfd8d3;padding:5px 10px;font-size:13px"
_TD_ROTULO = _TD + ";background:#f3f6f4;font-weight:bold"
_TH = _TD + ";background:#e3ece7;text-align:left"


def destinatarios_da_fabrica(supplier: str, db=None) -> list[str]:
    """A lista de cada fabrica - a mesma dos outros e-mails de agendamento,
    editavel em Configuracoes. Sem banco, a lista padrao."""
    from . import listas_email

    chave = "heringer" if (supplier or "").strip().lower() == "heringer" else "fertimaxi"
    if db is None:
        return list(listas_email.LISTAS[chave]["padrao"])
    return listas_email.destinatarios(db, chave)


def destino(reais: list[str], teste: bool) -> list[str]:
    """Pra quem o e-mail vai de fato.

    Em teste, so pro endereco de teste. A propria conta que envia recebe
    copia: o e-mail fica na caixa do sistema, e da pra conferir que saiu.
    """
    para = [settings.email_teste_fabrica] if teste else list(reais)
    if settings.gmail_sender_email and settings.gmail_sender_email not in para:
        para.append(settings.gmail_sender_email)
    return para


def _campo(item, nome):
    return item.get(nome) if isinstance(item, dict) else getattr(item, nome, "")


def numeros_dos_pedidos(itens) -> str:
    vistos: list[str] = []
    for item in itens:
        numero = str(_campo(item, "pedido") or "").strip()
        if numero and numero not in vistos:
            vistos.append(numero)
    return " / ".join(vistos) or "s/nº"


def assunto_padrao(tipo: str, motorista: str, itens) -> str:
    return f"{TIPOS[tipo]}: {(motorista or '').strip()} - Nº {numeros_dos_pedidos(itens)}"


def mensagem_padrao(tipo: str, itens, data_carregamento: str = "", motorista_anterior: str = "") -> str:
    data = f", com carregamento previsto para {data_carregamento}" if (data_carregamento or "").strip() else ""
    return (
        MODELOS_MENSAGEM[tipo]
        .replace("{pedidos}", numeros_dos_pedidos(itens))
        .replace("{data_carregamento}", data)
        .replace("{motorista_anterior}", (motorista_anterior or "").strip() or "o motorista anterior")
    )


def _cpf(valor) -> str:
    digitos = re.sub(r"\D", "", str(valor or ""))
    if len(digitos) != 11:
        return str(valor or "").strip()
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def _placa(valor) -> str:
    limpa = re.sub(r"[^A-Za-z0-9]", "", str(valor or "")).upper()
    return f"{limpa[:3]}-{limpa[3:]}" if len(limpa) == 7 else str(valor or "").strip().upper()


def _toneladas(valor) -> str:
    try:
        numero = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return str(valor or "")
    texto = f"{numero:.3f}".rstrip("0").rstrip(".")
    return f"{texto.replace('.', ',')} t"


def dados_do_motorista(motorista: dict) -> list[tuple[str, str]]:
    return [
        ("Motorista", (motorista.get("nome") or "").strip()),
        ("CPF", _cpf(motorista.get("cpf"))),
        ("CNH", (motorista.get("cnh") or "").strip()),
        ("Telefone", (motorista.get("fone") or "").strip()),
        ("Placa do cavalo", _placa(motorista.get("placa1"))),
        ("Placa da carreta 1", _placa(motorista.get("placa2"))),
        ("Placa da carreta 2", _placa(motorista.get("placa3"))),
        ("Modelo do veículo", (motorista.get("modelo") or "").strip().upper()),
    ]


def _tabela_rotulada(titulo: str, linhas: list[tuple[str, str]]) -> str:
    linhas = [(rotulo, valor) for rotulo, valor in linhas if str(valor or "").strip()]
    if not linhas:
        return ""
    corpo = "".join(
        f'<tr><td style="{_TD_ROTULO}">{html.escape(rotulo)}</td><td style="{_TD}">{html.escape(valor)}</td></tr>'
        for rotulo, valor in linhas
    )
    return f'<p style="margin:18px 0 6px"><b>{html.escape(titulo)}</b></p><table style="border-collapse:collapse">{corpo}</table>'


def montar_corpo(
    tipo: str,
    mensagem: str,
    motorista: dict,
    itens,
    anterior: dict | None = None,
    iria_para: list[str] | None = None,
) -> str:
    """HTML do e-mail: aviso de teste (se for), o recado, as tabelas e a assinatura."""
    partes = []
    if iria_para is not None:
        partes.append(
            '<p style="padding:8px 12px;background:#fff4d6;border:1px solid #e0b000">'
            f"<b>E-mail de teste.</b> Em produção iria para: {html.escape(', '.join(iria_para))}</p>"
        )
    for paragrafo in re.split(r"\n\s*\n", (mensagem or "").strip()):
        if paragrafo.strip():
            partes.append("<p>" + html.escape(paragrafo.strip()).replace("\n", "<br>") + "</p>")

    partes.append(_tabela_rotulada(
        "Motorista a incluir" if tipo == "inclusao" else "Novo motorista",
        dados_do_motorista(motorista),
    ))
    if tipo == "substituicao" and anterior:
        partes.append(_tabela_rotulada("Motorista que sai", dados_do_motorista(anterior)))

    cabecalho = "".join(f'<th style="{_TH}">{c}</th>' for c in ("Pedido", "Cliente", "Produto", "Embalagem", "Toneladas", "Cidade"))
    linhas = ""
    for item in itens:
        valores = [
            _campo(item, "pedido"), _campo(item, "cliente"), _campo(item, "produto"),
            _campo(item, "embalagem"), _toneladas(_campo(item, "toneladas")), _campo(item, "cidade"),
        ]
        linhas += "<tr>" + "".join(f'<td style="{_TD}">{html.escape(str(v or "-"))}</td>' for v in valores) + "</tr>"
    partes.append(
        '<p style="margin:18px 0 6px"><b>Pedidos</b></p>'
        f'<table style="border-collapse:collapse"><tr>{cabecalho}</tr>{linhas}</table>'
    )
    partes.append('<img src="cid:assinatura_fertlog" alt="Atlântico Fertlog" style="max-width:420px;margin-top:18px">')
    return "\n".join(p for p in partes if p)
