"""Geracao da Ordem de Coleta via HTML/CSS -> PDF (WeasyPrint).

Substitui o antigo caminho DOCX->PDF para a Ordem de Coleta, permitindo um
layout visual (icones, pilulas arredondadas, sombras, zebra) que o
Word/LibreOffice nao renderiza de forma confiavel.
"""
from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from .documentos import _format_peso_documento, _safe_float

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
DADOS_DIR = Path(__file__).resolve().parents[2] / "dados"

_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

REMETENTE_POR_FORNECEDOR = {
    "AFL": "FERTIMAXI INDÚSTRIA COMÉRCIO E SERVIÇOS DE FERTILIZANTES",
    "HERINGER": "FERTILIZANTES HERINGER S.A.",
}
ENDERECO_REMETENTE = "ROD SALVADOR-FEIRA DE SANTANA, S/N, BR 324 KM 537 - BESSA - CONCEIÇÃO DO JACUÍPE/BA"

MIN_ROWS_PRINT = 6


def _logo_data_uri() -> str:
    logo_path = DADOS_DIR / "logo.svg"
    data = logo_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def gerar_oc_pdf_html(
    template: str,
    produtos: list[dict],
    cpf: str,
    nome: str,
    cnh: str,
    fone: str,
    placa1: str,
    placa2: str,
    placa3: str,
    data_carregamento: str,
    save_path: str,
    observacoes: str = "",
) -> None:
    supplier_key = template.upper() if template.upper() in REMETENTE_POR_FORNECEDOR else "AFL"

    produtos_ctx = [
        {
            "contrato": p.get("contrato", ""),
            "produto": p.get("produto", ""),
            "embalagem": p.get("embalagem", ""),
            "peso": _format_peso_documento(p.get("toneladas")),
            "cidade": p.get("cidade", ""),
            "cliente": p.get("cliente", ""),
        }
        for p in (produtos or [])
    ]
    peso_total = sum(_safe_float(p.get("toneladas")) for p in (produtos or []))

    blank_rows = range(max(0, MIN_ROWS_PRINT - len(produtos_ctx)))

    tpl = _env.get_template("ordem_coleta.html")
    html_str = tpl.render(
        logo_data_uri=_logo_data_uri(),
        data_emissao=datetime.now().strftime("%d/%m/%Y"),
        remetente=REMETENTE_POR_FORNECEDOR[supplier_key],
        endereco=ENDERECO_REMETENTE,
        produtos=produtos_ctx,
        blank_rows=blank_rows,
        peso_total=_format_peso_documento(peso_total),
        motorista_doc=cpf,
        motorista_nome=nome,
        cnh=cnh,
        fone=fone,
        placa1=placa1,
        placa2=placa2,
        placa3=placa3,
        data_carregamento=data_carregamento,
        observacoes=observacoes,
    )

    HTML(string=html_str, base_url=str(TEMPLATES_DIR)).write_pdf(save_path)
