"""Emissao de CT-e a partir de um agendamento, via API do Bsoft.

Fluxo: agendamento + XML da NF-e -> operacao fiscal (rascunho local) ->
importa a NF-e no Bsoft -> cria o CT-e pelo viaNFe -> acompanha o status.

Protecoes da operacao:
1. `settings.bsoft_emissao_habilitada` - com ela desligada, nenhuma chamada
   de escrita sai do processo. Hoje ligada, por autorizacao do responsavel;
   pra desligar sem deploy, BSOFT_EMISSAO_HABILITADA=false.
2. Indice unico (agendamento_id, chave_nfe) - impede emitir dois CT-e pra
   mesma carga, mesmo com clique duplo ou retry.
3. Payload incompleto e recusado antes do envio, e o CT-e sai como rascunho
   a menos que alguem marque a emissao definitiva.

O endpoint /simular monta e devolve o payload exato que seria enviado, sem
chamar nada. E como se valida o mapeamento antes de existir risco fiscal.
"""
from __future__ import annotations

import json
import logging
from xml.etree import ElementTree

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import Agendamento, OperacaoFiscal, User
from ..servicos import bsoft_fiscal, cte_montagem, nfe_xml
from ..servicos.bsoft_client import BsoftEmissaoBloqueada, BsoftError, sanitizar

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fiscal", tags=["fiscal"], dependencies=[Depends(get_current_user)])


def _to_dict(op: OperacaoFiscal) -> dict:
    return {
        "id": op.id,
        "agendamento_id": op.agendamento_id,
        "status": op.status,
        "chave_nfe": op.chave_nfe,
        "cod_nfe_bsoft": op.cod_nfe_bsoft,
        "cod_conhecimento_bsoft": op.cod_conhecimento_bsoft,
        "cte_numero": op.cte_numero,
        "cte_chave": op.cte_chave,
        "cte_protocolo": op.cte_protocolo,
        "cte_motivo_rejeicao": op.cte_motivo_rejeicao,
        "ciot": op.ciot,
        "erro": op.erro,
        "tentativas": op.tentativas,
        "solicitado_por": op.solicitado_por,
        "created_at": op.created_at,
        "updated_at": op.updated_at,
    }


def montar_payload_cte(
    *, chave_nfe: str, parametro_criacao_cte: str, valor_frete: float, cod_nfe: str = ""
) -> dict:
    """Monta o corpo do POST /conhecimentos/viaNFe.

    Funcao pura de proposito: nao chama nada, so traduz os dados da operacao
    pro formato do Bsoft. E o que o /simular devolve.
    """
    valor = f"{float(valor_frete):.2f}"
    corpo = {
        "parametroCriacaoCTe": str(parametro_criacao_cte),
        "tipoRateio": "P",
        "composicaoFrete": "M",
        "valorFrete": valor,
        "baseCalculo": valor,
        "totalServico": valor,
        "totalPrestacao": valor,
        "valorSeguroAduaneiro": "0.00",
        "diaria": "0.00",
        "valoresOutros": "0.00",
        "valorPedagioConhecimento": "0.00",
        "valorSeguro": "0.00",
        "gris": "0.00",
    }
    # A chave tem prioridade: quando informada, o Bsoft ignora "ids".
    if chave_nfe:
        corpo["chavesNFe"] = [chave_nfe]
    elif cod_nfe:
        corpo["ids"] = [str(cod_nfe)]
    return corpo


def escolher_cfops_id(uf_origem: str, uf_destino: str) -> int:
    """Natureza da operacao (cfops_id no Bsoft): CFOP 5352 quando a prestacao
    fica dentro do estado, 6352 quando cruza a divisa. Sem as duas UFs, cai
    no interestadual, que e o caso mais comum da operacao."""
    origem = (uf_origem or "").strip().upper()
    destino = (uf_destino or "").strip().upper()
    if origem and destino and origem == destino:
        return settings.bsoft_cfops_id_estadual
    return settings.bsoft_cfops_id_interestadual


class SimularIn(BaseModel):
    agendamento_id: int
    chave_nfe: str = ""
    valor_frete: float = 0
    parametro_criacao_cte: str = ""


@router.post("/simular")
def simular(payload: SimularIn, db: Session = Depends(get_db)):
    """Nao chama o Bsoft. Devolve o payload exato que seria enviado, junto
    com o que ainda falta pra emitir de verdade."""
    agendamento = db.get(Agendamento, payload.agendamento_id)
    if agendamento is None:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado")

    chave = "".join(filter(str.isdigit, payload.chave_nfe or ""))
    parametro = payload.parametro_criacao_cte or settings.bsoft_parametro_criacao_cte
    pendencias = []
    if not parametro:
        pendencias.append(
            "Parametro de Criacao de CT-e nao informado. O cadastro paramCriaCteViaNFe "
            "esta vazio no Bsoft e precisa ser configurado la (pergunta 1.6 do suporte)."
        )
    if not chave:
        pendencias.append("Chave da NF-e nao informada.")
    elif not nfe_xml.chave_valida(chave):
        pendencias.append("Chave da NF-e invalida (digito verificador nao confere).")
    if payload.valor_frete <= 0:
        pendencias.append("Valor do frete precisa ser maior que zero.")
    if not settings.bsoft_emissao_habilitada:
        pendencias.append(
            "Emissao desligada por configuracao (BSOFT_EMISSAO_HABILITADA=false)."
        )

    return {
        "endpoint": "POST /transporte/v1/conhecimentos/viaNFe",
        "payload": montar_payload_cte(
            chave_nfe=chave,
            parametro_criacao_cte=parametro or "<FALTA CONFIGURAR>",
            valor_frete=payload.valor_frete,
        ),
        "ids_do_tenant": {
            "agencia": settings.bsoft_agencia_id,
            "talao_cte": settings.bsoft_talao_cte_id,
            "regra_frete": settings.bsoft_regra_frete_id,
            "apolice": settings.bsoft_numero_apolice,
            "natureza_carga": settings.bsoft_natureza_carga_id,
            "cfops_estadual": f"{settings.bsoft_cfops_id_estadual} (CFOP 5352)",
            "cfops_interestadual": f"{settings.bsoft_cfops_id_interestadual} (CFOP 6352)",
        },
        "agendamento": {
            "id": agendamento.id,
            "fornecedor": agendamento.supplier,
            "data": agendamento.loading_date,
            "motorista": agendamento.driver_name,
            "placa": agendamento.plate_cavalo,
            "toneladas": agendamento.total_tons,
        },
        "pendencias": pendencias,
        "pronto_para_emitir": not pendencias,
    }


@router.post("/espelho")
async def espelho_do_cte(
    arquivo: UploadFile,
    tarifa_por_tonelada: str = Form(""),
    embalagem: str = Form(""),
    buscar_partes: bool = Form(False),
    especie_id: str = Form(""),
    aliquota_icms: str = Form(""),
    km: str = Form(""),
    forma_pagamento: str = Form(""),
    conjunto_veiculos_id: str = Form(""),
    endereco_remetente_id: str = Form(""),
    endereco_destinatario_id: str = Form(""),
    motorista_id: str = Form(""),
    motorista_cpf: str = Form(""),
    placa_cavalo: str = Form(""),
    placa_carreta1: str = Form(""),
    placa_carreta2: str = Form(""),
    agendamento_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    """Le o XML da NF-e e mostra como o CT-e sairia.

    Serve pra conferir contra um DACTE real antes de emitir qualquer coisa:
    e o mesmo caminho validado no teste dourado do CT-e 5053.

    Com buscar_partes, consulta os ids de pessoa, endereco, motorista e
    veiculo no cadastro do Bsoft e monta o payload completo do
    POST /conhecimentos. Continua sendo so leitura - nada e criado la, e o
    payload sai como rascunho.
    """
    agendamento = db.get(Agendamento, agendamento_id) if agendamento_id else None
    conteudo = await arquivo.read()
    try:
        resultado = cte_montagem.derivar(
            conteudo,
            tarifa_por_tonelada=tarifa_por_tonelada or None,
            embalagem=embalagem,
            especie_id=especie_id or None,
        )
    except nfe_xml.NFeInvalida as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ElementTree.ParseError as exc:
        raise HTTPException(status_code=400, detail=f"XML ilegivel: {exc}")

    cfops_id = escolher_cfops_id(resultado["uf_origem"], resultado["uf_destino"])
    resultado["cfops_id"] = cfops_id
    resultado["cfop"] = "5352" if cfops_id == settings.bsoft_cfops_id_estadual else "6352"
    resultado["regra_frete_id"] = settings.bsoft_regra_frete_id
    resultado["apolice"] = settings.bsoft_numero_apolice

    if not buscar_partes:
        return resultado

    # Daqui pra baixo consulta o Bsoft, sempre em leitura. Falha aqui nao
    # derruba o espelho: o resto do documento continua util pra conferencia.
    try:
        partes = await run_in_threadpool(
            cte_montagem.resolver_partes,
            resultado,
            buscar_pessoa=bsoft_fiscal.buscar_pessoa,
            listar_enderecos=bsoft_fiscal.listar_enderecos,
            endereco_remetente_id=endereco_remetente_id or None,
            endereco_destinatario_id=endereco_destinatario_id or None,
        )
        veiculos = await run_in_threadpool(_resolver_veiculos, agendamento, _escolhas(locals()))
        seguro = await run_in_threadpool(_resolver_apolice)
    except BsoftError as exc:
        resultado["partes"] = {"erro": str(exc)}
        resultado["pendencias"] = resultado["pendencias"] + [
            f"Nao foi possivel consultar os cadastros no Bsoft: {exc}"
        ]
        return resultado

    resultado["partes"] = partes
    resultado["veiculos"] = veiculos
    corpo = cte_montagem.montar_payload_conhecimento(
        resultado,
        partes=partes,
        veiculos=veiculos,
        aliquota_icms=aliquota_icms or None,
        cfops_id=cfops_id,
        km=km,
        forma_pagamento=forma_pagamento,
        conjunto_veiculos_id=conjunto_veiculos_id,
        **seguro,
    )
    resultado["endpoint"] = "POST /transporte/v1/conhecimentos"
    resultado["payload"] = corpo
    resultado["pendencias"] = (
        resultado["pendencias"] + partes["pendencias"] + cte_montagem.conferir_payload(corpo)
    )
    return resultado


def _resolver_apolice() -> dict:
    """Ids do seguro. Configurado por variavel vence; senao, busca pelo numero.

    O numero da apolice ja e conhecido (202511, conferido no DACTE 5053),
    entao nao faz sentido pedir o id na mao: a consulta resolve.
    """
    if settings.bsoft_seguradora_id:
        return {
            "seguradora_id": settings.bsoft_seguradora_id,
            "apolice_id": settings.bsoft_apolice_id,
        }
    achada = bsoft_fiscal.buscar_apolice(settings.bsoft_numero_apolice)
    if not achada:
        return {"seguradora_id": "", "apolice_id": ""}
    return {
        "seguradora_id": str(achada.get("seguradora_id") or ""),
        "apolice_id": str(achada.get("apolice_id") or ""),
    }


CAMPOS_ESCOLHA = (
    "motorista_id", "motorista_cpf", "placa_cavalo",
    "placa_carreta1", "placa_carreta2",
)


def _escolhas(valores: dict) -> dict:
    """Junta o que foi escolhido na tela, ignorando os campos vazios."""
    return {nome: valores[nome] for nome in CAMPOS_ESCOLHA if valores.get(nome)}


def _resolver_veiculos(agendamento, escolhas: dict | None = None) -> dict:
    """Traduz motorista e placas em ids do Bsoft.

    O que vier da tela vence o agendamento: quando o cadastro nao e achado
    pela placa ou pelo CPF, quem opera corrige ali em vez de ficar travado.
    Devolve tambem o que foi procurado, pra tela poder explicar a falha.
    """
    escolhas = escolhas or {}
    cpf = escolhas.get("motorista_cpf") or getattr(agendamento, "driver_cpf", "")
    placas = {
        "veiculo_id": escolhas.get("placa_cavalo") or getattr(agendamento, "plate_cavalo", ""),
        "carreta_id": escolhas.get("placa_carreta1") or getattr(agendamento, "plate_carreta1", ""),
        "semireboque_id": escolhas.get("placa_carreta2") or getattr(agendamento, "plate_carreta2", ""),
    }
    encontrados = {"procurou": dict(placas, motorista_cpf=cpf)}

    if escolhas.get("motorista_id"):
        encontrados["motorista_id"] = escolhas["motorista_id"]
    else:
        motorista = bsoft_fiscal.buscar_pessoa(cpf) if cpf else None
        encontrados["motorista_id"] = motorista.get("id") if motorista else None

    for campo, placa in placas.items():
        veiculo = bsoft_fiscal.buscar_veiculo_por_placa(placa) if placa else None
        encontrados[campo] = veiculo.get("id") if veiculo else None
    return encontrados


@router.post("/emitir")
async def emitir_conhecimento(
    arquivo: UploadFile,
    agendamento_id: int = Form(...),
    tarifa_por_tonelada: str = Form(...),
    aliquota_icms: str = Form(...),
    km: str = Form(""),
    forma_pagamento: str = Form(""),
    conjunto_veiculos_id: str = Form(""),
    embalagem: str = Form(""),
    especie_id: str = Form(""),
    endereco_remetente_id: str = Form(""),
    endereco_destinatario_id: str = Form(""),
    motorista_id: str = Form(""),
    motorista_cpf: str = Form(""),
    placa_cavalo: str = Form(""),
    placa_carreta1: str = Form(""),
    placa_carreta2: str = Form(""),
    confirmar_emissao_real: bool = Form(False),
    db: Session = Depends(get_db),
    usuario: User = Depends(get_current_user),
):
    """Cria o CT-e pelo payload completo do POST /conhecimentos.

    Por padrao cria RASCUNHO. So manda documento definitivo com
    confirmar_emissao_real, e mesmo assim a trava
    settings.bsoft_emissao_habilitada precisa estar ligada - com ela
    desligada, nenhuma requisicao sai daqui.
    """
    agendamento = db.get(Agendamento, agendamento_id)
    if agendamento is None:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado")

    conteudo = await arquivo.read()
    try:
        espelho = cte_montagem.derivar(
            conteudo,
            tarifa_por_tonelada=tarifa_por_tonelada,
            embalagem=embalagem,
            especie_id=especie_id or None,
        )
    except nfe_xml.NFeInvalida as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ElementTree.ParseError as exc:
        raise HTTPException(status_code=400, detail=f"XML ilegivel: {exc}")

    chave = espelho["chaves_nfe"][0]
    # Protecao contra emissao duplicada: o indice unico
    # (agendamento_id, chave_nfe) garante uma operacao por carga.
    operacao = (
        db.query(OperacaoFiscal)
        .filter(OperacaoFiscal.agendamento_id == agendamento_id, OperacaoFiscal.chave_nfe == chave)
        .one_or_none()
    )
    if operacao and operacao.cod_conhecimento_bsoft:
        raise HTTPException(
            status_code=409,
            detail=f"Essa NF-e ja gerou o CT-e {operacao.cod_conhecimento_bsoft}. Nao sera emitido de novo.",
        )
    if operacao is None:
        operacao = OperacaoFiscal(agendamento_id=agendamento_id, chave_nfe=chave, status="RASCUNHO")
        db.add(operacao)

    try:
        partes = await run_in_threadpool(
            cte_montagem.resolver_partes,
            espelho,
            buscar_pessoa=bsoft_fiscal.buscar_pessoa,
            listar_enderecos=bsoft_fiscal.listar_enderecos,
            endereco_remetente_id=endereco_remetente_id or None,
            endereco_destinatario_id=endereco_destinatario_id or None,
        )
        veiculos = await run_in_threadpool(_resolver_veiculos, agendamento, _escolhas(locals()))
        seguro = await run_in_threadpool(_resolver_apolice)
    except BsoftError as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao consultar cadastros: {exc}")

    corpo = cte_montagem.montar_payload_conhecimento(
        espelho,
        partes=partes,
        veiculos=veiculos,
        aliquota_icms=aliquota_icms,
        rascunho=not confirmar_emissao_real,
        cfops_id=escolher_cfops_id(espelho["uf_origem"], espelho["uf_destino"]),
        km=km,
        forma_pagamento=forma_pagamento,
        conjunto_veiculos_id=conjunto_veiculos_id,
        **seguro,
    )

    # Payload incompleto nao vai pra frente: melhor recusar aqui do que
    # deixar o Bsoft criar um documento torto.
    pendencias = partes["pendencias"] + cte_montagem.conferir_payload(corpo)
    if pendencias:
        raise HTTPException(status_code=400, detail={"pendencias": pendencias})

    operacao.ultimo_payload = json.dumps(sanitizar(corpo))[:4000]
    operacao.tentativas += 1
    operacao.solicitado_por = usuario.email
    operacao.status = "ENVIANDO_CTE"
    db.commit()

    try:
        resposta = await run_in_threadpool(bsoft_fiscal.criar_conhecimento, corpo)
    except BsoftEmissaoBloqueada as exc:
        operacao.status = "RASCUNHO"
        operacao.erro = str(exc)[:1000]
        db.commit()
        raise HTTPException(status_code=409, detail=str(exc))
    except BsoftError as exc:
        # Sem retry automatico: pode ter criado do outro lado.
        operacao.status = "CTE_REJEITADO"
        operacao.erro = str(exc)[:1000]
        db.commit()
        logger.warning("Falha ao criar CT-e do agendamento %s: %s", agendamento_id, exc)
        raise HTTPException(status_code=502, detail=str(exc))

    operacao.cod_conhecimento_bsoft = str(resposta.get("codConhecimentos", ""))
    operacao.ultima_resposta = json.dumps(sanitizar(resposta))[:4000]
    operacao.status = "CTE_CRIADO"
    operacao.erro = ""
    db.commit()
    db.refresh(operacao)
    return {"operacao": _to_dict(operacao), "rascunho": not confirmar_emissao_real}


@router.get("/nfes-recebidas")
async def listar_nfes_recebidas(data_inicio: str, data_fim: str, ator: str = "TRA"):
    """LEITURA. Chaves das NF-e recebidas no periodo (maximo 3 meses).

    Serve pra achar uma nota que ainda nao virou CT-e: o Bsoft recusa
    emitir duas vezes sobre a mesma NF-e.
    """
    try:
        chaves = await run_in_threadpool(
            bsoft_fiscal.listar_chaves_nfes_recebidas, data_inicio, data_fim, ator
        )
    except BsoftError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"chaves": chaves}


@router.get("/nfe-xml")
async def baixar_xml_nfe(chave: str):
    """LEITURA. XML de uma NF-e recebida, pelo numero da chave."""
    limpa = "".join(filter(str.isdigit, chave or ""))
    if len(limpa) != 44:
        raise HTTPException(status_code=400, detail="Informe a chave da NF-e (44 digitos)")
    try:
        return {"xml": await run_in_threadpool(bsoft_fiscal.obter_xml_nfes_recebidas, [limpa])}
    except BsoftError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/motoristas")
async def procurar_motoristas(nome: str = ""):
    """LEITURA. Busca motorista pelo nome no cadastro do Bsoft.

    E a lupa da tela: quando o CPF do agendamento nao acha ninguem, da pra
    achar a pessoa pelo nome e usar o id dela.
    """
    if len((nome or "").strip()) < 3:
        return {"resultados": [], "aviso": "Digite ao menos 3 letras do nome."}
    try:
        resultados = await run_in_threadpool(bsoft_fiscal.buscar_pessoas_por_nome, nome)
    except BsoftError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"resultados": resultados}


@router.get("/veiculos")
async def procurar_veiculos(placa: str = ""):
    """LEITURA. Busca veiculo por parte da placa."""
    alvo = "".join(c for c in (placa or "").upper() if c.isalnum())
    if len(alvo) < 3:
        return {"resultados": [], "aviso": "Digite ao menos 3 caracteres da placa."}
    try:
        todos = await run_in_threadpool(bsoft_fiscal._todos_os_veiculos)
    except BsoftError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    resultados = [
        {"id": v.get("id"), "placa": v.get("placa")}
        for v in todos
        if alvo in "".join(c for c in str(v.get("placa", "")).upper() if c.isalnum())
    ][:25]
    return {"resultados": resultados}


class ConferirIn(BaseModel):
    chave_cte: str
    valor_frete: float = 0


@router.post("/conferir")
async def conferir_contra_cte_real(payload: ConferirIn):
    """Somente leitura. Busca o XML autorizado de um CT-e ja emitido por
    voces e devolve os valores que a SEFAZ registrou, pra comparar com o que
    o sistema montaria.

    E assim que se prova que a emissao pelo sistema sai igual a manual:
    reproduz um documento real e confere campo a campo, sem emitir nada.
    """
    chave = "".join(filter(str.isdigit, payload.chave_cte or ""))
    if len(chave) != 44:
        raise HTTPException(status_code=400, detail="Informe a chave de acesso do CT-e (44 digitos)")

    try:
        xml = await run_in_threadpool(bsoft_fiscal.obter_xml_ctes_emitidos, [chave])
    except BsoftError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {
        "chave_consultada": chave,
        "xml_autorizado": xml,
        "ids_que_o_sistema_usaria": {
            "agencia": settings.bsoft_agencia_id,
            "talao_cte": settings.bsoft_talao_cte_id,
            "regra_frete": settings.bsoft_regra_frete_id,
            "natureza_carga": settings.bsoft_natureza_carga_id,
            "apolice": settings.bsoft_numero_apolice,
            "resp_seguro": "4 (emitente)",
            "tipo_documentos": "N (NF-e)",
            "cte_os": "N",
        },
        "observacao": (
            "Compare os valores do XML autorizado com o que o sistema montaria "
            "para a mesma NF-e. Divergencia aqui e erro de mapeamento e precisa "
            "ser corrigida antes de qualquer emissao real."
        ),
    }


@router.get("/operacoes")
def listar_operacoes(db: Session = Depends(get_db)):
    operacoes = db.query(OperacaoFiscal).order_by(OperacaoFiscal.created_at.desc()).limit(200).all()
    return [_to_dict(op) for op in operacoes]


@router.post("/operacoes/nfe")
async def importar_nfe(
    agendamento_id: int = Form(...),
    arquivo: UploadFile = None,
    db: Session = Depends(get_db),
    usuario: User = Depends(get_current_user),
):
    """Le o XML da NF-e, valida localmente e cria/reaproveita a operacao.
    So chama o Bsoft se a emissao estiver habilitada."""
    if arquivo is None:
        raise HTTPException(status_code=400, detail="Envie o XML da NF-e")
    if db.get(Agendamento, agendamento_id) is None:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado")

    conteudo = await arquivo.read()
    try:
        dados_nfe = nfe_xml.extrair_dados(conteudo)
    except nfe_xml.NFeInvalida as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    operacao = (
        db.query(OperacaoFiscal)
        .filter(
            OperacaoFiscal.agendamento_id == agendamento_id,
            OperacaoFiscal.chave_nfe == dados_nfe["chave"],
        )
        .first()
    )
    if operacao is None:
        operacao = OperacaoFiscal(
            agendamento_id=agendamento_id,
            chave_nfe=dados_nfe["chave"],
            status="RASCUNHO",
            solicitado_por=usuario.email,
        )
        db.add(operacao)
        db.commit()
        db.refresh(operacao)
    elif operacao.cod_conhecimento_bsoft:
        raise HTTPException(
            status_code=409,
            detail=f"Ja existe CT-e emitido para essa NF-e nesse agendamento (operacao #{operacao.id})",
        )

    if not settings.bsoft_emissao_habilitada:
        return {**_to_dict(operacao), "nfe": dados_nfe, "aviso": "Emissao desligada: NF-e nao foi enviada ao Bsoft."}

    try:
        resposta = await run_in_threadpool(bsoft_fiscal.importar_nfe_por_xml, conteudo)
        operacao.cod_nfe_bsoft = str(resposta.get("codNFe", ""))
        operacao.ultima_resposta = json.dumps(sanitizar(resposta))[:4000]
        operacao.erro = ""
    except (BsoftError, BsoftEmissaoBloqueada) as exc:
        operacao.erro = str(exc)[:1000]
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc))
    db.commit()
    db.refresh(operacao)
    return {**_to_dict(operacao), "nfe": dados_nfe}


class EmitirCteIn(BaseModel):
    valor_frete: float
    # Cai pro configurado em settings quando nao vier no corpo.
    parametro_criacao_cte: str = ""


@router.post("/operacoes/{operacao_id}/cte")
async def emitir_cte(
    operacao_id: int,
    payload: EmitirCteIn,
    db: Session = Depends(get_db),
    usuario: User = Depends(get_current_user),
):
    """Cria o CT-e no Bsoft a partir da NF-e ja vinculada."""
    operacao = db.get(OperacaoFiscal, operacao_id)
    if operacao is None:
        raise HTTPException(status_code=404, detail="Operacao nao encontrada")
    if operacao.cod_conhecimento_bsoft:
        raise HTTPException(
            status_code=409,
            detail=f"Essa operacao ja tem CT-e ({operacao.cod_conhecimento_bsoft}). Nao sera emitido de novo.",
        )
    if payload.valor_frete <= 0:
        raise HTTPException(status_code=400, detail="Valor do frete precisa ser maior que zero")

    parametro = payload.parametro_criacao_cte or settings.bsoft_parametro_criacao_cte
    if not parametro:
        raise HTTPException(
            status_code=400,
            detail="Parametro de Criacao de CT-e nao configurado (BSOFT_PARAMETRO_CRIACAO_CTE). "
                   "Ele precisa existir no Bsoft antes de emitir.",
        )
    corpo = montar_payload_cte(
        chave_nfe=operacao.chave_nfe,
        cod_nfe=operacao.cod_nfe_bsoft,
        parametro_criacao_cte=parametro,
        valor_frete=payload.valor_frete,
    )
    operacao.ultimo_payload = json.dumps(sanitizar(corpo))[:4000]
    operacao.tentativas += 1
    operacao.solicitado_por = usuario.email
    operacao.status = "ENVIANDO_CTE"
    db.commit()

    try:
        resposta = await run_in_threadpool(
            bsoft_fiscal.criar_cte_via_nfe,
            parametro_criacao_cte=parametro,
            chaves_nfe=[operacao.chave_nfe] if operacao.chave_nfe else None,
            ids_nfe=[operacao.cod_nfe_bsoft] if operacao.cod_nfe_bsoft else None,
            valores={k: v for k, v in corpo.items() if k not in ("chavesNFe", "ids", "parametroCriacaoCTe")},
        )
    except BsoftEmissaoBloqueada as exc:
        operacao.status = "RASCUNHO"
        operacao.erro = str(exc)[:1000]
        db.commit()
        raise HTTPException(status_code=409, detail=str(exc))
    except BsoftError as exc:
        # Sem retry automatico: pode ter criado do outro lado. O status
        # fica explicito pra alguem consultar antes de tentar de novo.
        operacao.status = "CTE_REJEITADO"
        operacao.erro = str(exc)[:1000]
        db.commit()
        logger.warning("Falha ao emitir CT-e da operacao %s: %s", operacao.id, exc)
        raise HTTPException(status_code=502, detail=str(exc))

    operacao.cod_conhecimento_bsoft = str(resposta.get("codConhecimentos", ""))
    operacao.ultima_resposta = json.dumps(sanitizar(resposta))[:4000]
    operacao.status = "CTE_CRIADO"
    operacao.erro = ""
    db.commit()
    db.refresh(operacao)
    return _to_dict(operacao)


@router.get("/operacoes/{operacao_id}/status")
async def consultar_status(operacao_id: int, db: Session = Depends(get_db)):
    """Consulta o CT-e no Bsoft e atualiza chave, protocolo e rejeicao."""
    operacao = db.get(OperacaoFiscal, operacao_id)
    if operacao is None:
        raise HTTPException(status_code=404, detail="Operacao nao encontrada")
    if not operacao.cod_conhecimento_bsoft:
        return {**_to_dict(operacao), "aviso": "Operacao ainda nao tem CT-e criado."}

    try:
        dados = await run_in_threadpool(bsoft_fiscal.obter_conhecimento, operacao.cod_conhecimento_bsoft)
    except BsoftError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    operacao.cte_numero = str(dados.get("nro") or operacao.cte_numero)
    operacao.cte_chave = str(dados.get("chaveAcesso") or operacao.cte_chave)
    operacao.cte_protocolo = str(dados.get("protocoloAverbacao") or operacao.cte_protocolo)
    if operacao.cte_chave:
        operacao.status = "CTE_AUTORIZADO"
    db.commit()
    db.refresh(operacao)
    return {**_to_dict(operacao), "bsoft": dados}
