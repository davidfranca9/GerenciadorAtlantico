"""Orquestracao do cadastro completo no Bsoft TMS (motorista + endereco +
proprietario + veiculos), portada de
gerenciador_atlantico/pyside_ui/bsoft_page.py (_register_worker e afins).
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime

import pdfplumber
from docx import Document
from sqlalchemy.orm import Session

from ..models import Cidade
from . import bsoft_api
from .bsoft_lookup import (
    BSOFT_CATEGORIAS_VEICULO,
    BSOFT_CATEGORY_ID_TO_RODADO_ID_MAP,
    BSOFT_CATEGORY_TO_EQUIPMENT_MAP,
    BSOFT_MARCA_ID_LOOKUP,
    BSOFT_TIPOS_CARROCERIA_NOMES,
    BSOFT_TIPOS_EQUIPAMENTO,
    BSOFT_TIPOS_RODADO_NOMES,
)
from .ocr import normalizar_texto_sem_acento


class CadastroBsoftError(Exception):
    pass


def _limpar(valor) -> str:
    texto = "" if valor is None else str(valor).strip()
    if texto.lower() in {"nao encontrado", "não encontrado", "nao encontrada", "não encontrada", "formato invalido", "formato inválido"}:
        return ""
    return texto


def _formatar_data_api(valor: str) -> str | None:
    texto = _limpar(valor)
    if not texto:
        return None
    try:
        return datetime.strptime(texto, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _formatar_cep(cep: str) -> str:
    digitos = re.sub(r"\D", "", cep or "")
    if len(digitos) == 8:
        return f"{digitos[:5]}-{digitos[5:]}"
    return digitos


def resolver_ibge(db: Session, estado: str, cidade: str) -> str | None:
    estado = (estado or "").strip().upper()
    cidade_norm = normalizar_texto_sem_acento(cidade or "")
    if not estado or not cidade_norm:
        return None
    for row in db.query(Cidade).filter(Cidade.uf == estado).all():
        if normalizar_texto_sem_acento(row.nome) == cidade_norm and row.ibge:
            return row.ibge
    return None


def montar_endereco_motorista(db: Session, endereco: dict) -> dict:
    estado = _limpar(endereco.get("estado"))
    cidade = _limpar(endereco.get("cidade"))
    return {
        "tipoEndereco": "N" if _limpar(endereco.get("tipoEndereco")) != "Estrangeiro" else "E",
        "cep": _formatar_cep(_limpar(endereco.get("cep"))),
        "bairro": _limpar(endereco.get("bairro")),
        "cidade": cidade,
        "estado": estado,
        "numero": _limpar(endereco.get("numero")),
        "complemento": _limpar(endereco.get("complemento")),
        "logradouro": _limpar(endereco.get("logradouro")),
        "cobrancaPreferencial": "S" if _limpar(endereco.get("cobrancaPreferencial")) == "Sim" else "N",
        "enderecoPreferencial": "N" if _limpar(endereco.get("enderecoPreferencial")) == "Não" else "S",
        "codIBGE": resolver_ibge(db, estado, cidade),
        "inscricaoMunicipal": _limpar(endereco.get("inscricaoMunicipal")) or "ISENTO",
        "inscricaoEstadual": _limpar(endereco.get("inscricaoEstadual")) or "ISENTO",
        "inscricaoEstadualNaoContribuinte": "N" if _limpar(endereco.get("ieNaoContribuinte")) == "Não" else "S",
    }


def montar_endereco_proprietario(db: Session, dados_cnpj: dict) -> dict:
    dados_cnpj = dados_cnpj or {}
    estado = _limpar(dados_cnpj.get("uf"))
    cidade = _limpar(dados_cnpj.get("municipio"))
    inscricao_estadual = "ISENTO"
    for item in dados_cnpj.get("inscricoes_estaduais", []) or []:
        if item.get("ativo"):
            inscricao_estadual = item.get("inscricao_estadual") or "ISENTO"
            break
    return {
        "tipoEndereco": "N",
        "cep": _formatar_cep(_limpar(dados_cnpj.get("cep"))),
        "bairro": _limpar(dados_cnpj.get("bairro")),
        "cidade": cidade,
        "estado": estado,
        "numero": _limpar(dados_cnpj.get("numero")),
        "complemento": _limpar(dados_cnpj.get("complemento")),
        "logradouro": _limpar(dados_cnpj.get("logradouro")),
        "codIBGE": resolver_ibge(db, estado, cidade),
        "inscricaoMunicipal": "ISENTO",
        "inscricaoEstadual": inscricao_estadual,
        "inscricaoEstadualNaoContribuinte": "S",
        "enderecoPreferencial": "S",
        "cobrancaPreferencial": "S",
    }


def montar_veiculo_payload(db: Session, slot: dict, driver_id, owner_id, driver_cpf, rntrc_final, motorista_e_proprietario: bool) -> dict:
    placa = _limpar(slot.get("placa")).upper()
    estado = _limpar(slot.get("estado"))
    cidade = _limpar(slot.get("cidade"))
    categoria = _limpar(slot.get("categoria"))
    marca = _limpar(slot.get("marca")).upper()

    if not estado or not cidade:
        raise CadastroBsoftError(f"Estado e cidade sao obrigatorios para o veiculo de placa {placa}.")
    if not categoria or not marca:
        raise CadastroBsoftError(f"Categoria e marca sao obrigatorias para o veiculo de placa {placa}.")

    cidade_ibge = resolver_ibge(db, estado, cidade)
    if not cidade_ibge:
        raise CadastroBsoftError(f"Nao foi possivel encontrar o codigo IBGE para {cidade} - {estado}.")

    categoria_id = BSOFT_CATEGORIAS_VEICULO.get(categoria)
    if categoria_id is None:
        raise CadastroBsoftError(f"A categoria '{categoria}' nao e valida para o veiculo de placa {placa}.")

    marca_id = BSOFT_MARCA_ID_LOOKUP.get((marca, categoria))
    if marca_id is None:
        raise CadastroBsoftError(f"Nao foi possivel encontrar o codigo da marca para {marca} / {categoria}.")

    rodado_nome = _limpar(slot.get("rodado"))
    carroceria_nome = _limpar(slot.get("carroceria"))
    equipamento_nome = _limpar(slot.get("equipamento"))

    tipo_rodado = next((k for k, v in BSOFT_TIPOS_RODADO_NOMES.items() if v == rodado_nome), "")
    tipo_carroceria = next((k for k, v in BSOFT_TIPOS_CARROCERIA_NOMES.items() if v == carroceria_nome), "")
    tipo_equipamento = BSOFT_TIPOS_EQUIPAMENTO.get(equipamento_nome)

    return {
        "placa": placa,
        "renavam": _limpar(slot.get("renavam")),
        "rntrc": rntrc_final,
        "tara": 9000,
        "capacidadeCarga": 32000,
        "capM3": 32,
        "modeloVeiculo": _limpar(slot.get("modelo")),
        "quantidadeEixos": _limpar(slot.get("eixos")) or None,
        "marcaVeiculo": marca_id,
        "categoriaVeiculo": categoria_id,
        "grupoVeiculo": 2,
        "tipoRodado": tipo_rodado,
        "tipoCarroceria": tipo_carroceria,
        "tipoEquipamento": tipo_equipamento,
        "motoristaEhProprietario": motorista_e_proprietario,
        "estado": estado,
        "cidade": cidade_ibge,
        "proprietario_id": owner_id,
        "motorista_documento": driver_cpf,
        "motoristaId": driver_id,
        "arrendatarioId": owner_id,
    }


def categoria_auto_campos(categoria: str) -> dict:
    """Dado o nome da categoria, retorna marca(s) possiveis e rodado/equipamento
    sugeridos, espelhando _handle_vehicle_category_change do app desktop."""
    from .bsoft_lookup import BSOFT_CATEGORY_TO_SIMPLE_BRANDS_MAP

    categoria_id = BSOFT_CATEGORIAS_VEICULO.get(categoria)
    marcas = sorted(BSOFT_CATEGORY_TO_SIMPLE_BRANDS_MAP.get(categoria, []))
    if categoria_id is None:
        return {"marcas": marcas, "rodado": "", "equipamento": ""}

    equipamento_id = BSOFT_CATEGORY_TO_EQUIPMENT_MAP.get(categoria_id)
    equipamento_nome = next((nome for nome, cod in BSOFT_TIPOS_EQUIPAMENTO.items() if cod == equipamento_id), "")
    rodado_id = BSOFT_CATEGORY_ID_TO_RODADO_ID_MAP.get(categoria_id, "00")
    rodado_nome = BSOFT_TIPOS_RODADO_NOMES.get(rodado_id, "NÃO APLICÁVEL")
    return {"marcas": marcas, "rodado": rodado_nome, "equipamento": equipamento_nome}


def _ler_texto_oc(caminho: str) -> str:
    extensao = os.path.splitext(caminho)[1].lower()
    if extensao == ".docx":
        documento = Document(caminho)
        return "\n".join(p.text for p in documento.paragraphs)
    if extensao == ".pdf":
        with pdfplumber.open(caminho) as pdf:
            textos = [pagina.extract_text() for pagina in pdf.pages]
        return "\n".join(t for t in textos if t)
    raise CadastroBsoftError(f"O formato '{extensao}' nao e suportado.")


def extrair_dados_oc(caminho: str) -> dict:
    texto = _ler_texto_oc(caminho)
    normalizado = normalizar_texto_sem_acento(texto).replace("–", "-").replace("—", "-").replace("â€“", "-").replace("â€”", "-")
    dados = {}

    motorista = re.search(r"MOTORISTA:\s*([\d.\-]+)\s*-\s*([A-Z\s]+?)(?=\s+CNH:|\s+FONE:|\n)", normalizado, re.MULTILINE)
    if motorista:
        dados["cpf"] = motorista.group(1).strip()
        dados["nome"] = motorista.group(2).strip()

    cnh = re.search(r"CNH:\s*(\d+)", normalizado)
    if cnh:
        dados["cnh"] = cnh.group(1).strip()

    fone = re.search(r"FONE:\s*([\d\s()\-]+)", normalizado)
    if fone:
        dados["fone"] = fone.group(1).strip()

    padroes = {
        "placa_cavalo": r"1\w*\s*PLACA:\s*([A-Z0-9\-]+)",
        "placa_carreta1": r"2\w*\s*PLACA:\s*([A-Z0-9\-]+)",
        "placa_carreta2": r"3\w*\s*PLACA:\s*([A-Z0-9\-]+)",
    }
    for chave, padrao in padroes.items():
        match = re.search(padrao, normalizado)
        if match:
            dados[chave] = match.group(1).strip()
    return dados


def executar_cadastro_completo(db: Session, payload: dict) -> dict:
    passos = []

    def registrar(passo, ok, mensagem):
        passos.append({"passo": passo, "ok": ok, "mensagem": mensagem})

    motorista = payload.get("motorista") or {}
    nome = _limpar(motorista.get("nome"))
    cpf = re.sub(r"\D", "", _limpar(motorista.get("cpf")))
    if not nome or not cpf:
        raise CadastroBsoftError("O Nome e o CPF do motorista sao obrigatorios.")

    motorista_e_proprietario = bool(payload.get("motorista_e_proprietario"))
    cnh = motorista.get("cnh") or {}
    driver_payload = {
        "nome": nome,
        "cpf": cpf,
        "fone": re.sub(r"\D", "", _limpar(motorista.get("fone"))),
        "is_owner": motorista_e_proprietario,
        "rntrc": _limpar(motorista.get("rntrc")),
        "dtNascimento": _formatar_data_api(motorista.get("dtNascimento")),
        "cnh": {
            "numero": _limpar(cnh.get("numero")),
            "seguro": _limpar(cnh.get("seguro")),
            "categoria": _limpar(cnh.get("categoria")),
            "protocolo": _limpar(cnh.get("protocolo")),
            "dtValidade": _formatar_data_api(cnh.get("dtValidade")),
            "dtExpedicao": _formatar_data_api(cnh.get("dtExpedicao")),
            "dtPrimeiraExpedicao": _formatar_data_api(cnh.get("dtPrimeiraExpedicao")),
        },
    }

    driver_existente = bsoft_api.buscar_pessoa_fisica_por_cpf(cpf)
    try:
        if driver_existente:
            driver_response = bsoft_api.atualizar_pessoa_fisica_bsoft(cpf, driver_payload)
        else:
            driver_response = bsoft_api.cadastrar_pessoa_fisica_bsoft(driver_payload)
    except bsoft_api.BsoftApiError as exc:
        registrar("Motorista", False, str(exc))
        return {"ok": False, "passos": passos, "mensagem": str(exc)}

    driver_id = driver_response.get("codPessoa")
    if not driver_id:
        mensagem = "A Bsoft nao retornou o identificador do motorista."
        registrar("Motorista", False, mensagem)
        return {"ok": False, "passos": passos, "mensagem": mensagem}
    registrar("Motorista", True, f"{'Atualizado' if driver_existente else 'Cadastrado'} com sucesso (id {driver_id}).")

    if not driver_existente:
        disponivel = False
        for _tentativa in range(10):
            time.sleep(2)
            if bsoft_api.buscar_pessoa_fisica_por_cpf(cpf):
                disponivel = True
                break
        if not disponivel:
            mensagem = "A API da Bsoft nao disponibilizou o motorista a tempo para vincular o endereco."
            registrar("Endereco do motorista", False, mensagem)
            return {"ok": False, "passos": passos, "mensagem": mensagem}

    endereco_payload = montar_endereco_motorista(db, payload.get("endereco") or {})
    if endereco_payload.get("logradouro"):
        try:
            bsoft_api.cadastrar_endereco_bsoft(driver_id, endereco_payload)
            registrar("Endereco do motorista", True, "Endereco salvo com sucesso.")
        except bsoft_api.BsoftApiError as exc:
            registrar("Endereco do motorista", False, str(exc))
            return {"ok": False, "passos": passos, "mensagem": str(exc)}
    else:
        registrar("Endereco do motorista", True, "Nenhum endereco informado, etapa pulada.")

    owner_id = driver_id
    rntrc_final = driver_payload["rntrc"]
    if not motorista_e_proprietario:
        proprietario = payload.get("proprietario") or {}
        owner_document = re.sub(r"\D", "", _limpar(proprietario.get("cnpj")))
        if len(owner_document) != 14:
            mensagem = "O CNPJ do proprietario e obrigatorio e deve conter 14 digitos."
            registrar("Proprietario", False, mensagem)
            return {"ok": False, "passos": passos, "mensagem": mensagem}

        tipo_map = {"ETC": "E", "CTC": "C", "Equiparado": "EQ"}
        pj_payload = {
            "cnpj": owner_document,
            "razao_social": _limpar(proprietario.get("razao_social")),
            "tipoTransportadora": tipo_map.get(_limpar(proprietario.get("tipo"))),
            "rntrc": _limpar(proprietario.get("rntrc")),
        }
        if not all(pj_payload.values()):
            mensagem = "Todos os campos do proprietario PJ sao obrigatorios."
            registrar("Proprietario", False, mensagem)
            return {"ok": False, "passos": passos, "mensagem": mensagem}

        owner_existente = bsoft_api.buscar_pessoa_juridica_por_cnpj(owner_document)
        try:
            if owner_existente:
                owner_response = bsoft_api.atualizar_pessoa_juridica_bsoft(owner_document, pj_payload)
            else:
                owner_response = bsoft_api.cadastrar_pessoa_juridica_bsoft(pj_payload)
        except bsoft_api.BsoftApiError as exc:
            registrar("Proprietario", False, str(exc))
            return {"ok": False, "passos": passos, "mensagem": str(exc)}

        owner_id = owner_response.get("codPessoa")
        if not owner_id:
            mensagem = "A Bsoft nao retornou o identificador do proprietario."
            registrar("Proprietario", False, mensagem)
            return {"ok": False, "passos": passos, "mensagem": mensagem}
        rntrc_final = pj_payload["rntrc"]
        registrar("Proprietario", True, f"{'Atualizado' if owner_existente else 'Cadastrado'} com sucesso (id {owner_id}).")

        dados_cnpj_lookup = proprietario.get("endereco_cnpj_data") or {}
        if re.sub(r"\D", "", str(dados_cnpj_lookup.get("cnpj", ""))) == owner_document:
            owner_address = montar_endereco_proprietario(db, dados_cnpj_lookup)
            if owner_address.get("logradouro"):
                time.sleep(5)
                try:
                    bsoft_api.cadastrar_endereco_bsoft(owner_id, owner_address)
                    registrar("Endereco do proprietario", True, "Endereco salvo com sucesso.")
                except bsoft_api.BsoftApiError as exc:
                    registrar("Endereco do proprietario", False, str(exc))
                    return {"ok": False, "passos": passos, "mensagem": str(exc)}
    else:
        registrar("Proprietario", True, "Motorista e o proprietario, etapa pulada.")

    slots = []
    if payload.get("cavalo") and _limpar(payload["cavalo"].get("placa")):
        slots.append(payload["cavalo"])
    if payload.get("reboque1") and _limpar(payload["reboque1"].get("placa")):
        slots.append(payload["reboque1"])
    if payload.get("reboque2") and _limpar(payload["reboque2"].get("placa")):
        slots.append(payload["reboque2"])

    if not slots and not payload.get("permitir_sem_veiculo"):
        mensagem = "Nenhum veiculo foi informado para cadastro."
        registrar("Veiculos", False, mensagem)
        return {"ok": False, "passos": passos, "mensagem": mensagem}

    salvos = 0
    for slot in slots:
        try:
            veiculo_payload = montar_veiculo_payload(db, slot, driver_id, owner_id, cpf, rntrc_final, motorista_e_proprietario)
        except CadastroBsoftError as exc:
            registrar(f"Veiculo {slot.get('placa', '')}", False, str(exc))
            return {"ok": False, "passos": passos, "mensagem": str(exc)}

        try:
            bsoft_api.cadastrar_veiculo_bsoft(veiculo_payload)
            registrar(f"Veiculo {slot.get('placa', '')}", True, "Cadastrado com sucesso.")
            salvos += 1
        except bsoft_api.BsoftApiError as exc:
            registrar(f"Veiculo {slot.get('placa', '')}", False, str(exc))
            return {"ok": False, "passos": passos, "mensagem": str(exc)}
        time.sleep(1)

    mensagem = f"Processo concluido com sucesso. {salvos} veiculo(s) salvo(s) para '{nome}'."
    return {"ok": True, "passos": passos, "mensagem": mensagem, "motorista_id": driver_id, "proprietario_id": owner_id}
