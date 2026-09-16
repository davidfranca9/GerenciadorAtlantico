"""Financeiro: saldo dos bancos, resultado do mes e agenda de pagamentos.

Faz as contas que viviam nas planilhas "Fluxo Caixa" e "Controle de
carregamentos" - sem copiar saldo de um dia pro outro e sem formula
quebrada. As rotas so recebem e devolvem; as regras ficam aqui.
"""
from __future__ import annotations

import calendar
import re
import unicodedata
import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..models import (
    CarregamentoFinanceiro,
    ContaAvulsa,
    ContaBancaria,
    Despesa,
    LancamentoCaixa,
    MetaMensal,
    PagamentoAgenda,
)

FORMAS = ("PIX", "TRANSFERENCIA", "BOLETO", "DEBITO", "CARTAO", "CHEQUE", "RENDIMENTO", "DINHEIRO", "OUTRO")
ESCOPOS = ("empresa", "pessoal")


class ErroFinanceiro(ValueError):
    """Pedido que nao faz sentido (conta inexistente, valor negativo...)."""


def dinheiro(valor) -> float:
    return round(float(valor or 0), 2)


def sem_acento(texto) -> str:
    base = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in base if not unicodedata.combining(c)).lower().strip()


# --------------------------------------------------------------------------
# Competencia (mes de referencia, "2026-09")
# --------------------------------------------------------------------------


def competencia_de(dia: date) -> str:
    return f"{dia.year:04d}-{dia.month:02d}"


def validar_competencia(competencia: str) -> str:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", competencia or ""):
        raise ErroFinanceiro("Mês inválido: use o formato AAAA-MM")
    return competencia


def limites_competencia(competencia: str) -> tuple[date, date]:
    ano, mes = map(int, validar_competencia(competencia).split("-"))
    return date(ano, mes, 1), date(ano, mes, calendar.monthrange(ano, mes)[1])


def somar_mes(dia: date, meses: int = 1) -> date:
    """31/01 + 1 mes = 28/02 (ultimo dia quando o mes e mais curto)."""
    total = dia.month - 1 + meses
    ano, mes = dia.year + total // 12, total % 12 + 1
    return date(ano, mes, min(dia.day, calendar.monthrange(ano, mes)[1]))


def meses_entre(inicio: str, fim: str) -> int:
    a1, m1 = map(int, inicio.split("-"))
    a2, m2 = map(int, fim.split("-"))
    return (a2 - a1) * 12 + (m2 - m1)


# --------------------------------------------------------------------------
# Caixa
# --------------------------------------------------------------------------

# "PIX: Bianca Maria", "TRNSF: Banco do Brasil", "BOLETOS: Equilibrio"...
_PREFIXOS_FORMA = (
    (r"PIX", "PIX"),
    (r"TRNSF|TRANSF\w*|TED|DOC", "TRANSFERENCIA"),
    (r"BOLETOS?", "BOLETO"),
    (r"D[EÉ]BITOS?", "DEBITO"),
    (r"CART[AÃ]O", "CARTAO"),
    (r"CH(EQUE)?", "CHEQUE"),
    (r"RENDE\s*F[AÁ]CIL|RENDIMENTOS?", "RENDIMENTO"),
)

# Palavras soltas em extrato de banco (OFX), em qualquer ponto do texto.
_PALAVRAS_FORMA = (
    (r"\bPIX\b", "PIX"),
    (r"\b(TED|DOC|TRANSF\w*)\b", "TRANSFERENCIA"),
    (r"BOLETO|PAG(AMENTO)?\.?\s*(DE\s*)?T[IÍ]TULO|COBRAN[CÇ]A", "BOLETO"),
    (r"RENDIMENTO|RENDE\s*F[AÁ]CIL|APLICA[CÇ][AÃ]O|RESGATE", "RENDIMENTO"),
    (r"CHEQUE", "CHEQUE"),
    (r"COMPRA|CART[AÃ]O", "CARTAO"),
    (r"TARIFA|D[EÉ]BITO|\bDEB\b|IOF|JUROS", "DEBITO"),
)


def separar_forma(texto: str) -> tuple[str, str]:
    """ "PIX: Bianca Maria" -> ("PIX", "Bianca Maria")."""
    bruto = re.sub(r"\s+", " ", str(texto or "")).strip()
    for padrao, forma in _PREFIXOS_FORMA:
        achou = re.match(rf"^({padrao})\s*:\s*(.*)$", bruto, flags=re.IGNORECASE)
        if achou:
            return forma, achou.groups()[-1].strip() or bruto
        if re.fullmatch(padrao, bruto, flags=re.IGNORECASE):
            return forma, bruto
    return "OUTRO", bruto


def forma_pelo_texto(texto: str) -> str:
    forma, _ = separar_forma(texto)
    if forma != "OUTRO":
        return forma
    for padrao, forma in _PALAVRAS_FORMA:
        if re.search(padrao, str(texto or ""), flags=re.IGNORECASE):
            return forma
    return "OUTRO"


def _com_sinal():
    return case((LancamentoCaixa.tipo == "entrada", LancamentoCaixa.valor), else_=-LancamentoCaixa.valor)


def _soma(db: Session, conta_id: int, de: date, ate_exclusivo: date) -> float:
    if de >= ate_exclusivo:
        return 0.0
    total = (
        db.query(func.coalesce(func.sum(_com_sinal()), 0))
        .filter(LancamentoCaixa.conta_id == conta_id, LancamentoCaixa.data >= de, LancamentoCaixa.data < ate_exclusivo)
        .scalar()
    )
    return float(total or 0)


def saldo_no_inicio(db: Session, conta: ContaBancaria, dia: date) -> float:
    """Saldo da conta no comeco de `dia`, andando a partir do saldo inicial
    pra frente ou pra tras."""
    base = dinheiro(conta.saldo_inicial)
    if dia >= conta.saldo_inicial_em:
        return dinheiro(base + _soma(db, conta.id, conta.saldo_inicial_em, dia))
    return dinheiro(base - _soma(db, conta.id, dia, conta.saldo_inicial_em))


def conta_para_dict(db: Session, conta: ContaBancaria, hoje: Optional[date] = None) -> dict:
    hoje = hoje or date.today()
    return {
        "id": conta.id,
        "nome": conta.nome,
        "instituicao": conta.instituicao,
        "cor": conta.cor,
        "saldo_inicial": dinheiro(conta.saldo_inicial),
        "saldo_inicial_em": conta.saldo_inicial_em.isoformat(),
        "ativa": conta.ativa,
        "ordem": conta.ordem,
        "saldo_atual": saldo_no_inicio(db, conta, hoje + timedelta(days=1)),
    }


def lancamento_para_dict(lanc: LancamentoCaixa, contas: dict[int, ContaBancaria], contraparte: Optional[int] = None) -> dict:
    conta = contas.get(lanc.conta_id)
    outra = contas.get(contraparte) if contraparte else None
    return {
        "id": lanc.id,
        "conta_id": lanc.conta_id,
        "conta": conta.nome if conta else "",
        "cor": conta.cor if conta else "",
        "data": lanc.data.isoformat(),
        "tipo": lanc.tipo,
        "forma": lanc.forma,
        "descricao": lanc.descricao,
        "valor": dinheiro(lanc.valor),
        "transferencia": lanc.transferencia,
        "contraparte_id": outra.id if outra else None,
        "contraparte": outra.nome if outra else "",
        "origem": lanc.origem,
    }


def resumo_caixa(db: Session, inicio: date, fim: date, conta_id: Optional[int] = None, dias_serie: int = 30) -> dict:
    if fim < inicio:
        raise ErroFinanceiro("O fim do período vem antes do início")
    contas = db.query(ContaBancaria).filter(ContaBancaria.ativa.is_(True)).order_by(ContaBancaria.ordem, ContaBancaria.id).all()
    por_id = {c.id: c for c in contas}

    serie_inicio = min(inicio, fim - timedelta(days=dias_serie - 1))
    lancs = (
        db.query(LancamentoCaixa)
        .filter(LancamentoCaixa.conta_id.in_(por_id.keys() or [0]), LancamentoCaixa.data >= serie_inicio, LancamentoCaixa.data <= fim)
        .order_by(LancamentoCaixa.data, LancamentoCaixa.id)
        .all()
    )

    # Ponta oposta de cada transferencia (pra tela dizer "de onde / pra onde").
    pontas: dict[str, list[LancamentoCaixa]] = defaultdict(list)
    for lanc in lancs:
        if lanc.transferencia:
            pontas[lanc.transferencia].append(lanc)
    faltando = [t for t, lista in pontas.items() if len(lista) < 2]
    if faltando:
        for lanc in db.query(LancamentoCaixa).filter(LancamentoCaixa.transferencia.in_(faltando)).all():
            if lanc not in pontas[lanc.transferencia]:
                pontas[lanc.transferencia].append(lanc)

    def contraparte(lanc):
        if not lanc.transferencia:
            return None
        return next((o.conta_id for o in pontas[lanc.transferencia] if o.id != lanc.id), None)

    saldo_serie = {c.id: saldo_no_inicio(db, c, serie_inicio) for c in contas}
    por_dia: dict[date, list[LancamentoCaixa]] = defaultdict(list)
    for lanc in lancs:
        por_dia[lanc.data].append(lanc)

    abertura = {}
    serie = []
    dia = serie_inicio
    while dia <= fim:
        if dia == inicio:
            abertura = dict(saldo_serie)
        for lanc in por_dia.get(dia, []):
            sinal = 1 if lanc.tipo == "entrada" else -1
            saldo_serie[lanc.conta_id] = saldo_serie.get(lanc.conta_id, 0) + sinal * float(lanc.valor)
        if dia >= fim - timedelta(days=dias_serie - 1):
            serie.append({"data": dia.isoformat(), "saldo": dinheiro(sum(saldo_serie.values()))})
        dia += timedelta(days=1)

    do_periodo = [l for l in lancs if inicio <= l.data <= fim]
    linhas = []
    for conta in contas:
        meus = [l for l in do_periodo if l.conta_id == conta.id]
        entradas = dinheiro(sum(float(l.valor) for l in meus if l.tipo == "entrada"))
        saidas = dinheiro(sum(float(l.valor) for l in meus if l.tipo == "saida"))
        linhas.append({
            "id": conta.id, "nome": conta.nome, "instituicao": conta.instituicao, "cor": conta.cor,
            "saldo_inicial": dinheiro(conta.saldo_inicial), "saldo_inicial_em": conta.saldo_inicial_em.isoformat(),
            "abertura": dinheiro(abertura.get(conta.id, 0)), "entradas": entradas, "saidas": saidas,
            "fechamento": dinheiro(abertura.get(conta.id, 0) + entradas - saidas),
            "movimentos": len(meus),
        })

    externas = [l for l in do_periodo if not l.transferencia]
    totais = {
        "abertura": dinheiro(sum(l["abertura"] for l in linhas)),
        "entradas": dinheiro(sum(l["entradas"] for l in linhas)),
        "saidas": dinheiro(sum(l["saidas"] for l in linhas)),
        "fechamento": dinheiro(sum(l["fechamento"] for l in linhas)),
        # Transferencia entre contas proprias nao e dinheiro novo nem gasto.
        "entradas_externas": dinheiro(sum(float(l.valor) for l in externas if l.tipo == "entrada")),
        "saidas_externas": dinheiro(sum(float(l.valor) for l in externas if l.tipo == "saida")),
        "transferencias": dinheiro(sum(float(l.valor) for l in do_periodo if l.transferencia and l.tipo == "saida")),
    }
    totais["resultado"] = dinheiro(totais["entradas_externas"] - totais["saidas_externas"])

    visiveis = [l for l in do_periodo if conta_id is None or l.conta_id == conta_id]
    visiveis.sort(key=lambda l: (l.data, l.id), reverse=True)
    ultimo = db.query(func.max(LancamentoCaixa.data)).scalar()
    return {
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
        # A tela abre no ultimo dia com movimento quando hoje ainda esta vazio.
        "ultimo_movimento": ultimo.isoformat() if ultimo else None,
        "contas": linhas,
        "totais": totais,
        "serie": serie,
        "lancamentos": [lancamento_para_dict(l, por_id, contraparte(l)) for l in visiveis],
    }


def _conta(db: Session, conta_id: int) -> ContaBancaria:
    conta = db.get(ContaBancaria, conta_id)
    if conta is None:
        raise ErroFinanceiro("Conta bancária não encontrada")
    return conta


def criar_lancamento(db: Session, *, conta_id: int, data: date, tipo: str, valor: float, descricao: str = "",
                     forma: str = "OUTRO", usuario: str = "", origem: str = "manual", id_externo: Optional[str] = None) -> LancamentoCaixa:
    _conta(db, conta_id)
    if tipo not in ("entrada", "saida"):
        raise ErroFinanceiro("Tipo precisa ser entrada ou saída")
    if dinheiro(valor) <= 0:
        raise ErroFinanceiro("O valor precisa ser maior que zero")
    forma = (forma or "OUTRO").upper()
    if forma not in FORMAS:
        raise ErroFinanceiro(f"Forma de pagamento desconhecida: {forma}")
    lanc = LancamentoCaixa(
        conta_id=conta_id, data=data, tipo=tipo, valor=dinheiro(valor), descricao=(descricao or "").strip()[:255],
        forma=forma, origem=origem, id_externo=id_externo, criado_por=usuario or "",
    )
    db.add(lanc)
    db.flush()
    return lanc


def criar_transferencia(db: Session, *, origem_id: int, destino_id: int, data: date, valor: float,
                        descricao: str = "", usuario: str = "") -> list[LancamentoCaixa]:
    if origem_id == destino_id:
        raise ErroFinanceiro("Escolha contas diferentes pra transferir")
    origem, destino = _conta(db, origem_id), _conta(db, destino_id)
    codigo = str(uuid.uuid4())
    saida = criar_lancamento(db, conta_id=origem.id, data=data, tipo="saida", valor=valor, forma="TRANSFERENCIA",
                             descricao=descricao or f"Para {destino.nome}", usuario=usuario)
    entrada = criar_lancamento(db, conta_id=destino.id, data=data, tipo="entrada", valor=valor, forma="TRANSFERENCIA",
                               descricao=descricao or f"De {origem.nome}", usuario=usuario)
    saida.transferencia = entrada.transferencia = codigo
    db.flush()
    return [saida, entrada]


def excluir_lancamento(db: Session, lancamento_id: int) -> int:
    lanc = db.get(LancamentoCaixa, lancamento_id)
    if lanc is None:
        raise ErroFinanceiro("Lançamento não encontrado")
    alvos = [lanc]
    if lanc.transferencia:
        alvos = db.query(LancamentoCaixa).filter(LancamentoCaixa.transferencia == lanc.transferencia).all()
    ids = [a.id for a in alvos]
    # Conta paga pela agenda continua paga; so perde o elo com o banco.
    for pagamento in db.query(PagamentoAgenda).filter(PagamentoAgenda.lancamento_id.in_(ids)).all():
        pagamento.lancamento_id = None
        pagamento.conta_id = None
    for alvo in alvos:
        db.delete(alvo)
    db.flush()
    return len(alvos)


def ligar_transferencias(db: Session, dia: date) -> int:
    """Liga a saida de uma conta com a entrada na outra: mesmo dia, mesmo
    valor, e cada descricao citando a outra conta ("TRNSF: Nu Pagamentos")."""
    contas = db.query(ContaBancaria).all()
    soltos = (
        db.query(LancamentoCaixa)
        .filter(LancamentoCaixa.data == dia, LancamentoCaixa.forma == "TRANSFERENCIA", LancamentoCaixa.transferencia.is_(None))
        .order_by(LancamentoCaixa.id)
        .all()
    )

    def cita(lanc, conta):
        texto = sem_acento(lanc.descricao)
        nomes = {sem_acento(conta.nome), sem_acento(conta.instituicao)} - {""}
        return any(nome in texto or texto in nome for nome in nomes if texto)

    ligadas = 0
    usados = set()
    for saida in [l for l in soltos if l.tipo == "saida"]:
        destino = next((c for c in contas if c.id != saida.conta_id and cita(saida, c)), None)
        origem = next((c for c in contas if c.id == saida.conta_id), None)
        if destino is None or origem is None:
            continue
        par = next(
            (e for e in soltos if e.tipo == "entrada" and e.id not in usados and e.conta_id == destino.id
             and abs(float(e.valor) - float(saida.valor)) < 0.005 and cita(e, origem)),
            None,
        )
        if par is None:
            continue
        saida.transferencia = par.transferencia = str(uuid.uuid4())
        usados.update({saida.id, par.id})
        ligadas += 1
    db.flush()
    return ligadas


# --------------------------------------------------------------------------
# Resultado dos carregamentos
# --------------------------------------------------------------------------

PARTES = ("frete_empresa", "frete_motorista", "agenciamento", "comissao")


def totais_carregamento(c: CarregamentoFinanceiro) -> dict:
    peso = float(c.peso or 0)
    totais = {}
    for parte in PARTES:
        fechado = getattr(c, f"{parte}_total")
        por_ton = getattr(c, f"{parte}_ton")
        totais[parte] = 0.0 if c.cancelado else dinheiro(fechado if fechado is not None else float(por_ton or 0) * peso)
    # Carga do Bsoft sem o frete do motorista: sem sobra ate completar (contar
    # o motorista como zero faria a carga parecer render o frete inteiro).
    completo = not falta_frete_do_motorista(c)
    if not completo:
        return {**totais, "liquido": None, "por_tonelada": None, "completo": False}
    liquido = dinheiro(totais["frete_empresa"] - totais["frete_motorista"] - totais["agenciamento"] - totais["comissao"])
    return {**totais, "liquido": liquido, "por_tonelada": dinheiro(liquido / peso) if peso and not c.cancelado else None, "completo": True}


def falta_frete_do_motorista(c: CarregamentoFinanceiro) -> bool:
    return (c.origem == "bsoft" and not c.cancelado
            and c.frete_motorista_ton is None and c.frete_motorista_total is None)


def carregamento_para_dict(c: CarregamentoFinanceiro) -> dict:
    return {
        "id": c.id,
        "competencia": c.competencia,
        "ctes": c.ctes,
        "data_emissao": c.data_emissao.isoformat() if c.data_emissao else None,
        "motorista": c.motorista,
        "fabrica": c.fabrica,
        "destino": c.destino,
        "contratante": c.contratante,
        "peso": float(c.peso or 0),
        **{f"{p}_ton": (dinheiro(getattr(c, f"{p}_ton")) if getattr(c, f"{p}_ton") is not None else None) for p in PARTES},
        **{f"{p}_fechado": (dinheiro(getattr(c, f"{p}_total")) if getattr(c, f"{p}_total") is not None else None) for p in PARTES},
        "cancelado": c.cancelado,
        "observacao": c.observacao,
        "origem": c.origem or "manual",
        "cliente": c.cliente or "",
        "contrato_frete": c.contrato_frete or "",
        "valor_contrato_frete": dinheiro(c.valor_contrato_frete) if c.valor_contrato_frete is not None else None,
        **_o_que_falta(c),
        "totais": totais_carregamento(c),
    }


def _o_que_falta(c: CarregamentoFinanceiro) -> dict:
    """Carga que veio do Bsoft e ainda nao tem o que so a operacao sabe."""
    faltando = []
    if c.origem == "bsoft" and not c.cancelado:
        if c.frete_motorista_ton is None and c.frete_motorista_total is None:
            faltando.append("frete do motorista")
        if c.agenciamento_ton is None and c.agenciamento_total is None:
            faltando.append("agenciamento")
        if not c.contratante:
            faltando.append("contratante")
    return {"a_completar": bool(faltando), "faltando": faltando}


def listar_carregamentos(db: Session, competencia: Optional[str] = None) -> dict:
    """Cada carregamento com as contas da linha (a aba LUCRO BRUTO inteira).
    Sem competencia, todos os meses - o mais recente primeiro."""
    consulta = db.query(CarregamentoFinanceiro)
    if competencia:
        consulta = consulta.filter(CarregamentoFinanceiro.competencia == validar_competencia(competencia))
    carregamentos = consulta.all()
    carregamentos.sort(key=lambda c: (c.competencia, not c.cancelado, c.data_emissao or date.min, c.id), reverse=True)
    meses = sorted({c for (c,) in db.query(CarregamentoFinanceiro.competencia).distinct()}, reverse=True)
    return {"competencias": meses, "carregamentos": [carregamento_para_dict(c) for c in carregamentos]}


def despesas_do_mes(db: Session, competencia: str, escopo: Optional[str] = None) -> list[tuple[Despesa, Optional[int]]]:
    """Despesas que valem no mes, com a parcela da vez (None se nao e parcelada)."""
    consulta = db.query(Despesa).filter(Despesa.ativa.is_(True))
    if escopo:
        consulta = consulta.filter(Despesa.escopo == escopo)
    valem = []
    for despesa in consulta.order_by(Despesa.escopo, Despesa.ordem, Despesa.id).all():
        passados = meses_entre(despesa.competencia_inicio, competencia)
        if passados < 0:
            continue
        parcela = None
        if despesa.parcelas_total:
            parcela = (despesa.parcela_inicial or 1) + passados
            if parcela > despesa.parcelas_total:
                continue
        valem.append((despesa, parcela))
    return valem


def _dias_de_carregamento(de: date, ate: date) -> int:
    """Segunda a sabado: a operacao nao carrega domingo."""
    if de > ate:
        return 0
    return sum(1 for n in range((ate - de).days + 1) if (de + timedelta(days=n)).weekday() != 6)


def resultado_mensal(db: Session, competencia: str, hoje: Optional[date] = None) -> dict:
    hoje = hoje or date.today()
    inicio, fim = limites_competencia(competencia)
    carregamentos = (
        db.query(CarregamentoFinanceiro)
        .filter(CarregamentoFinanceiro.competencia == competencia)
        .all()
    )
    # Por data de emissao; cancelado (sem data) vai pro fim.
    carregamentos.sort(key=lambda c: (c.cancelado, c.data_emissao is None, c.data_emissao or date.min, c.id))
    linhas = [carregamento_para_dict(c) for c in carregamentos]
    validos = [l for l in linhas if not l["cancelado"]]
    # Lucro e margem so das cargas completas; tonelada conta todas (a carga existiu).
    completos = [l for l in validos if l["totais"]["completo"]]
    pendentes = [l for l in validos if not l["totais"]["completo"]]

    toneladas = round(sum(l["peso"] for l in validos), 2)
    toneladas_completas = round(sum(l["peso"] for l in completos), 2)
    soma = {p: dinheiro(sum(l["totais"][p] for l in completos)) for p in PARTES}
    lucro_bruto = dinheiro(sum(l["totais"]["liquido"] for l in completos))
    media = dinheiro(lucro_bruto / toneladas_completas) if toneladas_completas else None

    meta = db.get(MetaMensal, competencia)
    meta_ton = float(meta.meta_toneladas) if meta and meta.meta_toneladas else None
    falta = round(max(0.0, meta_ton - toneladas), 2) if meta_ton else None
    dias_restantes = _dias_de_carregamento(max(hoje, inicio), fim) if hoje <= fim else 0

    despesas = despesas_do_mes(db, competencia)
    empresa = dinheiro(sum(float(d.valor) for d, _ in despesas if d.escopo == "empresa" and d.conta_no_resultado))
    pessoal = dinheiro(sum(float(d.valor) for d, _ in despesas if d.escopo == "pessoal" and d.conta_no_resultado))
    custo_fixo = dinheiro(sum(float(d.valor) for d, _ in despesas if d.escopo == "empresa" and d.entra_precificacao))
    lucro_real = dinheiro(lucro_bruto - empresa)
    sobra = dinheiro(lucro_real - pessoal)

    def agrupar(campo):
        grupos: dict[str, dict] = {}
        for l in completos:
            chave = l[campo] or "Sem " + ("contratante" if campo == "contratante" else "fábrica")
            g = grupos.setdefault(chave, {"nome": chave, "carregamentos": 0, "toneladas": 0.0, "lucro": 0.0})
            g["carregamentos"] += 1
            g["toneladas"] = round(g["toneladas"] + l["peso"], 2)
            g["lucro"] = dinheiro(g["lucro"] + l["totais"]["liquido"])
        lista = sorted(grupos.values(), key=lambda g: g["lucro"], reverse=True)
        for g in lista:
            g["por_tonelada"] = dinheiro(g["lucro"] / g["toneladas"]) if g["toneladas"] else None
        return lista

    return {
        "competencia": competencia,
        "carregamentos": linhas,
        "resumo": {
            "carregamentos": len(validos),
            "cancelados": len(linhas) - len(validos),
            "toneladas": toneladas,
            "toneladas_completas": toneladas_completas,
            **soma,
            "lucro_bruto": lucro_bruto,
            "lucro_por_tonelada": media,
            "pendentes": {
                "carregamentos": len(pendentes),
                "toneladas": round(sum(l["peso"] for l in pendentes), 2),
                "frete_empresa": dinheiro(sum(l["totais"]["frete_empresa"] for l in pendentes)),
            },
        },
        "meta": {
            "toneladas": meta_ton,
            "falta": falta,
            "percentual": round(toneladas / meta_ton * 100, 1) if meta_ton else None,
            "dias_restantes": dias_restantes,
            "ritmo_necessario": round(falta / dias_restantes, 1) if falta and dias_restantes else None,
        },
        "despesas": {"empresa": empresa, "pessoal": pessoal},
        "lucro_real": lucro_real,
        "sobra": sobra,
        # Na planilha "Valor por Tonelada" subtraia o lucro bruto das despesas
        # em vez de dividir pelas toneladas. Aqui e a conta que ela queria.
        "precificacao": {
            "custo_fixo": custo_fixo,
            "por_tonelada_atual": dinheiro(custo_fixo / toneladas) if toneladas else None,
            "por_tonelada_na_meta": dinheiro(custo_fixo / meta_ton) if meta_ton else None,
            "ponto_de_equilibrio_ton": round(custo_fixo / media, 1) if media and media > 0 else None,
        },
        "cascata": [
            {"rotulo": "Frete cobrado", "valor": soma["frete_empresa"], "tipo": "inicio"},
            {"rotulo": "Frete dos motoristas", "valor": -soma["frete_motorista"], "tipo": "saida"},
            {"rotulo": "Agenciamento", "valor": -soma["agenciamento"], "tipo": "saida"},
            {"rotulo": "Comissão de representante", "valor": -soma["comissao"], "tipo": "saida"},
            {"rotulo": "Lucro bruto", "valor": lucro_bruto, "tipo": "subtotal"},
            {"rotulo": "Despesas da empresa", "valor": -empresa, "tipo": "saida"},
            {"rotulo": "Lucro real", "valor": lucro_real, "tipo": "subtotal"},
            {"rotulo": "Gastos pessoais", "valor": -pessoal, "tipo": "saida"},
            {"rotulo": "Sobra do mês", "valor": sobra, "tipo": "final"},
        ],
        "por_contratante": agrupar("contratante"),
        "por_fabrica": agrupar("fabrica"),
    }


# --------------------------------------------------------------------------
# Agenda de pagamentos
# --------------------------------------------------------------------------


def despesa_para_dict(despesa: Despesa, parcela: Optional[int] = None) -> dict:
    return {
        "id": despesa.id,
        "escopo": despesa.escopo,
        "grupo": despesa.grupo,
        "descricao": despesa.descricao,
        "dia_vencimento": despesa.dia_vencimento,
        "valor": dinheiro(despesa.valor),
        "parcela_inicial": despesa.parcela_inicial,
        "parcelas_total": despesa.parcelas_total,
        "parcela": parcela,
        "competencia_inicio": despesa.competencia_inicio,
        "conta_no_resultado": despesa.conta_no_resultado,
        "entra_precificacao": despesa.entra_precificacao,
        "ativa": despesa.ativa,
        "ordem": despesa.ordem,
    }


def agenda(db: Session, competencia: str, hoje: Optional[date] = None, escopo: Optional[str] = None) -> dict:
    hoje = hoje or date.today()
    inicio, fim = limites_competencia(competencia)
    pagos = {(p.origem, p.origem_id): p for p in db.query(PagamentoAgenda).filter(PagamentoAgenda.competencia == competencia).all()}
    contas = {c.id: c for c in db.query(ContaBancaria).all()}

    itens = []

    def situacao(vencimento, pagamento):
        if pagamento:
            return "pago"
        if vencimento is None:
            return "sem_data"
        if vencimento < hoje:
            return "atrasado"
        return "hoje" if vencimento == hoje else "a_vencer"

    def pagamento_dict(p):
        if not p:
            return None
        conta = contas.get(p.conta_id)
        return {"valor": dinheiro(p.valor), "pago_em": p.pago_em.isoformat(), "conta_id": p.conta_id,
                "conta": conta.nome if conta else "", "lancamento_id": p.lancamento_id}

    # Despesa que so entra na precificacao (seguro, Buonny) nao e boleto do mes.
    for despesa, parcela in despesas_do_mes(db, competencia, escopo):
        if not despesa.conta_no_resultado:
            continue
        vencimento = date(inicio.year, inicio.month, min(despesa.dia_vencimento, fim.day)) if despesa.dia_vencimento else None
        pagamento = pagos.get(("despesa", despesa.id))
        itens.append({
            "origem": "despesa", "id": despesa.id, "escopo": despesa.escopo, "grupo": despesa.grupo,
            "descricao": despesa.descricao, "parcela": f"{parcela}/{despesa.parcelas_total}" if parcela else None,
            # Conta fixa com valor zerado (agua, taxa variavel) e "valor a definir".
            "valor": dinheiro(despesa.valor) or None, "vencimento": vencimento.isoformat() if vencimento else None,
            "situacao": situacao(vencimento, pagamento), "pagamento": pagamento_dict(pagamento),
        })

    avulsas = db.query(ContaAvulsa).filter(ContaAvulsa.data >= inicio, ContaAvulsa.data <= fim)
    if escopo:
        avulsas = avulsas.filter(ContaAvulsa.escopo == escopo)
    for avulsa in avulsas.all():
        pagamento = pagos.get(("avulsa", avulsa.id))
        itens.append({
            "origem": "avulsa", "id": avulsa.id, "escopo": avulsa.escopo, "grupo": "Avulsa",
            "descricao": avulsa.descricao, "parcela": None,
            "valor": dinheiro(avulsa.valor) if avulsa.valor is not None else None,
            "vencimento": avulsa.data.isoformat(), "situacao": situacao(avulsa.data, pagamento),
            "pagamento": pagamento_dict(pagamento),
        })

    itens.sort(key=lambda i: (i["vencimento"] or "9999", i["descricao"]))

    def valor(i):
        if i["pagamento"]:
            return i["pagamento"]["valor"]
        return i["valor"] or 0

    daqui_7 = hoje + timedelta(days=7)
    abertos = [i for i in itens if i["situacao"] != "pago"]
    return {
        "competencia": competencia,
        "hoje": hoje.isoformat(),
        "itens": itens,
        "totais": {
            "total": dinheiro(sum(valor(i) for i in itens)),
            "pago": dinheiro(sum(valor(i) for i in itens if i["situacao"] == "pago")),
            "a_pagar": dinheiro(sum(valor(i) for i in abertos)),
            "atrasado": dinheiro(sum(valor(i) for i in abertos if i["situacao"] == "atrasado")),
            "atrasados": sum(1 for i in abertos if i["situacao"] == "atrasado"),
            "proximos_7_dias": dinheiro(sum(
                valor(i) for i in abertos if i["vencimento"] and hoje.isoformat() <= i["vencimento"] <= daqui_7.isoformat()
            )),
            "sem_valor": sum(1 for i in itens if i["valor"] is None),
        },
    }


def _item_da_agenda(db: Session, origem: str, origem_id: int, competencia: str) -> dict:
    for item in agenda(db, competencia)["itens"]:
        if item["origem"] == origem and item["id"] == origem_id:
            return item
    raise ErroFinanceiro("Essa conta não está na agenda desse mês")


def pagar(db: Session, *, origem: str, origem_id: int, competencia: str, pago_em: date,
          valor: Optional[float] = None, conta_id: Optional[int] = None, forma: str = "BOLETO", usuario: str = "") -> PagamentoAgenda:
    item = _item_da_agenda(db, origem, origem_id, competencia)
    if item["pagamento"]:
        raise ErroFinanceiro("Essa conta já está paga")
    valor = dinheiro(valor if valor is not None else item["valor"])
    if valor <= 0:
        raise ErroFinanceiro("Informe o valor pago")
    lancamento = None
    if conta_id:
        descricao = item["descricao"] + (f" {item['parcela']}" if item["parcela"] else "")
        lancamento = criar_lancamento(
            db, conta_id=conta_id, data=pago_em, tipo="saida", valor=valor, descricao=descricao, forma=forma,
            usuario=usuario, origem="agenda", id_externo=f"agenda:{origem}:{origem_id}:{competencia}",
        )
    pagamento = PagamentoAgenda(
        origem=origem, origem_id=origem_id, competencia=competencia, valor=valor, pago_em=pago_em,
        conta_id=conta_id if lancamento else None, lancamento_id=lancamento.id if lancamento else None,
    )
    db.add(pagamento)
    db.flush()
    return pagamento


def desfazer_pagamento(db: Session, *, origem: str, origem_id: int, competencia: str) -> None:
    pagamento = (
        db.query(PagamentoAgenda)
        .filter(PagamentoAgenda.origem == origem, PagamentoAgenda.origem_id == origem_id, PagamentoAgenda.competencia == competencia)
        .first()
    )
    if pagamento is None:
        raise ErroFinanceiro("Essa conta não está marcada como paga")
    if pagamento.lancamento_id:
        lanc = db.get(LancamentoCaixa, pagamento.lancamento_id)
        if lanc is not None:
            db.delete(lanc)
    db.delete(pagamento)
    db.flush()
