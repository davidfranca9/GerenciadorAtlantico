"""Respostas da fabrica aos e-mails de agendamento.

A fabrica responde em texto livre. Tres jeitos, lidos das respostas reais da
Fertimaxi:
- confirmou: "ok", "agendado para 22/09", ou so a tabela com a data;
- ainda nao confirmou: "Disponibilidade para 21/09, podemos confirmar?",
  "previsto para o dia 21/09, aguardamos os dados";
- problema: "pedido nao contem o produto", "precisamos da planilha",
  "esta enviando o mesmo agendamento".

So a confirmacao mexe no agendamento (data agendada + status Agendado). O
resto aparece na tela, pra quem opera decidir.

Ligacao com o agendamento, nessa ordem:
1. a resposta cita o Message-ID de um e-mail que saiu do agendamento;
2. e-mail que saiu antes do Message-ID ser guardado: o horario e o pedido
   do e-mail citado batem com a criacao de um agendamento so;
3. resposta a uma resposta nossa ("Re: ..."): a lista de e-mails anteriores
   (References) cita uma resposta da fabrica ja ligada;
4. ainda nessa situacao, sem a lista: a ultima resposta ja ligada com o
   mesmo assunto, ou a mesma conversa do Gmail ligada a um agendamento so.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Agendamento, AgendamentoEmail, RespostaFabrica
from . import saldo_pedidos

logger = logging.getLogger(__name__)

# Horario de Brasilia (sem horario de verao desde 2019): o que a fabrica cita.
FUSO_BRASILIA = timedelta(hours=-3)
CONFIRMADO_POR = "Fábrica, por e-mail"
STATUS_QUE_ACEITAM_CONFIRMACAO = {"Aguardando Agendamento", "Agendado"}

MESES = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7,
    "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}
MESES_CURTOS = {nome[:3]: numero for nome, numero in MESES.items()}

PROBLEMA = (
    # Negacao primeiro: "Nao confirmado agendamento, pedido bloqueado" tem
    # "confirmado" no meio e nao e confirmacao.
    "NAO CONFIRMAD", "NAO AGENDAD", "NAO FOI AGENDAD", "BLOQUEAD", "RECUSAD", "NEGAD",
    "NAO CONTEM", "NAO POSSUI", "SALDO INSUFICIENTE", "NAO TEM SALDO", "SEM SALDO", "CONSTA UM SALDO",
    "JANELAS", "PREENCHIDAS", "ENTRAR EM CONTATO", "CONTATO NOVAMENTE", "MESMO AGENDAMENTO",
    "ENCERRADO", "COM CORTE", "JA AGENDADO", "JA ESTA AGENDADO", "JA TEMOS", "IMPOSSIBILITAD",
    "PLANILHA", "VERIFICAR", "NAO SERA POSSIVEL", "NAO FOI POSSIVEL", "INDISPONIVEL",
    "SEM DISPONIBILIDADE", "CANCELAD", "AJUSTE", "NAO CONSEGUIMOS",
)
AGUARDANDO = (
    "?", "PREVISTO", "AGUARDANDO", "AGUARDAMOS", "DISPONIBILIDADE PARA", "PODEMOS CONFIRMAR",
    "FAVOR CONFIRMAR", "GENTILEZA CONFIRMAR", "PODE CONFIRMAR",
)
CONFIRMADO = ("CONFIRMADO", "AGENDADO", "CIENTE", "PLACA INCLUSA", "INCLUIDA", "INCLUSO")

# Onde comeca o que nao e a resposta em si: citacao do e-mail anterior e o
# rodape padrao da Fertimaxi.
CORTES = (
    r"\n\s*_{5,}", r"\n\s*-{5,}", r"\n\s*De: ", r"\n\s*From: ", r"\n\s*Em .{5,80} escreveu:",
    r"\n\s*On .{5,80} wrote:", r"Informamos que a partir de", r"\n\s*Atenciosamente",
)


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).upper()


def texto_da_resposta(corpo: str) -> str:
    """So o que a fabrica escreveu agora, sem citacao nem rodape."""
    texto = (corpo or "").replace("\r", "").replace("\xa0", " ")
    fim = len(texto)
    for corte in CORTES:
        achado = re.search(corte, texto)
        if achado and achado.start() < fim:
            fim = achado.start()
    linhas = [re.sub(r"[ \t]+", " ", linha).strip() for linha in texto[:fim].splitlines()]
    return "\n".join(linha for linha in linhas if linha)


def extrair_data(texto: str, referencia: date) -> str:
    """Primeira data do texto ("21/09", "21/09/2026", "22-set"), em dd/mm/aaaa."""
    normal = _normalizar(texto)
    achado = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", normal)
    if achado:
        dia, mes, ano = int(achado.group(1)), int(achado.group(2)), achado.group(3)
    else:
        achado = re.search(r"\b(\d{1,2})[-/ ](" + "|".join(MESES_CURTOS) + r")\b", normal)
        if not achado:
            return ""
        dia, mes, ano = int(achado.group(1)), MESES_CURTOS[achado.group(2)], None
    if not 1 <= mes <= 12:
        return ""
    if ano:
        ano = int(ano) + (2000 if len(ano) == 2 else 0)
    else:
        ano = referencia.year
        # "05/01" respondido em dezembro e do ano que vem.
        if (referencia - date(ano, mes, 1)).days > 180:
            ano += 1
    try:
        return date(ano, mes, dia).strftime("%d/%m/%Y")
    except ValueError:
        return ""


def classificar(texto: str, referencia: date) -> tuple[str, str]:
    """(tipo, data) de uma resposta: confirmado | aguardando | problema | outro."""
    normal = _normalizar(texto)
    data = extrair_data(texto, referencia)
    if any(p in normal for p in PROBLEMA):
        return "problema", data
    if any(p in normal for p in AGUARDANDO):
        return "aguardando", data
    if re.search(r"\bOK\b", normal) or any(p in normal for p in CONFIRMADO):
        return "confirmado", data
    # So a data e a tabela do agendamento, sem pergunta: e o que a fabrica
    # manda quando agenda ("22/09" + linha com placa e toneladas).
    if data:
        return "confirmado", data
    return "outro", ""


def ids_citados(*cabecalhos: str) -> list[str]:
    return re.findall(r"<[^<>\s]+>", " ".join(c or "" for c in cabecalhos))


def citacao(corpo: str) -> tuple[datetime | None, str]:
    """Horario (UTC) e assunto do e-mail citado logo abaixo da resposta."""
    texto = (corpo or "").replace("\r", "").replace("\xa0", " ")
    achado = re.search(
        r"(?:Enviad[ao]|Data|Sent|Date):\s*(.{0,80}?)\n(?:.*\n){0,4}?\s*(?:Assunto|Subject):\s*([^\n]+)",
        texto,
    )
    if not achado:
        return None, ""
    quando = re.search(r"(\d{1,2}) DE (\w+) DE (\d{4})\D{0,5}(\d{1,2}):(\d{2})", _normalizar(achado.group(1)))
    assunto = achado.group(2).strip()
    if not quando or quando.group(2) not in MESES:
        return None, assunto
    local = datetime(int(quando.group(3)), MESES[quando.group(2)], int(quando.group(1)),
                     int(quando.group(4)), int(quando.group(5)))
    return local - FUSO_BRASILIA, assunto


def _numeros_de_pedido(assunto: str) -> set[str]:
    depois = re.split(r"N[º°O]\.?\s*", _normalizar(assunto), maxsplit=1)
    if len(depois) < 2:
        return set()
    return {n.lstrip("0") for n in re.findall(r"\d{4,}", depois[1])}


def _eh_resposta(assunto: str) -> bool:
    return bool(re.match(r"\s*(RE|RES|ENC|FW|FWD|TR)\s*:", _normalizar(assunto)))


def _pelo_message_id(db: Session, ids: list[str]) -> list[Agendamento]:
    achados = []
    for message_id in ids:
        for agendamento in db.query(Agendamento).filter(Agendamento.email_message_ids.contains(message_id)).all():
            if message_id in (agendamento.email_message_ids or "").split() and agendamento not in achados:
                achados.append(agendamento)
    return achados


def _pelo_horario(db: Session, enviado_em: datetime, assunto_citado: str) -> list[Agendamento]:
    """Agendamento criado (ou e-mail de motorista mandado) no minuto citado,
    com o pedido do assunto. O minuto citado nao tem segundos: vale o mais
    perto do meio dele, e empate de verdade fica sem ligacao."""
    numeros = _numeros_de_pedido(assunto_citado)
    if not numeros or _eh_resposta(assunto_citado):
        return []
    meio = enviado_em + timedelta(seconds=30)
    janela = (enviado_em - timedelta(seconds=60), enviado_em + timedelta(seconds=120))

    candidatos: dict[int, tuple[float, Agendamento]] = {}
    horarios = [(a.created_at, a) for a in db.query(Agendamento).filter(Agendamento.created_at.between(*janela)).all()]
    horarios += [
        (e.created_at, e.agendamento)
        for e in db.query(AgendamentoEmail).filter(AgendamentoEmail.created_at.between(*janela)).all()
    ]
    for quando, agendamento in horarios:
        if agendamento is None:
            continue
        pedidos = {(i.pedido or "").lstrip("0") for i in agendamento.itens}
        if not pedidos & numeros:
            continue
        distancia = abs((quando - meio).total_seconds())
        if agendamento.id not in candidatos or distancia < candidatos[agendamento.id][0]:
            candidatos[agendamento.id] = (distancia, agendamento)
    ordem = sorted(candidatos.values(), key=lambda par: par[0])
    if not ordem:
        return []
    if len(ordem) > 1 and ordem[1][0] - ordem[0][0] < 15:
        return []
    return [ordem[0][1]]


def _pelas_respostas_anteriores(db: Session, ids: list[str]) -> list[Agendamento]:
    """References cita a resposta da fabrica que respondemos."""
    if not ids:
        return []
    anteriores = db.query(RespostaFabrica).filter(
        RespostaFabrica.message_id.in_(ids), RespostaFabrica.agendamento_id.isnot(None)
    ).all()
    agendamento_ids = {r.agendamento_id for r in anteriores}
    return [db.get(Agendamento, agendamento_ids.pop())] if len(agendamento_ids) == 1 else []


def _assunto_base(assunto: str) -> str:
    base = _normalizar(assunto)
    while True:
        sem = re.sub(r"^\s*(RE|RES|ENC|FW|FWD|TR)\s*:\s*", "", base)
        if sem == base:
            return re.sub(r"\s+", " ", base).strip()
        base = sem


def _pelo_assunto(db: Session, assunto_citado: str, antes_de: datetime) -> list[Agendamento]:
    """Respondemos a fabrica ("Re: ...") e ela respondeu de novo: vale a
    ultima resposta dela, ja ligada, com o mesmo assunto."""
    base = _assunto_base(assunto_citado)
    if not base or not _numeros_de_pedido(base):
        return []
    anteriores = (
        db.query(RespostaFabrica)
        .filter(RespostaFabrica.agendamento_id.isnot(None), RespostaFabrica.recebido_em <= antes_de,
                RespostaFabrica.recebido_em >= antes_de - timedelta(days=3))
        .order_by(RespostaFabrica.recebido_em.desc())
        .all()
    )
    for anterior in anteriores:
        if _assunto_base(anterior.assunto) == base:
            return [anterior.agendamento]
    return []


def _pela_conversa(db: Session, conversa: str) -> list[Agendamento]:
    if not conversa:
        return []
    ids = {
        r.agendamento_id
        for r in db.query(RespostaFabrica).filter(RespostaFabrica.conversa == conversa, RespostaFabrica.agendamento_id.isnot(None))
    }
    if len(ids) != 1:
        return []
    return [db.get(Agendamento, ids.pop())]


def ligar(db: Session, mensagem: dict) -> tuple[Agendamento | None, str]:
    ids = ids_citados(mensagem.get("in_reply_to", ""), mensagem.get("references", ""))
    por_id = _pelo_message_id(db, ids)
    if len(por_id) == 1:
        return por_id[0], "resposta"
    enviado_em, assunto_citado = citacao(mensagem.get("texto", ""))
    if enviado_em is not None:
        pelo_horario = _pelo_horario(db, enviado_em, assunto_citado)
        if pelo_horario:
            return pelo_horario[0], "horario"
    pelas_anteriores = _pelas_respostas_anteriores(db, ids)
    if pelas_anteriores:
        return pelas_anteriores[0], "resposta"
    if enviado_em is not None and _eh_resposta(assunto_citado):
        pelo_assunto = _pelo_assunto(db, assunto_citado, enviado_em)
        if pelo_assunto:
            return pelo_assunto[0], "assunto"
    pela_conversa = _pela_conversa(db, mensagem.get("conversa", ""))
    if pela_conversa:
        return pela_conversa[0], "conversa"
    return None, ""


def _data_proposta_antes(db: Session, agendamento: Agendamento, recebido_em: datetime | None) -> str:
    """Resposta "ok" sem data: vale a data que a fabrica tinha proposto antes."""
    anteriores = [
        r for r in agendamento.respostas
        if r.data and r.tipo in ("aguardando", "confirmado") and (recebido_em is None or (r.recebido_em or recebido_em) <= recebido_em)
    ]
    return anteriores[-1].data if anteriores else ""


def _aplicar(db: Session, agendamento: Agendamento, resposta: RespostaFabrica) -> bool:
    if agendamento.status not in STATUS_QUE_ACEITAM_CONFIRMACAO or not resposta.data:
        return False
    # Confirmacao feita depois (na tela, por alguem) vale mais que o e-mail antigo.
    if agendamento.agendamento_confirmado_em and resposta.recebido_em and agendamento.agendamento_confirmado_em > resposta.recebido_em:
        return False
    agendamento.data_agendada = resposta.data
    agendamento.agendamento_confirmado_em = resposta.recebido_em or datetime.utcnow()
    agendamento.agendamento_confirmado_por = CONFIRMADO_POR
    if agendamento.status != "Agendado":
        saldo_pedidos.mudar_status(db, agendamento, "Agendado")
    agendamento.updated_at = datetime.utcnow()
    return True


def processar(db: Session, mensagens: list[dict]) -> list[dict]:
    """Grava e aplica as respostas (da mais antiga pra mais nova). Quem chama
    decide o commit - a previa desfaz tudo."""
    resumo = []
    ordenadas = sorted(mensagens, key=lambda m: m.get("recebido_em") or datetime.min)
    for mensagem in ordenadas:
        message_id = (mensagem.get("message_id") or "").strip()
        if not message_id or db.query(RespostaFabrica).filter(RespostaFabrica.message_id == message_id).first():
            continue
        recebido_em = mensagem.get("recebido_em")
        referencia = (recebido_em or datetime.utcnow()).date()
        texto = texto_da_resposta(mensagem.get("texto", ""))
        tipo, data = classificar(texto, referencia)
        agendamento, como = ligar(db, mensagem)

        resposta = RespostaFabrica(
            message_id=message_id[:500], agendamento_id=agendamento.id if agendamento else None,
            conversa=(mensagem.get("conversa") or "")[:40], recebido_em=recebido_em,
            remetente=(mensagem.get("remetente") or "")[:255], assunto=(mensagem.get("assunto") or "")[:500],
            texto=texto[:4000], tipo=tipo, data=data, como_ligou=como,
        )
        db.add(resposta)
        db.flush()
        if agendamento is not None:
            db.refresh(agendamento)
            if tipo == "confirmado" and not resposta.data:
                resposta.data = _data_proposta_antes(db, agendamento, recebido_em)
            if tipo == "confirmado":
                resposta.aplicada = _aplicar(db, agendamento, resposta)
            db.flush()

        resumo.append({
            "recebido_em": recebido_em, "assunto": resposta.assunto, "tipo": tipo, "data": resposta.data,
            "agendamento_id": resposta.agendamento_id, "como_ligou": como, "aplicada": resposta.aplicada,
            "texto": texto[:200],
        })
    return resumo


def busca_padrao(dias: int) -> str:
    """Respostas aos e-mails de agendamento, menos o que a propria conta mandou
    e aviso de e-mail nao entregue."""
    remetente = settings.gmail_sender_email or "me"
    return (
        f"newer_than:{int(dias)}d -from:{remetente} -from:postmaster -from:mailer-daemon "
        f"subject:(AGENDAMENTO OR PLACAS OR MOTORISTA)"
    )


def ler_da_caixa(db: Session, dias: int = 3, aplicar: bool = True) -> dict:
    """Le as respostas novas da caixa. Sem `aplicar`, so mostra o que faria."""
    from . import email_inbox

    ja_lidas = {m for (m,) in db.query(RespostaFabrica.message_id).all()}
    mensagens = email_inbox.mensagens_para_ler(busca_padrao(dias), ja_lidas)
    try:
        resumo = processar(db, mensagens)
        if aplicar:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    return {
        "lidas": len(resumo),
        "ligadas": sum(1 for r in resumo if r["agendamento_id"]),
        "aplicadas": sum(1 for r in resumo if r["aplicada"]),
        "respostas": resumo,
        "aplicado": aplicar,
    }


def registrar_envio(agendamento: Agendamento, message_id: str | None) -> None:
    """Guarda o Message-ID de um e-mail que saiu do agendamento."""
    if not message_id or not isinstance(message_id, str):
        return
    atuais = (agendamento.email_message_ids or "").split()
    if message_id not in atuais:
        agendamento.email_message_ids = " ".join(atuais + [message_id])


def para_tela(resposta: RespostaFabrica) -> dict:
    return {
        "id": resposta.id,
        "recebido_em": resposta.recebido_em,
        "remetente": resposta.remetente,
        "tipo": resposta.tipo,
        "data": resposta.data,
        "texto": resposta.texto,
        "aplicada": resposta.aplicada,
    }
