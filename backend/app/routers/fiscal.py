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
from datetime import datetime
from xml.etree import ElementTree

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import Agendamento, EstadoSefaz, NotaFiscalRecebida, OperacaoFiscal, User
from ..servicos import bsoft_fiscal, cte_montagem, emissao_cte, nfe_xml, notas_recebidas, sefaz_nfe
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


# A regra do CFOP (5352 dentro do estado, 6352 fora) mora no servico de
# emissao, que a tela e o rascunho automatico compartilham.
escolher_cfops_id = emissao_cte.escolher_cfops_id


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


# --------------------------------------------------------------------------
# De onde vem a NF-e
#
# Sao tres caminhos, porque a nota chega de tres jeitos na pratica:
#
#   xml       - o arquivo que a fabrica mandou, enviado na tela
#   recebida  - uma das notas que o sistema ja coletou sozinho (e-mail ou
#               SEFAZ); a tela lista e quem opera so escolhe
#   manual    - nenhum arquivo: o DANFE e transcrito na mao, pra quando a
#               fabrica nao manda e a SEFAZ ainda nao liberou
#
# Os tres desembocam no mesmo espelho. Dali pra frente - partes, veiculos,
# payload, conferencias - o caminho e unico.
# --------------------------------------------------------------------------
ORIGENS_DA_NOTA = ("xml", "recebida", "manual")


async def _xml_da_nota_recebida(db: Session, chave: str) -> bytes:
    """XML de uma nota ja coletada. Se ainda nao foi, busca na SEFAZ.

    A consulta por chave nao mexe na esteira por NSU nem esbarra na regra de
    uma hora, entao da pra fazer na hora em que a tela pede.
    """
    limpa = "".join(filter(str.isdigit, chave or ""))
    if len(limpa) != 44:
        raise HTTPException(status_code=400, detail="Informe a chave da NF-e (44 digitos)")

    nota = (
        db.query(NotaFiscalRecebida)
        .filter(NotaFiscalRecebida.chave == limpa)
        .one_or_none()
    )
    if nota is not None and nota.xml:
        return nota.xml.encode()

    try:
        resposta = await run_in_threadpool(sefaz_nfe.consultar_por_chave, limpa)
    except sefaz_nfe.SefazIndisponivel as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Nota {limpa} nao esta guardada e a SEFAZ nao devolveu: {exc}",
        )
    completos = [d for d in resposta["documentos"] if "procNFe" in d["schema"]]
    if not completos:
        raise HTTPException(
            status_code=404,
            detail=(
                f"A SEFAZ nao devolveu o XML da nota {limpa} "
                f"({resposta.get('status')} {resposta.get('motivo')}). "
                "Envie o arquivo ou digite a nota na mao."
            ),
        )
    notas_recebidas.guardar(db, completos[0]["xml"], "sefaz")
    return completos[0]["xml"].encode()


async def _espelho_da_nota(
    db: Session,
    *,
    origem: str,
    arquivo: UploadFile | None,
    chave_nfe: str,
    nota_manual: str,
    tarifa_por_tonelada: str | None,
    embalagem: str,
    especie_id: str | None,
) -> dict:
    """Monta o espelho a partir da origem escolhida na tela."""
    origem = (origem or "xml").strip().lower()
    if origem not in ORIGENS_DA_NOTA:
        raise HTTPException(
            status_code=400,
            detail=f"Origem da nota desconhecida: {origem}. Use {', '.join(ORIGENS_DA_NOTA)}.",
        )

    if origem == "manual":
        try:
            campos = json.loads(nota_manual or "{}")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Dados da nota ilegiveis: {exc}")
        try:
            return cte_montagem.derivar_manual(
                campos,
                tarifa_por_tonelada=tarifa_por_tonelada or None,
                embalagem=embalagem,
                especie_id=especie_id or None,
            )
        except (cte_montagem.DadosInsuficientes, nfe_xml.NFeInvalida) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    if origem == "recebida":
        conteudo = await _xml_da_nota_recebida(db, chave_nfe)
    elif arquivo is not None:
        conteudo = await arquivo.read()
    else:
        raise HTTPException(status_code=400, detail="Envie o XML da NF-e ou escolha outra origem.")

    try:
        return cte_montagem.derivar(
            conteudo,
            tarifa_por_tonelada=tarifa_por_tonelada or None,
            embalagem=embalagem,
            especie_id=especie_id or None,
        )
    except nfe_xml.NFeInvalida as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ElementTree.ParseError as exc:
        raise HTTPException(status_code=400, detail=f"XML ilegivel: {exc}")


@router.post("/espelho")
async def espelho_do_cte(
    arquivo: UploadFile | None = None,
    origem_nota: str = Form("xml"),
    chave_nfe: str = Form(""),
    nota_manual: str = Form(""),
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
    placa_quarto: str = Form(""),
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
    resultado = await _espelho_da_nota(
        db,
        origem=origem_nota,
        arquivo=arquivo,
        chave_nfe=chave_nfe,
        nota_manual=nota_manual,
        tarifa_por_tonelada=tarifa_por_tonelada,
        embalagem=embalagem,
        especie_id=especie_id,
    )

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
        veiculos = await run_in_threadpool(emissao_cte.resolver_veiculos, agendamento, emissao_cte.escolhas_de(locals()))
        seguro = await run_in_threadpool(emissao_cte.resolver_apolice)
    except BsoftError as exc:
        resultado["partes"] = {"erro": str(exc)}
        resultado["pendencias"] = resultado["pendencias"] + [
            f"Nao foi possivel consultar os cadastros no Bsoft: {exc}"
        ]
        return resultado

    resultado["partes"] = partes
    resultado["veiculos"] = veiculos
    # Numa nota digitada o municipio do trecho nao foi informado; quem sabe
    # dele e o endereco escolhido no cadastro. Pra nota com XML isso nao
    # muda nada, porque os campos ja vieram preenchidos.
    cte_montagem.completar_percurso(resultado, partes)
    cfops_id = escolher_cfops_id(resultado["uf_origem"], resultado["uf_destino"])
    resultado["cfops_id"] = cfops_id
    resultado["cfop"] = "5352" if cfops_id == settings.bsoft_cfops_id_estadual else "6352"
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


@router.post("/emitir")
async def emitir_conhecimento(
    arquivo: UploadFile | None = None,
    origem_nota: str = Form("xml"),
    chave_nfe: str = Form(""),
    nota_manual: str = Form(""),
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
    placa_quarto: str = Form(""),
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

    espelho = await _espelho_da_nota(
        db,
        origem=origem_nota,
        arquivo=arquivo,
        chave_nfe=chave_nfe,
        nota_manual=nota_manual,
        tarifa_por_tonelada=tarifa_por_tonelada,
        embalagem=embalagem,
        especie_id=especie_id,
    )

    chave = espelho["chaves_nfe"][0]
    try:
        montado = await run_in_threadpool(
            emissao_cte.montar,
            espelho, agendamento,
            escolhas=emissao_cte.escolhas_de(locals()),
            aliquota_icms=aliquota_icms,
            km=km,
            forma_pagamento=forma_pagamento,
            conjunto_veiculos_id=conjunto_veiculos_id,
            endereco_remetente_id=endereco_remetente_id,
            endereco_destinatario_id=endereco_destinatario_id,
            rascunho=not confirmar_emissao_real,
        )
    except emissao_cte.FalhaCadastros as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Payload incompleto nao vai pra frente: melhor recusar aqui do que
    # deixar o Bsoft criar um documento torto.
    if montado["pendencias"]:
        raise HTTPException(status_code=400, detail={"pendencias": montado["pendencias"]})

    try:
        operacao = await run_in_threadpool(
            emissao_cte.emitir, db,
            corpo=montado["corpo"],
            chave=chave,
            agendamento_id=agendamento_id,
            solicitado_por=usuario.email,
            rascunho=not confirmar_emissao_real,
        )
    except emissao_cte.JaEmitido as exc:
        # Inclui o rascunho criado sozinho: a API nao promove rascunho a
        # definitivo, e um segundo POST criaria outro documento.
        raise HTTPException(status_code=409, detail=str(exc))
    except BsoftEmissaoBloqueada as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except emissao_cte.FalhaBsoft as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"operacao": _to_dict(operacao), "rascunho": not confirmar_emissao_real}


@router.get("/conhecimento/{conhecimento_id}")
async def ler_conhecimento(conhecimento_id: str):
    """LEITURA. Registro do CT-e como o Bsoft gravou.

    Serve pra conferir o que chegou la de verdade, campo a campo, em vez de
    inferir pela tela.
    """
    try:
        return await run_in_threadpool(bsoft_fiscal.obter_conhecimento, conhecimento_id)
    except BsoftError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


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


@router.get("/conjuntos")
async def listar_conjuntos():
    """LEITURA. Conjuntos de veiculos cadastrados (motorista + cavalo +
    carretas).

    A API do Bsoft aceita OU o conjunto OU os veiculos avulsos, e cobra um
    dos dois. Quando as placas do agendamento nao estao no cadastro, o
    conjunto e a saida - por isso a tela precisa oferecer a escolha.
    """
    try:
        conjuntos = await run_in_threadpool(bsoft_fiscal.listar_conjuntos_veiculos)
    except BsoftError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"conjuntos": conjuntos}


@router.get("/motoristas")
async def procurar_motoristas(nome: str = ""):
    """LEITURA. Busca motorista pelo nome no cadastro do Bsoft.

    Procura no grupo de motoristas, que e o unico que o campo motorista_id
    do CT-e aceita. Achando so fora do grupo, devolve assim mesmo - com o
    aviso - porque quem opera precisa saber que a pessoa existe mas esta
    cadastrada como outra coisa (cliente, dono de veiculo).
    """
    if len((nome or "").strip()) < 3:
        return {"resultados": [], "aviso": "Digite ao menos 3 letras do nome."}
    try:
        return await run_in_threadpool(bsoft_fiscal.procurar_motoristas, nome)
    except BsoftError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


class ConjuntoIn(BaseModel):
    motorista_id: str
    placa_cavalo: str
    placa_carreta1: str = ""
    placa_carreta2: str = ""
    placa_quarto: str = ""


@router.post("/conjuntos")
async def criar_conjunto(payload: ConjuntoIn):
    """ESCRITA no cadastro de veiculos do Bsoft (nao e documento fiscal).

    Vincula motorista e placas num conjunto. Com ele, o CT-e precisa de um
    campo so - sem ele, a API cobra os cinco, um erro por vez.
    """
    try:
        resposta = await run_in_threadpool(
            bsoft_fiscal.criar_conjunto_veiculos, payload.motorista_id, payload.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except BsoftError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"criado": resposta}


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
        {
            "id": v.get("id"), "placa": v.get("placa"),
            "categoria": v.get("categoria", ""), "motorista": v.get("motorista", ""),
        }
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
    operacao.tentativas = (operacao.tentativas or 0) + 1
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


@router.post("/sefaz/sincronizar")
async def sincronizar_sefaz(db: Session = Depends(get_db)):
    """LEITURA na SEFAZ. Baixa os XML de NF-e novos com o certificado A1.

    Continua de onde parou: o servico entrega por NSU, e pedir desde o zero
    e recusado como "consumo indevido" com uma hora de bloqueio. Por isso o
    ponteiro fica no banco, nao em memoria.
    """
    estado = (
        db.query(EstadoSefaz)
        .filter(EstadoSefaz.cnpj == settings.certificado_cnpj)
        .one_or_none()
    )
    if estado is None:
        estado = EstadoSefaz(cnpj=settings.certificado_cnpj, ultimo_nsu="0")
        db.add(estado)

    try:
        resultado = await run_in_threadpool(sefaz_nfe.sincronizar, estado.ultimo_nsu)
    except sefaz_nfe.CertificadoAusente as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except sefaz_nfe.SefazIndisponivel as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # A SEFAZ devolve o ponteiro dela mesmo quando recusa a consulta: vale
    # guardar, senao a proxima tentativa repete o erro.
    if resultado.get("ultimo_nsu"):
        estado.ultimo_nsu = resultado["ultimo_nsu"]
    if resultado.get("maximo_nsu"):
        estado.maximo_nsu = resultado["maximo_nsu"]
    estado.ultima_consulta = datetime.utcnow()
    estado.ultimo_status = f"{resultado.get('status')} {resultado.get('motivo')}"[:200]
    estado.documentos_baixados = (estado.documentos_baixados or 0) + len(resultado["completas"])
    db.commit()

    guardadas = 0
    for nota in resultado["completas"]:
        if notas_recebidas.guardar(db, nota["xml"], "sefaz") is not None:
            guardadas += 1

    return {
        "status": resultado["status"],
        "motivo": resultado["motivo"],
        "ultimo_nsu": estado.ultimo_nsu,
        "maximo_nsu": estado.maximo_nsu,
        "resumos_recebidos": resultado["resumos"],
        "notas_completas": len(resultado["completas"]),
        "guardadas": guardadas,
        "chaves": [c["chave"] for c in resultado["completas"]],
        "falhas": resultado["falhas"],
    }


@router.post("/email/sincronizar")
async def sincronizar_email(dias: int = 7, db: Session = Depends(get_db)):
    """Guarda as NF-e que chegaram anexadas no e-mail.

    Caminho rapido: quando o fornecedor manda o arquivo, a nota fica
    disponivel na hora, sem esperar a esteira da SEFAZ.
    """
    from ..servicos import email_inbox
    try:
        xmls = await run_in_threadpool(email_inbox.anexos_xml_recentes, dias)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao ler a caixa: {exc}")

    guardadas = [n for n in (notas_recebidas.guardar(db, x, "email") for x in xmls) if n]
    return {
        "anexos_xml": len(xmls),
        "notas": len(guardadas),
        "chaves": [n.chave for n in guardadas],
    }


# Embalagem do pedido (vocabulario do OCR) -> o que a tela de emissao usa.
EMBALAGENS_DA_TELA = ("GRANEL", "BIG BAG", "SACARIA")


def _embalagem_da_tela(texto: str) -> str:
    alto = (texto or "").upper()
    if "GRANEL" in alto:
        return "GRANEL"
    if "BIG" in alto:
        return "BIG BAG"
    if "SAC" in alto:
        return "SACARIA"
    return ""


def sugerir_para_agendamento(db: Session, agendamento: Agendamento) -> dict:
    """O que da pra preencher sozinho a partir do agendamento.

    Tarifa: a ultima cotacao registrada pro destino (e, se houver, pro
    mesmo cliente). Embalagem: a do item do pedido, lida pelo OCR. Os dois
    eram digitados toda vez; agora vem preenchidos e a pessoa so corrige.
    """
    from ..models import CotacaoFrete

    itens = list(agendamento.itens)
    primeiro = itens[0] if itens else None
    destino = (primeiro.cidade if primeiro else "") or ""
    cliente = (primeiro.cliente if primeiro else "") or ""
    embalagem = _embalagem_da_tela(primeiro.embalagem if primeiro else "")

    cotacao = None
    if destino:
        cidade = destino.split("-")[0].split("/")[0].strip()
        consulta = db.query(CotacaoFrete).filter(CotacaoFrete.destino.ilike(f"%{cidade}%"))
        # Do mesmo cliente vale mais; sem cliente, a mais recente do destino.
        if cliente:
            cotacao = (
                consulta.filter(CotacaoFrete.cliente_nome.ilike(f"%{cliente.split()[0]}%"))
                .order_by(CotacaoFrete.data_cotacao.desc()).first()
            )
        if cotacao is None:
            cotacao = consulta.order_by(CotacaoFrete.data_cotacao.desc()).first()

    return {
        "agendamento_id": agendamento.id,
        "destino": destino,
        "cliente": cliente,
        "embalagem": embalagem,
        "tarifa": f"{cotacao.valor_tonelada:.2f}" if cotacao else "",
        "cotacao": {
            "data": cotacao.data_cotacao,
            "destino": cotacao.destino,
            "cliente": cotacao.cliente_nome,
            "fabrica": cotacao.fabrica,
        } if cotacao else None,
    }


@router.get("/sugestoes")
def sugestoes(agendamento_id: int, db: Session = Depends(get_db)):
    """LEITURA. Tarifa e embalagem sugeridas pra um agendamento."""
    agendamento = db.get(Agendamento, agendamento_id)
    if agendamento is None:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado")
    return sugerir_para_agendamento(db, agendamento)


@router.get("/notas")
def listar_notas(db: Session = Depends(get_db)):
    """NF-e disponiveis pra virar CT-e, de qualquer fonte, com o agendamento
    que o sistema casou sozinho (ou o motivo de nao ter casado)."""
    return {
        "notas": [
            {
                "chave": n.chave,
                "origem": n.origem,
                "numero": n.numero,
                "serie": n.serie,
                "emissao": n.emissao,
                "emitente": n.emitente_nome,
                "destinatario": n.destinatario_nome,
                "destinatario_doc": n.destinatario_doc,
                "destino": f"{n.municipio_destino} - {n.uf_destino}",
                "valor": n.valor_nota,
                "peso": n.peso_bruto,
                "agendamento_id": n.agendamento_id,
                "casamento": n.casamento,
                "rascunho_resultado": n.rascunho_resultado,
            }
            for n in notas_recebidas.pendentes(db)
        ]
    }


@router.get("/notas/contagem")
def contar_notas(db: Session = Depends(get_db)):
    """Quantas notas esperam CT-e. E o numero da barra lateral."""
    pendentes = notas_recebidas.pendentes(db, limite=500)
    return {
        "sem_cte": len(pendentes),
        "casadas": sum(1 for n in pendentes if n.agendamento_id),
    }


@router.post("/notas/{chave}/agendamento")
def ligar_nota_ao_agendamento(chave: str, agendamento_id: int | None = None, db: Session = Depends(get_db)):
    """Escolha feita na tela vence a automatica: liga (ou solta) a nota."""
    nota = db.query(NotaFiscalRecebida).filter(NotaFiscalRecebida.chave == chave).one_or_none()
    if nota is None:
        raise HTTPException(status_code=404, detail="Nota nao encontrada")
    if agendamento_id and db.get(Agendamento, agendamento_id) is None:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado")
    nota.agendamento_id = agendamento_id
    nota.casamento = f"escolhido na tela: #{agendamento_id}" if agendamento_id else "solto na tela"
    db.commit()
    return {"chave": nota.chave, "agendamento_id": nota.agendamento_id, "casamento": nota.casamento}
