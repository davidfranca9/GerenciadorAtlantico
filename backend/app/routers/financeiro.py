"""Financeiro: caixa dos bancos, resultado do mes e contas a pagar.

Leitura e escrita andam separadas aqui. Quem tem uma aba do Financeiro
liberada na tela de Administracao consegue VER o que aquela aba mostra (os
GET); lancar, pagar, excluir e importar continuam so de administrador - aqui
tem saldo de banco, gastos pessoais e dividas.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin, tem_tela
from ..database import get_db
from ..models import (CarregamentoFinanceiro, CartaFreteEnviada, ContaAvulsa, ContaBancaria, Despesa, Divida, LancamentoCaixa,
                      MetaMensal, PagamentoAgenda, PagamentoFaturaAbastecimento, User)
from ..servicos import financeiro as fin
from ..servicos import financeiro_importacao as importacao

# Cada GET do financeiro pertence a uma (ou mais) aba do menu: quem tem a aba
# liberada le o que aquela aba precisa, e nada alem disso. A chave e o caminho
# da rota como o FastAPI registra; o valor, as abas que usam a resposta.
TELAS_DE_LEITURA: dict[str, tuple[str, ...]] = {
    # Nome e SALDO das contas bancarias. So abas que mostram saldo ou escolhem
    # a conta de um pagamento - Carregamentos e Lucro bruto nao precisam.
    "/financeiro/contas": ("/financeiro/caixa", "/financeiro/gastos", "/financeiro/pagamentos",
                           "/financeiro/faturas", "/financeiro/agenciamentos", "/financeiro/dividas"),
    "/financeiro/caixa": ("/financeiro/caixa",),
    "/financeiro/resultado": ("/financeiro/lucro-bruto", "/financeiro/gastos", "/financeiro/precificacao"),
    "/financeiro/carregamentos": ("/financeiro/carregamentos",),
    "/financeiro/faturas": ("/financeiro/faturas",),
    # /comissoes e o endereco antigo de /agenciamentos: mesma aba.
    "/financeiro/comissoes": ("/financeiro/agenciamentos",),
    "/financeiro/agenciamentos": ("/financeiro/agenciamentos",),
    # A agenda do mes aparece em Pagamentos e no resumo de Gastos.
    "/financeiro/agenda": ("/financeiro/pagamentos", "/financeiro/gastos"),
    # Despesas da empresa e gastos PESSOAIS do dono.
    "/financeiro/despesas": ("/financeiro/gastos", "/financeiro/precificacao"),
    "/financeiro/dividas": ("/financeiro/dividas", "/financeiro/gastos"),
}


def permissao_financeiro(request: Request, user: User = Depends(get_current_user)) -> User:
    """Porteiro do financeiro inteiro, uma vez por requisicao:

    - administrador faz tudo;
    - GET de aba liberada passa: e o "acesso de visualizacao";
    - qualquer gravacao (POST/PUT/PATCH/DELETE) e so de administrador, mesmo
      pra quem tem a aba liberada;
    - GET que ninguem mapeou em TELAS_DE_LEITURA fica so de administrador, de
      proposito: rota de leitura nova nasce fechada em vez de nascer aberta
      porque alguem esqueceu de pensar nela.
    """
    if getattr(user, "role", "") == "admin":
        return user
    if request.method != "GET":
        raise HTTPException(status_code=403, detail="Somente administrador pode alterar o financeiro")
    rota = request.scope.get("route")
    telas = TELAS_DE_LEITURA.get(getattr(rota, "path", ""), ())
    if not telas or not tem_tela(user, *telas):
        raise HTTPException(status_code=403, detail="Você não tem acesso a essa tela do financeiro")
    return user


router = APIRouter(prefix="/financeiro", tags=["financeiro"], dependencies=[Depends(permissao_financeiro)])

LIMITE_ARQUIVO = 5 * 1024 * 1024


def _erro(exc: fin.ErroFinanceiro):
    return HTTPException(status_code=400, detail=str(exc))


def _usuario(user: User) -> str:
    return getattr(user, "email", "") or ""


async def _ler_arquivo(arquivo: UploadFile) -> bytes:
    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo vazio")
    if len(conteudo) > LIMITE_ARQUIVO:
        raise HTTPException(status_code=400, detail="Arquivo grande demais (máximo 5 MB)")
    return conteudo


# --------------------------------------------------------------------------
# Contas bancarias
# --------------------------------------------------------------------------


class ContaIn(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    instituicao: str = ""
    cor: str = ""
    saldo_inicial: float = 0
    saldo_inicial_em: date
    ativa: bool = True
    ordem: int = 0


class ContaPatch(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=80)
    instituicao: Optional[str] = None
    cor: Optional[str] = None
    saldo_inicial: Optional[float] = None
    saldo_inicial_em: Optional[date] = None
    ativa: Optional[bool] = None
    ordem: Optional[int] = None


@router.get("/contas")
def listar_contas(db: Session = Depends(get_db)):
    contas = db.query(ContaBancaria).order_by(ContaBancaria.ordem, ContaBancaria.id).all()
    return [fin.conta_para_dict(db, c) for c in contas]


@router.post("/contas")
def criar_conta(dados: ContaIn, db: Session = Depends(get_db)):
    conta = ContaBancaria(**dados.model_dump())
    conta.saldo_inicial = fin.dinheiro(conta.saldo_inicial)
    db.add(conta)
    db.commit()
    return fin.conta_para_dict(db, conta)


@router.patch("/contas/{conta_id}")
def atualizar_conta(conta_id: int, dados: ContaPatch, db: Session = Depends(get_db)):
    conta = db.get(ContaBancaria, conta_id)
    if conta is None:
        raise HTTPException(status_code=404, detail="Conta bancária não encontrada")
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(conta, campo, fin.dinheiro(valor) if campo == "saldo_inicial" else valor)
    db.commit()
    return fin.conta_para_dict(db, conta)


@router.post("/contas/{conta_id}/importar-extrato")
async def importar_extrato(conta_id: int, arquivo: UploadFile = File(...), aplicar: bool = False,
                           db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Extrato OFX do banco. Sem `aplicar`, so mostra o que entraria."""
    conteudo = await _ler_arquivo(arquivo)
    try:
        return importacao.importar_extrato(db, conta_id, conteudo, aplicar=aplicar, usuario=_usuario(user))
    except fin.ErroFinanceiro as exc:
        raise _erro(exc)


# Janela maxima de uma puxada. Nao e limite do banco (a doc nao diz qual e):
# e pra ninguem pedir "o ano inteiro" sem querer e ficar esperando paginacao.
DIAS_MAXIMOS_EXTRATO_ITAU = 92


@router.post("/contas/{conta_id}/extrato-itau")
def puxar_extrato_itau(conta_id: int, inicio: date, fim: date, aplicar: bool = False,
                       db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Extrato do periodo direto na API do Itau, no mesmo fluxo do OFX.

    Sem `aplicar`, so mostra o que entraria (a previa roda e desfaz). Com as
    credenciais do banco em branco responde 400 dizendo isso, em vez de
    estourar erro de conexao na cara de quem clicou.
    """
    from ..servicos import itau_extrato

    if fim < inicio:
        raise HTTPException(status_code=400, detail="O fim do período não pode ser antes do início")
    if (fim - inicio).days > DIAS_MAXIMOS_EXTRATO_ITAU:
        raise HTTPException(status_code=400, detail="Puxe no máximo 3 meses de extrato por vez")
    try:
        return itau_extrato.importar_extrato(db, conta_id, inicio, fim, aplicar=aplicar, usuario=_usuario(user))
    except itau_extrato.CredencialItauAusente as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except itau_extrato.PayloadItauDesconhecido as exc:
        # Campo que a documentacao nao mostrava: a mensagem traz o lancamento
        # que veio, pra ajustar a leitura sem adivinhacao.
        raise HTTPException(status_code=502, detail=str(exc)[:1200])
    except itau_extrato.ErroItau as exc:
        raise HTTPException(status_code=502, detail=f"O Itaú não respondeu: {str(exc)[:400]}")
    except fin.ErroFinanceiro as exc:
        raise _erro(exc)


# --------------------------------------------------------------------------
# Caixa
# --------------------------------------------------------------------------


class LancamentoIn(BaseModel):
    tipo: Literal["entrada", "saida", "transferencia"]
    data: date
    valor: float = Field(gt=0)
    descricao: str = Field(default="", max_length=255)
    forma: str = "OUTRO"
    conta_id: Optional[int] = None
    conta_destino_id: Optional[int] = None


class LancamentoPatch(BaseModel):
    data: Optional[date] = None
    valor: Optional[float] = Field(default=None, gt=0)
    descricao: Optional[str] = Field(default=None, max_length=255)
    forma: Optional[str] = None
    conta_id: Optional[int] = None


class FaturaAbastecimentoPatch(BaseModel):
    incluida: bool
    data_abastecimento: Optional[date] = None


class PagamentoFaturaAbastecimentoIn(BaseModel):
    competencia: str
    chave_fatura: str = Field(min_length=1, max_length=40)
    valor: Optional[float] = Field(default=None, gt=0)
    pago_em: date
    conta_id: int
    forma: str = "BOLETO"


class PagamentoComissaoIn(BaseModel):
    competencia: str
    beneficiario: str = Field(min_length=1, max_length=120)
    valor: float = Field(gt=0)
    pago_em: date
    conta_id: Optional[int] = None
    observacao: str = Field(default="", max_length=300)


@router.get("/caixa")
def caixa(inicio: date, fim: Optional[date] = None, conta_id: Optional[int] = None, db: Session = Depends(get_db)):
    try:
        return fin.resumo_caixa(db, inicio, fim or inicio, conta_id)
    except fin.ErroFinanceiro as exc:
        raise _erro(exc)


@router.post("/lancamentos")
def criar_lancamento(dados: LancamentoIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    try:
        if dados.tipo == "transferencia":
            if not dados.conta_id or not dados.conta_destino_id:
                raise fin.ErroFinanceiro("Escolha a conta de saída e a de entrada")
            criados = fin.criar_transferencia(db, origem_id=dados.conta_id, destino_id=dados.conta_destino_id, data=dados.data,
                                              valor=dados.valor, descricao=dados.descricao, usuario=_usuario(user))
        else:
            if not dados.conta_id:
                raise fin.ErroFinanceiro("Escolha a conta")
            criados = [fin.criar_lancamento(db, conta_id=dados.conta_id, data=dados.data, tipo=dados.tipo, valor=dados.valor,
                                            descricao=dados.descricao, forma=dados.forma, usuario=_usuario(user))]
        db.commit()
    except fin.ErroFinanceiro as exc:
        db.rollback()
        raise _erro(exc)
    return {"ids": [c.id for c in criados]}


@router.patch("/lancamentos/{lancamento_id}")
def atualizar_lancamento(lancamento_id: int, dados: LancamentoPatch, db: Session = Depends(get_db)):
    lanc = db.get(LancamentoCaixa, lancamento_id)
    if lanc is None:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    mudancas = dados.model_dump(exclude_unset=True)
    if "forma" in mudancas:
        mudancas["forma"] = (mudancas["forma"] or "OUTRO").upper()
        if mudancas["forma"] not in fin.FORMAS:
            raise HTTPException(status_code=400, detail="Forma de pagamento desconhecida")
    if "conta_id" in mudancas and db.get(ContaBancaria, mudancas["conta_id"]) is None:
        raise HTTPException(status_code=400, detail="Conta bancária não encontrada")
    # Transferencia: data e valor andam juntos nas duas pontas.
    pontas = [lanc]
    if lanc.transferencia:
        pontas = db.query(LancamentoCaixa).filter(LancamentoCaixa.transferencia == lanc.transferencia).all()
    for ponta in pontas:
        for campo in ("data", "valor"):
            if campo in mudancas:
                setattr(ponta, campo, fin.dinheiro(mudancas[campo]) if campo == "valor" else mudancas[campo])
    for campo in ("descricao", "forma", "conta_id"):
        if campo in mudancas:
            setattr(lanc, campo, mudancas[campo])
    db.commit()
    return {"ok": True}


@router.delete("/lancamentos/{lancamento_id}")
def excluir_lancamento(lancamento_id: int, db: Session = Depends(get_db)):
    try:
        removidos = fin.excluir_lancamento(db, lancamento_id)
        db.commit()
    except fin.ErroFinanceiro as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    return {"removidos": removidos}


# --------------------------------------------------------------------------
# Resultado do mes
# --------------------------------------------------------------------------


class CarregamentoIn(BaseModel):
    competencia: str
    ctes: str = Field(default="", max_length=120)
    data_emissao: Optional[date] = None
    motorista: str = Field(default="", max_length=255)
    fabrica: str = Field(default="", max_length=120)
    destino: str = Field(default="", max_length=160)
    contratante: str = Field(default="", max_length=120)
    peso: float = Field(default=0, ge=0)
    frete_empresa_ton: Optional[float] = None
    frete_empresa_total: Optional[float] = None
    frete_motorista_ton: Optional[float] = None
    frete_motorista_total: Optional[float] = None
    agenciamento_ton: Optional[float] = None
    agenciamento_total: Optional[float] = None
    comissao_ton: Optional[float] = None
    comissao_total: Optional[float] = None
    cancelado: bool = False
    observacao: str = Field(default="", max_length=500)


class MetaIn(BaseModel):
    meta_toneladas: float = Field(ge=0)


@router.get("/resultado")
def resultado(competencia: str, db: Session = Depends(get_db)):
    try:
        return fin.resultado_mensal(db, competencia)
    except fin.ErroFinanceiro as exc:
        raise _erro(exc)


@router.post("/carregamentos/bsoft")
def puxar_do_bsoft(competencia: str, aplicar: bool = False, db: Session = Depends(get_db)):
    """Le os CT-es e contratos de frete do mes no Bsoft (so leitura la) e
    mostra o que entraria. Com `aplicar`, grava."""
    from ..servicos import financeiro_bsoft
    from ..servicos.bsoft_client import BsoftError

    try:
        fin.validar_competencia(competencia)
        return financeiro_bsoft.sincronizar(db, competencia, aplicar=aplicar)
    except fin.ErroFinanceiro as exc:
        raise _erro(exc)
    except BsoftError as exc:
        raise HTTPException(status_code=502, detail=f"O Bsoft não respondeu: {str(exc)[:200]}")


@router.get("/carregamentos")
def listar_carregamentos(competencia: Optional[str] = None, db: Session = Depends(get_db)):
    """Todos os carregamentos (ou os do mes), com frete, custos e sobra de cada um."""
    try:
        return fin.listar_carregamentos(db, competencia)
    except fin.ErroFinanceiro as exc:
        raise _erro(exc)


@router.get("/faturas")
def listar_faturas(competencia: str, db: Session = Depends(get_db)):
    try:
        return fin.previsao_faturas_abastecimento(db, competencia)
    except fin.ErroFinanceiro as exc:
        raise _erro(exc)


@router.patch("/faturas/{autorizacao_id}")
def alterar_fatura(autorizacao_id: int, dados: FaturaAbastecimentoPatch, db: Session = Depends(get_db)):
    carta = db.get(CartaFreteEnviada, autorizacao_id)
    if carta is None:
        raise HTTPException(status_code=404, detail="Autorização de abastecimento não encontrada")
    carta.incluida_fatura = dados.incluida
    carta.data_abastecimento = dados.data_abastecimento
    db.commit()
    # Mudar a data move a autorizacao de fatura, as vezes pra outro mes: a
    # tela precisa saber pra onde ela foi, senao ela some sem explicacao.
    vencimento = fin.vencimento_da_autorizacao(carta)
    return {
        "ok": True, "incluida": carta.incluida_fatura, "data_abastecimento": carta.data_abastecimento,
        "vencimento": vencimento.isoformat(), "competencia": vencimento.strftime("%Y-%m"),
        "chave_fatura": f"vencimento-{vencimento.isoformat()}",
    }


@router.post("/faturas/pagamentos")
def pagar_fatura(dados: PagamentoFaturaAbastecimentoIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    try:
        pagamento = fin.pagar_fatura_abastecimento(
            db, competencia=dados.competencia, chave_fatura=dados.chave_fatura, pago_em=dados.pago_em,
            valor=dados.valor, conta_id=dados.conta_id, forma=dados.forma.upper(), usuario=_usuario(user),
        )
        db.commit()
        return {"id": pagamento.id, "ok": True}
    except fin.ErroFinanceiro as exc:
        db.rollback()
        raise _erro(exc)


@router.delete("/faturas/pagamentos/{pagamento_id}")
def desfazer_pagamento_fatura(pagamento_id: int, db: Session = Depends(get_db)):
    try:
        fin.desfazer_pagamento_fatura_abastecimento(db, pagamento_id)
        db.commit()
        return {"ok": True}
    except fin.ErroFinanceiro as exc:
        db.rollback()
        raise _erro(exc)


@router.get("/comissoes")
@router.get("/agenciamentos")
def listar_comissoes(competencia: str, db: Session = Depends(get_db)):
    try:
        return fin.painel_comissoes(db, competencia)
    except fin.ErroFinanceiro as exc:
        raise _erro(exc)


@router.post("/comissoes/pagamentos")
@router.post("/agenciamentos/pagamentos")
def registrar_pagamento_comissao(dados: PagamentoComissaoIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    try:
        fin.pagar_comissao(db, **dados.model_dump(), usuario=_usuario(user))
        db.commit()
        return fin.painel_comissoes(db, dados.competencia)
    except fin.ErroFinanceiro as exc:
        db.rollback()
        raise _erro(exc)


@router.delete("/comissoes/pagamentos/{pagamento_id}")
@router.delete("/agenciamentos/pagamentos/{pagamento_id}")
def remover_pagamento_comissao(pagamento_id: int, db: Session = Depends(get_db)):
    try:
        fin.desfazer_comissao(db, pagamento_id)
        db.commit()
    except fin.ErroFinanceiro as exc:
        db.rollback()
        raise _erro(exc)
    return {"ok": True}


def _aplicar_carregamento(c: CarregamentoFinanceiro, dados: CarregamentoIn):
    fin.validar_competencia(dados.competencia)
    for campo, valor in dados.model_dump().items():
        if campo.endswith("_ton") or campo.endswith("_total"):
            valor = fin.dinheiro(valor) if valor is not None else None
        elif campo == "contratante":
            valor = (valor or "").strip().upper()
        setattr(c, campo, valor)


@router.post("/carregamentos")
def criar_carregamento(dados: CarregamentoIn, db: Session = Depends(get_db)):
    c = CarregamentoFinanceiro()
    try:
        _aplicar_carregamento(c, dados)
    except fin.ErroFinanceiro as exc:
        raise _erro(exc)
    db.add(c)
    db.commit()
    return fin.carregamento_para_dict(c)


@router.put("/carregamentos/{carregamento_id}")
def atualizar_carregamento(carregamento_id: int, dados: CarregamentoIn, db: Session = Depends(get_db)):
    c = db.get(CarregamentoFinanceiro, carregamento_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Carregamento não encontrado")
    try:
        _aplicar_carregamento(c, dados)
    except fin.ErroFinanceiro as exc:
        raise _erro(exc)
    db.commit()
    return fin.carregamento_para_dict(c)


@router.delete("/carregamentos/{carregamento_id}")
def excluir_carregamento(carregamento_id: int, db: Session = Depends(get_db)):
    c = db.get(CarregamentoFinanceiro, carregamento_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Carregamento não encontrado")
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.put("/metas/{competencia}")
def definir_meta(competencia: str, dados: MetaIn, db: Session = Depends(get_db)):
    try:
        fin.validar_competencia(competencia)
    except fin.ErroFinanceiro as exc:
        raise _erro(exc)
    meta = db.get(MetaMensal, competencia) or MetaMensal(competencia=competencia)
    meta.meta_toneladas = dados.meta_toneladas
    db.add(meta)
    db.commit()
    return {"competencia": competencia, "meta_toneladas": meta.meta_toneladas}


# --------------------------------------------------------------------------
# Contas a pagar
# --------------------------------------------------------------------------


class DespesaIn(BaseModel):
    escopo: Literal["empresa", "pessoal"]
    grupo: str = Field(default="Outras", max_length=80)
    descricao: str = Field(min_length=1, max_length=160)
    dia_vencimento: Optional[int] = Field(default=None, ge=1, le=31)
    valor: float = Field(default=0, ge=0)
    parcela_inicial: Optional[int] = Field(default=None, ge=1)
    parcelas_total: Optional[int] = Field(default=None, ge=1)
    competencia_inicio: str
    conta_no_resultado: bool = True
    entra_precificacao: bool = False
    ativa: bool = True
    ordem: int = 0


class AvulsaIn(BaseModel):
    escopo: Literal["empresa", "pessoal"] = "empresa"
    data: date
    descricao: str = Field(min_length=1, max_length=160)
    valor: Optional[float] = Field(default=None, ge=0)


class PagamentoIn(BaseModel):
    origem: Literal["despesa", "avulsa"]
    origem_id: int
    competencia: str
    pago_em: date
    valor: Optional[float] = Field(default=None, gt=0)
    conta_id: Optional[int] = None
    forma: str = "BOLETO"


class DesfazerIn(BaseModel):
    origem: Literal["despesa", "avulsa"]
    origem_id: int
    competencia: str


class VencidasIn(BaseModel):
    competencia: str
    ate: date


class DividaIn(BaseModel):
    credor: str = Field(min_length=1, max_length=120)
    valor_total: Optional[float] = Field(default=None, ge=0)
    parcelas_total: Optional[int] = Field(default=None, ge=1)
    parcelas_pagas: int = Field(default=0, ge=0)
    valor_parcela: Optional[float] = Field(default=None, ge=0)
    proximo_pagamento: Optional[date] = None
    observacao: str = Field(default="", max_length=300)
    quitada: bool = False
    congelada: bool = False


class PagamentoDividaIn(BaseModel):
    valor: float = Field(gt=0)
    pago_em: date
    observacao: str = Field(default="", max_length=300)
    conta_id: Optional[int] = None
    forma: str = "PIX"


@router.get("/agenda")
def ver_agenda(competencia: str, escopo: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        return fin.agenda(db, competencia, escopo=escopo)
    except fin.ErroFinanceiro as exc:
        raise _erro(exc)


@router.post("/agenda/pagar")
def pagar(dados: PagamentoIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    try:
        fin.validar_competencia(dados.competencia)
        fin.pagar(db, **dados.model_dump(), usuario=_usuario(user))
        db.commit()
    except fin.ErroFinanceiro as exc:
        db.rollback()
        raise _erro(exc)
    return fin.agenda(db, dados.competencia)


@router.post("/agenda/desfazer")
def desfazer(dados: DesfazerIn, db: Session = Depends(get_db)):
    try:
        fin.desfazer_pagamento(db, **dados.model_dump())
        db.commit()
    except fin.ErroFinanceiro as exc:
        db.rollback()
        raise _erro(exc)
    return fin.agenda(db, dados.competencia)


@router.post("/agenda/pagar-vencidas")
def pagar_vencidas(dados: VencidasIn, db: Session = Depends(get_db)):
    """Marca como pago o que ja estava atrasado ate a data, sem lancar no
    banco - pra comecar a usar a agenda no meio do mes sem 30 contas
    "atrasadas". O que vence hoje fica de fora: pode nao ter sido pago."""
    try:
        itens = fin.agenda(db, dados.competencia)["itens"]
        marcados = 0
        for item in itens:
            if item["situacao"] == "atrasado" and item["vencimento"] <= dados.ate.isoformat() and item["valor"]:
                fin.pagar(db, origem=item["origem"], origem_id=item["id"], competencia=dados.competencia,
                          pago_em=date.fromisoformat(item["vencimento"]), valor=item["valor"])
                marcados += 1
        db.commit()
    except fin.ErroFinanceiro as exc:
        db.rollback()
        raise _erro(exc)
    return {"marcados": marcados, **fin.agenda(db, dados.competencia)}


@router.get("/despesas")
def listar_despesas(competencia: str, db: Session = Depends(get_db)):
    try:
        do_mes = {d.id: parcela for d, parcela in fin.despesas_do_mes(db, competencia)}
    except fin.ErroFinanceiro as exc:
        raise _erro(exc)
    despesas = db.query(Despesa).order_by(Despesa.escopo, Despesa.ordem, Despesa.id).all()
    despesas = [d for d in despesas if fin.sem_acento(d.grupo) not in ("divida", "dividas", "dividas ativas")]
    return [
        {**fin.despesa_para_dict(d, do_mes.get(d.id)), "vale_no_mes": d.id in do_mes}
        for d in despesas
    ]


def _validar_despesa(dados: DespesaIn):
    fin.validar_competencia(dados.competencia_inicio)
    if dados.parcelas_total and dados.parcela_inicial and dados.parcela_inicial > dados.parcelas_total:
        raise fin.ErroFinanceiro("A parcela atual passa do total de parcelas")


@router.post("/despesas")
def criar_despesa(dados: DespesaIn, db: Session = Depends(get_db)):
    try:
        _validar_despesa(dados)
    except fin.ErroFinanceiro as exc:
        raise _erro(exc)
    campos = dados.model_dump()
    campos["valor"] = fin.dinheiro(campos["valor"])
    if campos["parcelas_total"] and not campos["parcela_inicial"]:
        campos["parcela_inicial"] = 1
    despesa = Despesa(**campos)
    db.add(despesa)
    db.commit()
    return fin.despesa_para_dict(despesa)


@router.put("/despesas/{despesa_id}")
def atualizar_despesa(despesa_id: int, dados: DespesaIn, db: Session = Depends(get_db)):
    despesa = db.get(Despesa, despesa_id)
    if despesa is None:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    try:
        _validar_despesa(dados)
    except fin.ErroFinanceiro as exc:
        raise _erro(exc)
    for campo, valor in dados.model_dump().items():
        setattr(despesa, campo, fin.dinheiro(valor) if campo == "valor" else valor)
    db.commit()
    return fin.despesa_para_dict(despesa)


def _conferir_sem_pagamento(db: Session, origem: str, origem_id: int) -> None:
    """Conta ja paga nao se apaga: o pagamento ficaria solto no caixa."""
    meses = [
        p.competencia for p in db.query(PagamentoAgenda)
        .filter(PagamentoAgenda.origem == origem, PagamentoAgenda.origem_id == origem_id)
        .order_by(PagamentoAgenda.competencia).all()
    ]
    if meses:
        raise HTTPException(
            status_code=400,
            detail=f"Essa conta tem pagamento lançado em {', '.join(meses)}. Desfaça o pagamento antes de excluir.",
        )


@router.delete("/despesas/{despesa_id}")
def excluir_despesa(despesa_id: int, db: Session = Depends(get_db)):
    despesa = db.get(Despesa, despesa_id)
    if despesa is None:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    _conferir_sem_pagamento(db, "despesa", despesa_id)
    db.delete(despesa)
    db.commit()
    return {"ok": True}


@router.post("/contas-avulsas")
def criar_avulsa(dados: AvulsaIn, db: Session = Depends(get_db)):
    campos = dados.model_dump()
    if campos["valor"] is not None:
        campos["valor"] = fin.dinheiro(campos["valor"])
    avulsa = ContaAvulsa(**campos)
    db.add(avulsa)
    db.commit()
    return {"id": avulsa.id}


@router.put("/contas-avulsas/{avulsa_id}")
def atualizar_avulsa(avulsa_id: int, dados: AvulsaIn, db: Session = Depends(get_db)):
    avulsa = db.get(ContaAvulsa, avulsa_id)
    if avulsa is None:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    for campo, valor in dados.model_dump().items():
        setattr(avulsa, campo, fin.dinheiro(valor) if campo == "valor" and valor is not None else valor)
    db.commit()
    return {"id": avulsa.id}


@router.delete("/contas-avulsas/{avulsa_id}")
def excluir_avulsa(avulsa_id: int, db: Session = Depends(get_db)):
    avulsa = db.get(ContaAvulsa, avulsa_id)
    if avulsa is None:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    _conferir_sem_pagamento(db, "avulsa", avulsa_id)
    db.delete(avulsa)
    db.commit()
    return {"ok": True}


def _divida_para_dict(db: Session, d: Divida, contas: Optional[dict[int, str]] = None) -> dict:
    if contas is None:
        contas = {c.id: c.nome for c in db.query(ContaBancaria).all()}
    pagamentos = fin.pagamentos_da_divida(db, d.id)
    totais = fin.totais_divida(d, pagamentos)
    return {
        "id": d.id, "credor": d.credor,
        "valor_total": fin.dinheiro(d.valor_total) if d.valor_total is not None else None,
        "parcelas_total": d.parcelas_total, "parcelas_pagas": d.parcelas_pagas,
        "valor_parcela": fin.dinheiro(d.valor_parcela) if d.valor_parcela is not None else None,
        "restante": totais["restante"], "pago": totais["pago"],
        "observacao": d.observacao, "quitada": d.quitada,
        "congelada": d.congelada,
        "proximo_pagamento": d.proximo_pagamento.isoformat() if d.proximo_pagamento else None,
        # O historico vem junto: a tela de dividas carrega tudo de uma vez e
        # abre o que foi pago sem outra ida ao servidor.
        "pagamentos": [
            {
                "id": p.id, "valor": fin.dinheiro(p.valor), "pago_em": p.pago_em.isoformat(),
                "observacao": p.observacao, "conta_id": p.conta_id, "conta": contas.get(p.conta_id or 0, ""),
                "no_caixa": p.lancamento_id is not None,
            }
            for p in pagamentos
        ],
    }


@router.get("/dividas")
def listar_dividas(db: Session = Depends(get_db)):
    # Em aberto primeiro, a que vence antes no topo; sem data no fim.
    dividas = db.query(Divida).all()
    dividas.sort(key=lambda d: (d.quitada, d.proximo_pagamento is None, d.proximo_pagamento or date.max, d.id))
    contas = {c.id: c.nome for c in db.query(ContaBancaria).all()}
    return [_divida_para_dict(db, d, contas) for d in dividas]


@router.post("/dividas")
def criar_divida(dados: DividaIn, db: Session = Depends(get_db)):
    divida = Divida(**dados.model_dump())
    db.add(divida)
    db.commit()
    return _divida_para_dict(db, divida)


@router.put("/dividas/{divida_id}")
def atualizar_divida(divida_id: int, dados: DividaIn, db: Session = Depends(get_db)):
    divida = db.get(Divida, divida_id)
    if divida is None:
        raise HTTPException(status_code=404, detail="Dívida não encontrada")
    for campo, valor in dados.model_dump().items():
        setattr(divida, campo, valor)
    db.commit()
    return _divida_para_dict(db, divida)


@router.post("/dividas/{divida_id}/parcela-paga")
def registrar_parcela(divida_id: int, db: Session = Depends(get_db)):
    """Parcela paga sem dizer quanto nem quando - o atalho de sempre. Pra
    guardar valor e data do que saiu, use /dividas/{id}/pagamentos."""
    divida = db.get(Divida, divida_id)
    if divida is None:
        raise HTTPException(status_code=404, detail="Dívida não encontrada")
    if divida.parcelas_total and divida.parcelas_pagas >= divida.parcelas_total:
        raise HTTPException(status_code=400, detail="Todas as parcelas já estão pagas")
    if divida.congelada:
        raise HTTPException(status_code=400, detail="Reative a dívida antes de registrar uma parcela")
    fin.avancar_parcela(divida)
    db.commit()
    return _divida_para_dict(db, divida)


@router.post("/dividas/{divida_id}/pagamentos")
def lancar_pagamento_divida(divida_id: int, dados: PagamentoDividaIn, db: Session = Depends(get_db),
                            user: User = Depends(require_admin)):
    if db.get(Divida, divida_id) is None:
        raise HTTPException(status_code=404, detail="Dívida não encontrada")
    campos = dados.model_dump()
    try:
        fin.registrar_pagamento_divida(
            db, divida_id=divida_id, **{**campos, "forma": (campos["forma"] or "PIX").upper()},
            usuario=_usuario(user),
        )
        db.commit()
    except fin.ErroFinanceiro as exc:
        db.rollback()
        raise _erro(exc)
    return _divida_para_dict(db, db.get(Divida, divida_id))


@router.delete("/dividas/pagamentos/{pagamento_id}")
def desfazer_pagamento_divida(pagamento_id: int, db: Session = Depends(get_db)):
    try:
        divida = fin.desfazer_pagamento_divida(db, pagamento_id)
        db.commit()
    except fin.ErroFinanceiro as exc:
        db.rollback()
        raise _erro(exc)
    if divida is None:
        return {"ok": True}
    return _divida_para_dict(db, divida)


@router.delete("/dividas/{divida_id}")
def excluir_divida(divida_id: int, db: Session = Depends(get_db)):
    divida = db.get(Divida, divida_id)
    if divida is None:
        raise HTTPException(status_code=404, detail="Dívida não encontrada")
    pagamentos = fin.pagamentos_da_divida(db, divida_id)
    # Pagamento que virou saida no banco nao se apaga por tabela: o lancamento
    # ficaria solto no caixa. O que nunca passou por conta vai junto.
    if any(p.lancamento_id for p in pagamentos):
        raise HTTPException(
            status_code=400,
            detail="Essa dívida tem pagamento lançado no Caixa. Desfaça o pagamento antes de excluir.",
        )
    for pagamento in pagamentos:
        db.delete(pagamento)
    db.delete(divida)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------
# Importar planilha
# --------------------------------------------------------------------------


@router.post("/importar-planilha")
async def importar_planilha(arquivo: UploadFile = File(...), aplicar: bool = False, competencia: Optional[str] = None,
                            db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Fluxo de Caixa ou Controle de Carregamentos. Sem `aplicar`, e so a previa."""
    conteudo = await _ler_arquivo(arquivo)
    try:
        return importacao.importar_planilha(db, conteudo, arquivo.filename or "", aplicar=aplicar,
                                            usuario=_usuario(user), competencia=competencia)
    except fin.ErroFinanceiro as exc:
        raise _erro(exc)
