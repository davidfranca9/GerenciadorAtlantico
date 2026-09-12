"""Monta e cria o CT-e no Bsoft - o mesmo caminho pra tela e pro automatico.

Ate aqui essa logica vivia dentro do endpoint /fiscal/emitir. Ela saiu de
la porque passou a ter dois chamadores: a pessoa clicando e o sistema
preparando o rascunho sozinho quando a nota chega. Um caminho so, com as
mesmas conferencias, pra nenhum dos dois sair diferente do outro.

Duas etapas, separadas de proposito:

    montar   - resolve partes, veiculos e seguro no Bsoft (so leitura) e
               devolve o payload com as pendencias. Nao grava nada.
    emitir   - registra a operacao e faz o POST. E a unica funcao deste
               modulo que cria documento do outro lado.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Agendamento, OperacaoFiscal
from . import bsoft_fiscal, cte_montagem
from .bsoft_client import BsoftEmissaoBloqueada, BsoftError, sanitizar

logger = logging.getLogger(__name__)


class Pendencias(Exception):
    """O payload nao esta pronto. `itens` lista o que falta."""

    def __init__(self, itens: list[str]):
        super().__init__("; ".join(itens))
        self.itens = itens


class JaEmitido(Exception):
    """Ja existe documento no Bsoft pra esta nota neste agendamento."""

    def __init__(self, operacao: OperacaoFiscal, rascunho: bool):
        self.operacao = operacao
        self.rascunho = rascunho
        cod = operacao.cod_conhecimento_bsoft
        if rascunho:
            mensagem = (
                f"Ja existe o rascunho {cod} no Bsoft para esta nota"
                f"{' (criado sozinho)' if operacao.solicitado_por == 'automatico' else ''}. "
                "Emita por la, ou apague o rascunho no Bsoft e tente de novo por aqui."
            )
        else:
            mensagem = f"Essa NF-e ja gerou o CT-e {operacao.cte_numero or cod}. Nao sera emitido de novo."
        super().__init__(mensagem)


class FalhaCadastros(Exception):
    """O Bsoft nao respondeu as consultas de cadastro."""


class FalhaBsoft(Exception):
    """O POST foi recusado. Pode ter criado do outro lado: sem retry."""


CAMPOS_ESCOLHA = (
    "motorista_id", "motorista_cpf", "placa_cavalo",
    "placa_carreta1", "placa_carreta2", "placa_quarto",
)


def escolhas_de(valores: dict) -> dict:
    """Junta o que foi escolhido na tela, ignorando os campos vazios."""
    return {nome: valores[nome] for nome in CAMPOS_ESCOLHA if valores.get(nome)}


def escolher_cfops_id(uf_origem: str, uf_destino: str) -> int:
    """CFOP 5352 dentro do estado, 6352 fora. Sem UF, assume interestadual."""
    origem = (uf_origem or "").strip().upper()
    destino = (uf_destino or "").strip().upper()
    if origem and destino and origem == destino:
        return settings.bsoft_cfops_id_estadual
    return settings.bsoft_cfops_id_interestadual


def resolver_apolice() -> dict:
    """Ids do seguro. Configurado por variavel vence; senao, busca pelo numero."""
    if settings.bsoft_seguradora_id:
        return {"seguradora_id": settings.bsoft_seguradora_id, "apolice_id": settings.bsoft_apolice_id}
    achada = bsoft_fiscal.buscar_apolice(settings.bsoft_numero_apolice)
    if not achada:
        return {"seguradora_id": "", "apolice_id": ""}
    return {
        "seguradora_id": str(achada.get("seguradora_id") or ""),
        "apolice_id": str(achada.get("apolice_id") or ""),
    }


def resolver_veiculos(agendamento, escolhas: dict | None = None) -> dict:
    """Traduz motorista e placas em ids do Bsoft.

    O que vier da tela vence o agendamento. Slot vazio e preenchido com
    duas fontes, nesta ordem: o cadastro do motorista (dono habitual do
    veiculo) e o ultimo CT-e com o mesmo cavalo ou motorista - que sabe
    qual carreta andou atras de qual cavalo de verdade. Devolve tambem o
    que foi procurado, pra tela poder explicar.
    """
    escolhas = escolhas or {}
    cpf = escolhas.get("motorista_cpf") or getattr(agendamento, "driver_cpf", "")
    placas = {
        "veiculo_id": escolhas.get("placa_cavalo") or getattr(agendamento, "plate_cavalo", ""),
        "carreta_id": escolhas.get("placa_carreta1") or getattr(agendamento, "plate_carreta1", ""),
        "semireboque_id": escolhas.get("placa_carreta2") or getattr(agendamento, "plate_carreta2", ""),
        # A API exige os quatro slots presentes; um rebocador comum so usa
        # dois, entao este costuma vir da tela.
        "quarto_veiculo_id": escolhas.get("placa_quarto", ""),
    }

    nome_motorista = ""
    if escolhas.get("motorista_id"):
        motorista_id = escolhas["motorista_id"]
        nome_motorista = bsoft_fiscal.nome_da_pessoa_por_id(motorista_id)
    else:
        motorista = bsoft_fiscal.buscar_pessoa(cpf) if cpf else None
        motorista_id = motorista.get("id") if motorista else None
        if motorista:
            nome_motorista = motorista.get("nome") or motorista.get("razaoSocial") or ""
    if not nome_motorista:
        nome_motorista = getattr(agendamento, "driver_name", "") or ""

    # Existir como pessoa nao basta: motorista_id so vale pra quem esta no
    # grupo de motoristas. Fora dele o Bsoft aceita o POST e deixa o campo
    # vazio - e o CT-e sai sem motorista.
    no_grupo = bsoft_fiscal.pessoa_esta_no_grupo(cpf) if (motorista_id and cpf) else None
    if no_grupo is False:
        motorista_fora_do_grupo = motorista_id
        motorista_id = None
    else:
        motorista_fora_do_grupo = None

    placas_do_motorista = {}
    placas_fonte = ""
    slots = (("veiculo_id", "placa_cavalo"), ("carreta_id", "placa_carreta1"), ("semireboque_id", "placa_carreta2"))
    if not all(placas[c] for c in ("veiculo_id", "carreta_id")):
        fontes = []
        if motorista_id:
            fontes.append(("cadastro do motorista", bsoft_fiscal.veiculos_do_motorista(cpf=cpf, nome=nome_motorista)))
        historico = bsoft_fiscal.placas_do_ultimo_cte(placa_cavalo=placas["veiculo_id"], motorista_nome=nome_motorista)
        if historico.get("fonte"):
            fontes.append((historico["fonte"], historico))
        for nome_fonte, achado in fontes:
            for campo, slot in slots:
                if not placas[campo] and achado.get(slot):
                    placas[campo] = achado[slot]
                    placas_do_motorista[campo] = achado[slot]
                    placas_fonte = placas_fonte or nome_fonte

    # O conjunto do motorista, quando existe, e o caminho curto: a API nao
    # pede nenhum campo de veiculo junto dele. Sem conjunto ela cobra os
    # cinco, um erro por vez.
    conjunto = bsoft_fiscal.buscar_conjunto_por_cpf(cpf) if cpf else None

    encontrados = {
        "procurou": dict(placas, motorista_cpf=cpf, motorista_nome=nome_motorista),
        "placas_do_motorista": placas_do_motorista,
        "placas_fonte": placas_fonte,
        "motorista_id": motorista_id,
        "motorista_fora_do_grupo": motorista_fora_do_grupo,
        "conjunto": conjunto,
    }
    for campo, placa in placas.items():
        veiculo = bsoft_fiscal.buscar_veiculo_por_placa(placa) if placa else None
        encontrados[campo] = veiculo.get("id") if veiculo else None
    return encontrados


def montar(
    espelho: dict,
    agendamento: Agendamento | None,
    *,
    escolhas: dict | None = None,
    aliquota_icms: str = "",
    km: str = "",
    forma_pagamento: str = "",
    conjunto_veiculos_id: str = "",
    endereco_remetente_id: str = "",
    endereco_destinatario_id: str = "",
    rascunho: bool = True,
    buscar_pessoa=None,
    listar_enderecos=None,
    resolver_veiculos_fn=None,
    resolver_apolice_fn=None,
) -> dict:
    """LEITURA no Bsoft. Devolve partes, veiculos, payload e pendencias.

    As buscas entram por parametro pra dar pra testar sem tocar na API.
    """
    buscar_pessoa = buscar_pessoa or bsoft_fiscal.buscar_pessoa
    listar_enderecos = listar_enderecos or bsoft_fiscal.listar_enderecos
    resolver_veiculos_fn = resolver_veiculos_fn or resolver_veiculos
    resolver_apolice_fn = resolver_apolice_fn or resolver_apolice

    try:
        partes = cte_montagem.resolver_partes(
            espelho,
            buscar_pessoa=buscar_pessoa,
            listar_enderecos=listar_enderecos,
            endereco_remetente_id=endereco_remetente_id or None,
            endereco_destinatario_id=endereco_destinatario_id or None,
        )
        veiculos = resolver_veiculos_fn(agendamento, escolhas or {})
        seguro = resolver_apolice_fn()
    except BsoftError as exc:
        raise FalhaCadastros(f"Falha ao consultar cadastros: {exc}") from exc

    # Conjunto escolhido na tela vence; senao, o do proprio motorista.
    conjunto_veiculos_id = conjunto_veiculos_id or str((veiculos.get("conjunto") or {}).get("id") or "")

    cte_montagem.completar_percurso(espelho, partes)
    cfops_id = escolher_cfops_id(espelho.get("uf_origem", ""), espelho.get("uf_destino", ""))
    corpo = cte_montagem.montar_payload_conhecimento(
        espelho,
        partes=partes,
        veiculos=veiculos,
        aliquota_icms=aliquota_icms or None,
        rascunho=rascunho,
        cfops_id=cfops_id,
        km=km,
        forma_pagamento=forma_pagamento,
        conjunto_veiculos_id=conjunto_veiculos_id,
        **seguro,
    )
    pendencias = partes["pendencias"] + cte_montagem.conferir_payload(corpo)
    if veiculos.get("motorista_fora_do_grupo"):
        nome = (veiculos.get("procurou") or {}).get("motorista_nome") or "o motorista"
        pendencias = [
            p for p in pendencias if not p.startswith("Motorista nao encontrado")
        ] + [
            f"{nome} esta no cadastro do Bsoft, mas nao no grupo de motoristas. "
            "Abra o cadastro dele no Bsoft e marque o grupo 'motoristas'; sem isso o CT-e sai sem motorista."
        ]
    return {
        "partes": partes,
        "veiculos": veiculos,
        "cfops_id": cfops_id,
        "corpo": corpo,
        "pendencias": pendencias,
    }


def rascunho_no_bsoft(operacao: OperacaoFiscal) -> bool:
    """O documento que esta operacao criou e um rascunho?

    A operacao nao guarda isso em coluna propria; esta no payload enviado
    (rascunho = "S") e continua valendo enquanto a SEFAZ nao autorizar.
    """
    if operacao.cte_chave:
        return False
    try:
        return json.loads(operacao.ultimo_payload or "{}").get("rascunho") == "S"
    except ValueError:
        return False


def operacao_existente(db: Session, agendamento_id: int, chave: str) -> OperacaoFiscal | None:
    return (
        db.query(OperacaoFiscal)
        .filter(OperacaoFiscal.agendamento_id == agendamento_id, OperacaoFiscal.chave_nfe == chave)
        .one_or_none()
    )


def emitir(
    db: Session,
    *,
    corpo: dict,
    chave: str,
    agendamento_id: int,
    solicitado_por: str,
    rascunho: bool,
    criar=None,
) -> OperacaoFiscal:
    """ESCRITA no Bsoft. Cria o CT-e (rascunho ou definitivo).

    Uma operacao por (agendamento, nota): e o que impede emitir duas vezes
    a mesma carga. Documento ja criado - rascunho ou nao - recusa aqui,
    antes de qualquer requisicao, porque a API do Bsoft nao tem como
    promover um rascunho a definitivo: um segundo POST criaria outro
    documento.
    """
    criar = criar or bsoft_fiscal.criar_conhecimento

    operacao = operacao_existente(db, agendamento_id, chave)
    if operacao and operacao.cod_conhecimento_bsoft:
        raise JaEmitido(operacao, rascunho_no_bsoft(operacao))
    if operacao is None:
        operacao = OperacaoFiscal(agendamento_id=agendamento_id, chave_nfe=chave, status="RASCUNHO")
        db.add(operacao)

    operacao.ultimo_payload = json.dumps(sanitizar(corpo))[:4000]
    operacao.tentativas = (operacao.tentativas or 0) + 1
    operacao.solicitado_por = solicitado_por
    operacao.status = "ENVIANDO_CTE"
    db.commit()

    try:
        resposta = criar(corpo)
    except BsoftEmissaoBloqueada as exc:
        operacao.status = "RASCUNHO"
        operacao.erro = str(exc)[:1000]
        db.commit()
        raise
    except BsoftError as exc:
        # Sem retry automatico: pode ter criado do outro lado.
        operacao.status = "CTE_REJEITADO"
        operacao.erro = str(exc)[:1000]
        db.commit()
        logger.warning("Falha ao criar CT-e do agendamento %s: %s", agendamento_id, exc)
        raise FalhaBsoft(str(exc)) from exc

    operacao.cod_conhecimento_bsoft = str(resposta.get("codConhecimentos", ""))
    operacao.ultima_resposta = json.dumps(sanitizar(resposta))[:4000]
    operacao.status = "CTE_CRIADO"
    operacao.erro = ""
    operacao.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(operacao)
    return operacao
