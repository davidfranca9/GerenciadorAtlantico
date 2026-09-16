from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import time
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Agendamento, Cidade
from ..servicos import bsoft_api, bsoft_orquestracao, ocr, ocr_gemini
from ..servicos.bsoft_lookup import (
    BSOFT_CATEGORY_ID_TO_RODADO_ID_MAP,
    BSOFT_CATEGORIAS_VEICULO,
    BSOFT_CATEGORY_TO_EQUIPMENT_MAP,
    BSOFT_CATEGORY_TO_SIMPLE_BRANDS_MAP,
    BSOFT_GRUPOS_VEICULO,
    BSOFT_MARCA_ID_LOOKUP,
    BSOFT_SIMPLE_BRANDS_LIST,
    BSOFT_TIPOS_CARROCERIA_NOMES,
    BSOFT_TIPOS_EQUIPAMENTO,
    BSOFT_TIPOS_RODADO_NOMES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bsoft", tags=["bsoft"], dependencies=[Depends(get_current_user)])


@router.get("/lookups")
def obter_lookups():
    return {
        "categorias_veiculo": BSOFT_CATEGORIAS_VEICULO,
        "tipos_equipamento": BSOFT_TIPOS_EQUIPAMENTO,
        "grupos_veiculo": BSOFT_GRUPOS_VEICULO,
        "tipos_rodado": BSOFT_TIPOS_RODADO_NOMES,
        "tipos_carroceria": BSOFT_TIPOS_CARROCERIA_NOMES,
        "categoria_id_to_rodado_id": BSOFT_CATEGORY_ID_TO_RODADO_ID_MAP,
        "categoria_to_equipamento": BSOFT_CATEGORY_TO_EQUIPMENT_MAP,
        "categoria_to_marcas": BSOFT_CATEGORY_TO_SIMPLE_BRANDS_MAP,
        "marcas": BSOFT_SIMPLE_BRANDS_LIST,
        "marca_id_lookup": {f"{marca}|{categoria}": id_ for (marca, categoria), id_ in BSOFT_MARCA_ID_LOOKUP.items()},
    }


@router.get("/configuracoes-cte")
def obter_configuracoes_cte():
    """Le (somente GET) os cadastros do Bsoft que a emissao de CT-e precisa
    referenciar por id - parametros de criacao, agencias, talao, operadora de
    credito (IPEF do CIOT), naturezas de carga/operacao."""
    return bsoft_api.obter_todas_configuracoes_cte()


@router.get("/sondar-cadastros")
def sondar_cadastros():
    """Somente leitura: tenta descobrir cadastros do modulo transporte que
    nao estao na documentacao (ex: regras de carreto)."""
    return bsoft_api.sondar_cadastros_transporte()


def _so_digitos_letras(texto: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (texto or "").upper())


@router.get("/documentos-fiscais")
def listar_documentos_fiscais(dias: int = 30, db: Session = Depends(get_db)):
    """Somente leitura: CT-es emitidos e contratos de frete (com CIOT) dos
    ultimos N dias, cruzados entre si e com os agendamentos do sistema."""
    from datetime import date, timedelta

    hoje = date.today()
    resultado = bsoft_api.listar_documentos_fiscais(
        (hoje - timedelta(days=max(1, min(dias, 180)))).strftime("%Y-%m-%d"),
        hoje.strftime("%Y-%m-%d"),
    )

    # Liga o documento ao agendamento pela placa do cavalo - a placa e o
    # identificador mais confiavel que os dois lados tem em comum.
    agendamentos_por_placa: dict[str, list] = {}
    for agendamento in db.query(Agendamento).all():
        placa = _so_digitos_letras(agendamento.plate_cavalo)
        if placa:
            agendamentos_por_placa.setdefault(placa, []).append(agendamento)

    for documento in resultado.get("documentos", []):
        candidatos = agendamentos_por_placa.get(_so_digitos_letras(documento.get("veiculo")), [])
        data_documento = (documento.get("emitido_em") or "")[:10]  # YYYY-MM-DD
        escolhido = None
        for agendamento in candidatos:
            partes = (agendamento.loading_date or "").split("/")
            if len(partes) == 3 and f"{partes[2]}-{partes[1]}-{partes[0]}" == data_documento:
                escolhido = agendamento
                break
        documento["agendamento_id"] = escolhido.id if escolhido else None
        documento["agendamento_status"] = escolhido.status if escolhido else None
    return resultado


@router.get("/exemplos-documentos")
def obter_exemplos_documentos():
    """Somente leitura: ultimos contratos de frete e CT-es emitidos, pra
    servir de modelo do payload de emissao."""
    return bsoft_api.obter_exemplos_documentos()


@router.get("/cidades")
def obter_cidades(db: Session = Depends(get_db)):
    cidades_por_uf: dict[str, list[list[str]]] = {}
    for c in db.query(Cidade).order_by(Cidade.uf, Cidade.nome).all():
        if not c.ibge:
            continue
        cidades_por_uf.setdefault(c.uf, []).append([c.nome, c.ibge])
    return cidades_por_uf


@router.get("/consulta-cep/{cep}")
def consulta_cep(cep: str):
    digitos = re.sub(r"\D", "", cep)
    if len(digitos) != 8:
        raise HTTPException(status_code=400, detail="O CEP deve conter 8 digitos.")
    try:
        return bsoft_api.consultar_cep(digitos)
    except bsoft_api.BsoftApiError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except requests.exceptions.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Nao foi possivel consultar o CEP: {exc}")


@router.get("/consulta-cnpj/{cnpj}")
def consulta_cnpj(cnpj: str):
    digitos = re.sub(r"\D", "", cnpj)
    if len(digitos) != 14:
        raise HTTPException(status_code=400, detail="O CNPJ deve conter 14 digitos.")
    try:
        return bsoft_api.consultar_cnpj(digitos)
    except bsoft_api.BsoftApiError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except requests.exceptions.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Nao foi possivel consultar o CNPJ: {exc}")


@router.get("/pessoas/fisicas/{cpf}/busca")
def buscar_pessoa_fisica(cpf: str):
    pessoa_id = bsoft_api.buscar_pessoa_fisica_por_cpf(re.sub(r"\D", "", cpf))
    return {"encontrado": bool(pessoa_id), "id": pessoa_id}


@router.get("/pessoas/juridicas/{cnpj}/busca")
def buscar_pessoa_juridica(cnpj: str):
    pessoa_id = bsoft_api.buscar_pessoa_juridica_por_cnpj(re.sub(r"\D", "", cnpj))
    return {"encontrado": bool(pessoa_id), "id": pessoa_id}


async def _salvar_upload(file: UploadFile) -> str:
    suffix = os.path.splitext(file.filename or "")[1] or ".pdf"
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(await file.read())
    return path


@router.post("/importar-oc")
async def importar_oc(file: UploadFile):
    path = await _salvar_upload(file)
    try:
        return await run_in_threadpool(bsoft_orquestracao.extrair_dados_oc, path)
    except bsoft_orquestracao.CadastroBsoftError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        os.remove(path)


def _classificar_e_extrair_fallback(path: str) -> dict:
    texto = ocr.obter_texto_do_arquivo_ocr(path)
    if not texto:
        return {"tipo": "DESCONHECIDO", "dados": {}}
    tipo = ocr.classificar_documento(texto)
    if tipo == "CNH":
        return {"tipo": tipo, "dados": ocr.extrair_dados_cnh_com_azure_api(texto)}
    if tipo == "CRLV":
        return {"tipo": tipo, "dados": ocr.extrair_dados_crlv_com_azure_api(texto, BSOFT_SIMPLE_BRANDS_LIST, BSOFT_TIPOS_CARROCERIA_NOMES)}
    if tipo == "RNTRC":
        return {"tipo": tipo, "dados": ocr.extrair_dados_rntrc_com_azure_api(texto)}
    return {"tipo": tipo, "dados": {}}


def _ler_documento(path: str) -> dict:
    """Um arquivo: IA numa chamada so (com troca de modelo quando um esta
    ocupado). Se a IA falhar, NAO preenche nada: o OCR local lia a CNH
    trocando campos ("OL RE" antes do nome, registro no lugar do seguro,
    categoria "X") e levava ~30 s. Melhor avisar pra tentar de novo.

    O OCR local so entra quando a IA nem esta configurada. Erro num arquivo
    nao derruba os outros que foram enviados junto."""
    inicio = time.perf_counter()
    aviso = ""
    erro_ia = ""
    try:
        resultado = ocr_gemini.ler_documento_com_gemini(path)
        metodo = "ia"
    except ocr_gemini.GeminiIndisponivel:
        aviso = "IA não configurada"
        try:
            resultado = _classificar_e_extrair_fallback(path)
            metodo = "ocr_local"
        except Exception:
            resultado = {"tipo": "DESCONHECIDO", "dados": {}}
            metodo = "falhou"
    except Exception as exc:
        codigo = getattr(exc, "code", None)
        aviso = "a IA está ocupada agora" if codigo in (429, 500, 503) else "a IA não conseguiu ler o arquivo"
        # Motivo curto (tipo e codigo do erro da API), sem nada do documento.
        erro_ia = f"{type(exc).__name__}{f' {codigo}' if codigo else ''}: {str(exc)[:240]}"
        logger.warning("importar-documentos: leitura pela IA falhou (%s)", erro_ia)
        resultado = {"tipo": "DESCONHECIDO", "dados": {}}
        metodo = "falhou"
    resultado = {**resultado, "metodo": metodo, "segundos": round(time.perf_counter() - inicio, 1), "aviso": aviso, "erro_ia": erro_ia}
    logger.info("importar-documentos: %s lido por %s em %.1f s", resultado["tipo"], metodo, resultado["segundos"])
    return resultado


@router.post("/importar-documentos")
async def importar_documentos(files: list[UploadFile]):
    """Le varios documentos (CNH, CRLV, RNTRC) AO MESMO TEMPO.

    Antes era um arquivo depois do outro, e cada um com duas chamadas a IA:
    tres documentos eram seis chamadas em fila. Agora cada arquivo e uma
    chamada e todas correm juntas - o total fica perto do documento mais
    lento, nao da soma.
    """
    caminhos = [await _salvar_upload(file) for file in files]
    try:
        resultados = await asyncio.gather(*(run_in_threadpool(_ler_documento, caminho) for caminho in caminhos))
    finally:
        for caminho in caminhos:
            try:
                os.remove(caminho)
            except OSError:
                pass

    driver_data: dict = {}
    vehicle_docs: list[dict] = []
    # Como cada arquivo foi lido: a tela avisa quando nao foi pela IA.
    leituras = [
        {"arquivo": file.filename or "", "tipo": r["tipo"], "metodo": r["metodo"], "segundos": r["segundos"],
         "aviso": r["aviso"], "erro_ia": r["erro_ia"]}
        for file, r in zip(files, resultados)
    ]
    for resultado in resultados:
        if resultado["tipo"] in ("CNH", "RNTRC"):
            # So o que veio preenchido: o RNTRC nao apaga o nome lido da CNH.
            driver_data.update({campo: valor for campo, valor in (resultado["dados"] or {}).items() if valor})
        elif resultado["tipo"] == "CRLV":
            vehicle_docs.append(resultado["dados"])
    return {"motorista": driver_data, "veiculos": vehicle_docs, "leituras": leituras}


class VeiculoIn(BaseModel):
    placa: str = ""
    renavam: str = ""
    rntrc: str = ""
    tara: Optional[float] = None
    capacidadeCarga: Optional[float] = None
    capM3: Optional[float] = None
    modeloVeiculo: str = ""
    quantidadeEixos: Optional[int] = None
    marcaVeiculo: Optional[int] = None
    categoriaVeiculo: Optional[int] = None
    grupoVeiculo: Optional[int] = None
    tipoRodado: str = ""
    tipoCarroceria: str = ""
    tipoEquipamento: Optional[int] = None
    motoristaEhProprietario: bool = False
    estado: str = ""
    cidade: str = ""
    proprietario_id: Optional[str] = None
    motoristaId: Optional[str] = None
    arrendatarioId: Optional[str] = None
    motorista_documento: Optional[str] = None


class EnderecoIn(BaseModel):
    cod_pessoa: str
    logradouro: str = ""
    numero: str = ""
    bairro: str = ""
    cidade: str = ""
    estado: str = ""
    cep: str = ""


class PessoaFisicaIn(BaseModel):
    nome: str
    cpf: str
    dtNascimento: Optional[str] = None
    rntrc: Optional[str] = None
    fone: Optional[str] = None
    is_owner: bool = False
    cnh: dict = {}


class PessoaJuridicaIn(BaseModel):
    cnpj: str
    razao_social: str
    tipoTransportadora: Optional[str] = None
    rntrc: Optional[str] = None
    inscricao_estadual: Optional[str] = None


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except bsoft_api.BsoftApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/veiculos")
def cadastrar_veiculo(payload: VeiculoIn):
    return _wrap(bsoft_api.cadastrar_veiculo_bsoft, payload.model_dump())


@router.post("/enderecos")
def cadastrar_endereco(payload: EnderecoIn):
    dados = payload.model_dump(exclude={"cod_pessoa"})
    return _wrap(bsoft_api.cadastrar_endereco_bsoft, payload.cod_pessoa, dados)


@router.post("/pessoas/fisicas")
def cadastrar_pessoa_fisica(payload: PessoaFisicaIn):
    return _wrap(bsoft_api.cadastrar_pessoa_fisica_bsoft, payload.model_dump())


@router.put("/pessoas/fisicas/{cpf}")
def atualizar_pessoa_fisica(cpf: str, payload: PessoaFisicaIn):
    return _wrap(bsoft_api.atualizar_pessoa_fisica_bsoft, cpf, payload.model_dump())


@router.post("/pessoas/juridicas")
def cadastrar_pessoa_juridica(payload: PessoaJuridicaIn):
    return _wrap(bsoft_api.cadastrar_pessoa_juridica_bsoft, payload.model_dump())


@router.put("/pessoas/juridicas/{cnpj}")
def atualizar_pessoa_juridica(cnpj: str, payload: PessoaJuridicaIn):
    return _wrap(bsoft_api.atualizar_pessoa_juridica_bsoft, cnpj, payload.model_dump())


class CnhIn(BaseModel):
    numero: str = ""
    seguro: str = ""
    categoria: str = ""
    protocolo: str = ""
    dtValidade: str = ""
    dtExpedicao: str = ""
    dtPrimeiraExpedicao: str = ""


class MotoristaIn(BaseModel):
    nome: str
    cpf: str
    fone: str = ""
    dtNascimento: str = ""
    rntrc: str = ""
    cnh: CnhIn = CnhIn()


class EnderecoMotoristaIn(BaseModel):
    cep: str = ""
    logradouro: str = ""
    numero: str = ""
    bairro: str = ""
    estado: str = ""
    cidade: str = ""
    complemento: str = ""
    inscricaoEstadual: str = "ISENTO"
    inscricaoMunicipal: str = "ISENTO"
    tipoEndereco: str = "Nacional"
    enderecoPreferencial: str = "Sim"
    cobrancaPreferencial: str = "Não"
    ieNaoContribuinte: str = "Sim"


class ProprietarioIn(BaseModel):
    cnpj: str = ""
    razao_social: str = ""
    rntrc: str = ""
    tipo: str = ""
    endereco_cnpj_data: dict = {}


class VeiculoSlotIn(BaseModel):
    placa: str = ""
    renavam: str = ""
    eixos: str = ""
    estado: str = ""
    cidade: str = ""
    marca: str = ""
    modelo: str = ""
    categoria: str = ""
    rodado: str = ""
    carroceria: str = ""
    equipamento: str = ""


class CadastroCompletoIn(BaseModel):
    motorista: MotoristaIn
    endereco: EnderecoMotoristaIn = EnderecoMotoristaIn()
    motorista_e_proprietario: bool = True
    proprietario: ProprietarioIn = ProprietarioIn()
    cavalo: VeiculoSlotIn = VeiculoSlotIn()
    reboque1: Optional[VeiculoSlotIn] = None
    reboque2: Optional[VeiculoSlotIn] = None
    permitir_sem_veiculo: bool = False


@router.post("/cadastrar-completo")
def cadastrar_completo(payload: CadastroCompletoIn, db: Session = Depends(get_db)):
    try:
        return bsoft_orquestracao.executar_cadastro_completo(db, payload.model_dump())
    except bsoft_orquestracao.CadastroBsoftError as exc:
        return {"ok": False, "passos": [], "mensagem": str(exc)}
