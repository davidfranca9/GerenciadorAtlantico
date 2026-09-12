"""Casa a NF-e que chegou com o agendamento que a espera.

Ate aqui quem escolhia o agendamento na tela era a pessoa. Mas a nota ja
diz quase tudo: pra quem vai (destinatario), pra onde (municipio), o que e
(produto) e quanto pesa. O agendamento tem os mesmos campos nos itens. O
que este modulo faz e comparar os dois lados e, quando so um agendamento
encaixa, ligar os dois - sozinho.

A pontuacao e deliberadamente conservadora: casamento errado vira CT-e
errado, e CT-e errado vira cancelamento na SEFAZ. Na duvida, nao casa e
explica por que - a tela mostra o motivo e a pessoa decide.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

from sqlalchemy.orm import Session

from ..models import Agendamento, Cliente, NotaFiscalRecebida, OperacaoFiscal

# A partir de quanto o casamento e aceito, e quanta vantagem o primeiro
# colocado precisa ter sobre o segundo pra nao ser ambiguidade.
PONTUACAO_MINIMA = 50
VANTAGEM_MINIMA = 15

# Quantos dias pra cada lado a data do agendamento pode ficar da emissao
# da nota. A nota sai no dia do carregamento ou perto dele.
JANELA_DIAS = 10

PALAVRAS_VAZIAS = {"LTDA", "LTDA.", "ME", "EPP", "SA", "S.A.", "S/A", "EIRELI", "DE", "DA", "DO", "DOS", "DAS", "E", "&", "CIA", "COMERCIO", "INDUSTRIA"}


def _sem_acento(texto) -> str:
    limpo = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in limpo if not unicodedata.combining(c)).upper().strip()


def _so_digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def _palavras(texto) -> set:
    return {p for p in re.split(r"[^A-Z0-9]+", _sem_acento(texto)) if p and p not in PALAVRAS_VAZIAS and len(p) > 1}


def _cidade(texto) -> str:
    """'MONTES CLAROS - MG' e 'Montes Claros/MG' viram 'MONTES CLAROS'."""
    base = _sem_acento(texto)
    base = re.split(r"\s*[-/]\s*[A-Z]{2}\s*$", base)[0]
    return " ".join(base.split())


def _data(texto) -> date | None:
    """Aceita dd/mm/aaaa (agendamento) e aaaa-mm-dd (nota)."""
    texto = str(texto or "").strip()[:10]
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def pontuar(nota: dict, agendamento: dict, cliente_por_doc: dict | None = None) -> tuple[int, list[str]]:
    """Pontua um agendamento contra a nota. Puro, pra testar sem banco.

    nota:        destinatario_doc, destinatario_nome, municipio_destino,
                 peso_kg, emissao
    agendamento: id, status, data, itens=[{cliente, cidade, toneladas}]
    cliente_por_doc: {digitos do CNPJ/CPF: nome do cliente no cadastro}
    """
    pontos = 0
    motivos: list[str] = []
    itens = agendamento.get("itens") or []

    # 1) O destinatario e um cliente cadastrado, e o agendamento e dele.
    doc = _so_digitos(nota.get("destinatario_doc"))
    nome_cadastro = (cliente_por_doc or {}).get(doc, "")
    clientes_do_agendamento = [_sem_acento(i.get("cliente")) for i in itens]
    if nome_cadastro and any(
        _sem_acento(nome_cadastro) in c or c in _sem_acento(nome_cadastro)
        for c in clientes_do_agendamento if c
    ):
        pontos += 50
        motivos.append(f"cliente {nome_cadastro} pelo CNPJ/CPF")
    else:
        # 2) Sem cadastro: o nome do destinatario parece com o do item.
        palavras_nota = _palavras(nota.get("destinatario_nome"))
        melhor = 0.0
        for c in clientes_do_agendamento:
            palavras_item = _palavras(c)
            if palavras_nota and palavras_item:
                comum = len(palavras_nota & palavras_item)
                melhor = max(melhor, comum / min(len(palavras_nota), len(palavras_item)))
        if melhor >= 0.5:
            pontos += 30
            motivos.append("nome do destinatario parecido com o cliente do agendamento")

    # 3) Mesmo municipio de destino.
    cidade_nota = _cidade(nota.get("municipio_destino"))
    if cidade_nota and any(_cidade(i.get("cidade")) == cidade_nota for i in itens):
        pontos += 25
        motivos.append(f"destino {cidade_nota.title()}")

    # 4) Peso proximo do total do agendamento.
    try:
        toneladas_nota = float(_so_digitos(str(nota.get("peso_kg") or "").split(".")[0]) or 0) / 1000
    except ValueError:
        toneladas_nota = 0.0
    toneladas_agendamento = sum(float(i.get("toneladas") or 0) for i in itens)
    if toneladas_nota and toneladas_agendamento:
        diferenca = abs(toneladas_nota - toneladas_agendamento)
        if diferenca <= 1:
            pontos += 15
            motivos.append(f"peso {toneladas_nota:g} t")
        elif diferenca <= 3:
            pontos += 5

    # 5) Data perto da emissao. Fora da janela, nem e candidato.
    emissao = _data(nota.get("emissao"))
    data_agendamento = _data(agendamento.get("data"))
    if emissao and data_agendamento:
        distancia = abs((emissao - data_agendamento).days)
        if distancia > JANELA_DIAS:
            return 0, [f"data do agendamento a {distancia} dias da nota"]
        if distancia == 0:
            pontos += 10
            motivos.append("mesmo dia")
        elif distancia <= 3:
            pontos += 5

    return pontos, motivos


def escolher(nota: dict, candidatos: list[dict], cliente_por_doc: dict | None = None) -> tuple[dict | None, str]:
    """Escolhe o agendamento, ou explica por que nao escolheu."""
    pontuados = []
    for agendamento in candidatos:
        pontos, motivos = pontuar(nota, agendamento, cliente_por_doc)
        if pontos > 0:
            pontuados.append((pontos, agendamento, motivos))
    if not pontuados:
        return None, "nenhum agendamento aberto parece com esta nota"

    pontuados.sort(key=lambda x: x[0], reverse=True)
    melhor, agendamento, motivos = pontuados[0]
    if melhor < PONTUACAO_MINIMA:
        return None, f"parecido com o agendamento #{agendamento['id']} ({', '.join(motivos)}), mas pouco pra ter certeza"
    if len(pontuados) > 1 and melhor - pontuados[1][0] < VANTAGEM_MINIMA:
        outros = ", ".join(f"#{a['id']}" for _, a, _ in pontuados[1:3])
        return None, f"mais de um agendamento encaixa (#{agendamento['id']} e {outros}): escolha na tela"
    return agendamento, ", ".join(motivos)


# --------------------------------------------------------------------------
# Com banco
# --------------------------------------------------------------------------


def _resumo(agendamento: Agendamento) -> dict:
    return {
        "id": agendamento.id,
        "status": agendamento.status,
        "data": agendamento.data_agendada or agendamento.loading_date,
        "itens": [
            {"cliente": i.cliente, "cidade": i.cidade, "toneladas": i.toneladas}
            for i in agendamento.itens
        ],
    }


def _candidatos(db: Session) -> list[dict]:
    """Agendamentos que ainda podem receber uma nota."""
    com_cte = {
        agendamento_id for (agendamento_id,) in db.query(OperacaoFiscal.agendamento_id)
        .filter(OperacaoFiscal.cod_conhecimento_bsoft != "").all()
    }
    abertos = db.query(Agendamento).filter(Agendamento.status != "Cancelado").all()
    return [_resumo(a) for a in abertos if a.id not in com_cte]


def _clientes_por_documento(db: Session) -> dict:
    return {
        _so_digitos(c.cnpj_cpf): c.nome
        for c in db.query(Cliente).filter(Cliente.cnpj_cpf != "").all()
        if _so_digitos(c.cnpj_cpf)
    }


def casar(db: Session, nota: NotaFiscalRecebida) -> NotaFiscalRecebida:
    """Liga a nota ao agendamento, quando da pra ter certeza. Grava o motivo
    nos dois casos, pra tela explicar."""
    dados = {
        "destinatario_doc": nota.destinatario_doc,
        "destinatario_nome": nota.destinatario_nome,
        "municipio_destino": nota.municipio_destino,
        "peso_kg": nota.peso_bruto,
        "emissao": nota.emissao,
    }
    escolhido, motivo = escolher(dados, _candidatos(db), _clientes_por_documento(db))
    nota.agendamento_id = escolhido["id"] if escolhido else None
    nota.casamento = motivo[:300]
    db.commit()
    return nota


def casar_pendentes(db: Session) -> int:
    """Tenta de novo as notas ainda soltas. O agendamento pode ter sido
    criado depois da nota chegar."""
    soltas = (
        db.query(NotaFiscalRecebida)
        .filter(NotaFiscalRecebida.tem_cte.is_(False), NotaFiscalRecebida.agendamento_id.is_(None))
        .all()
    )
    casadas = 0
    for nota in soltas:
        if casar(db, nota).agendamento_id:
            casadas += 1
    return casadas
