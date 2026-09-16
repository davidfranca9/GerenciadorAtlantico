"""Geracao de documentos DOCX (Ordem de Coleta / Carta Frete).

Portado de gerenciador_atlantico/servicos/documentos.py, removendo a
dependencia de tkinter/shared.py para poder rodar em um servidor Linux.
"""
from __future__ import annotations

import locale
import re
import unicodedata
from copy import copy
from datetime import datetime

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from openpyxl import load_workbook
from openpyxl.worksheet.pagebreak import Break

OC_HEADERS = ["Pedido", "Produto", "Embalagem", "Peso (t)", "Cidade/UF", "Cliente"]
OC_COLUMN_WIDTHS_IN = [0.55, 1.55, 0.78, 0.58, 1.05, 1.39]

LABEL_PATTERN = re.compile(
    "((?:Motorista|CNH|Fone|Telefone)|(?:(?:1(?:a|ª)?|2(?:a|ª)?|3(?:a|ª)?)\\s*Placa))",
    re.IGNORECASE,
)
STANDARDIZED_LABELS = {
    "motorista": "Motorista",
    "cnh": "CNH",
    "fone": "Fone",
    "1": "1a Placa",
    "2": "2a Placa",
    "3": "3a Placa",
}


def _clean(s):
    return re.sub(r"\s+", " ", str(s)).strip() if s is not None else ""


def _format_peso(v):
    if v is None:
        return ""
    try:
        v_str = str(v).replace(",", ".")
        f = float(v_str)
        formatted_str = f"{f:.3f}".rstrip("0").rstrip(".")
        return formatted_str or "0"
    except (ValueError, TypeError):
        return _clean(v)


def _format_peso_documento(value):
    text = _format_peso(value)
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return text.replace(".", ",")
    return text


def formatar_moeda_brasileira(valor_str: str) -> str:
    if not valor_str:
        return ""
    try:
        try:
            locale.setlocale(locale.LC_ALL, "pt_BR.UTF-8")
        except locale.Error:
            pass
        valor_limpo = valor_str.replace(".", "").replace(",", ".")
        valor_float = float(valor_limpo)
        return f"{valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except ValueError:
        return valor_str


def _safe_float(value):
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    text = text.replace(" t", "").replace("T", "").strip()
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def calcular_peso_total(produtos):
    return sum(_safe_float(p.get("toneladas")) for p in produtos or [])


def _find_prod_table(doc):
    for t in doc.tables:
        if t.rows and len(t.rows[0].cells) >= 2:
            header = [c.text.strip().lower() for c in t.rows[0].cells]
            if "pedido" in header[0] and "produto" in header[1]:
                return t
    return None


def _label_key_from_text(text):
    text = text.strip().lower()
    if "motorista" in text:
        return "motorista"
    if "cnh" in text:
        return "cnh"
    if "fone" in text or "telefone" in text:
        return "fone"
    if "placa" in text:
        if re.search(r"^\s*1", text):
            return "1"
        if re.search(r"^\s*2", text):
            return "2"
        if re.search(r"^\s*3", text):
            return "3"
    return None


def _set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def _set_cell_text(cell, value, bold=False, size=7.5, align=WD_ALIGN_PARAGRAPH.CENTER, color=None):
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = align
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.0
    run = paragraph.add_run(str(_clean(value)))
    run.font.name = "Arial"
    run._element.rPr.rFonts.set(qn("w:ascii"), "Arial")
    run._element.rPr.rFonts.set(qn("w:hAnsi"), "Arial")
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _set_row_fill(row, fill):
    for cell in row.cells:
        _set_cell_shading(cell, fill)


def _apply_oc_table_geometry(table):
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    try:
        table.style = "Table Grid"
    except Exception:
        pass
    for row in table.rows:
        for idx, width in enumerate(OC_COLUMN_WIDTHS_IN):
            if idx < len(row.cells):
                row.cells[idx].width = Inches(width)


def _replace_paragraph_text(paragraph, replacements):
    if not paragraph.runs:
        return
    full_text = "".join(run.text for run in paragraph.runs)
    updated = full_text
    for key, value in replacements.items():
        updated = updated.replace(key, str(value or ""))
    if updated == full_text:
        return
    paragraph.runs[0].text = updated
    for run in paragraph.runs[1:]:
        run.text = ""


def _iter_all_paragraphs(parent):
    for paragraph in getattr(parent, "paragraphs", []):
        yield paragraph
    for table in getattr(parent, "tables", []):
        for row in table.rows:
            for cell in row.cells:
                yield from _iter_all_paragraphs(cell)


def fill_products_in_existing_table(doc, produtos):
    table = _find_prod_table(doc)
    if not table:
        return

    while len(table.columns) < len(OC_HEADERS):
        table.add_column(Inches(0.45))

    _apply_oc_table_geometry(table)

    while len(table.rows) > 1:
        table._tbl.remove(table.rows[1]._tr)

    header_row = table.rows[0]
    _set_row_fill(header_row, "FFFFFF")
    for cell, header in zip(header_row.cells, OC_HEADERS):
        _set_cell_text(cell, header, bold=True, size=7.5, color="000000")

    for p in produtos or []:
        row = table.add_row()
        values = [
            p.get("contrato", ""),
            p.get("produto", ""),
            p.get("embalagem", ""),
            _format_peso_documento(p.get("toneladas")),
            p.get("cidade", ""),
            p.get("cliente", ""),
        ]
        for idx, value in enumerate(values):
            align = WD_ALIGN_PARAGRAPH.LEFT if idx in (1, 5) else WD_ALIGN_PARAGRAPH.CENTER
            _set_cell_text(row.cells[idx], value, size=7.2, align=align)

    total_row = table.add_row()
    _set_row_fill(total_row, "E6F4F1")
    try:
        label_cell = total_row.cells[0].merge(total_row.cells[2])
    except Exception:
        label_cell = total_row.cells[0]
    _set_cell_text(label_cell, "PESO TOTAL", bold=True, size=7.5, align=WD_ALIGN_PARAGRAPH.RIGHT, color="0F3D36")
    _set_cell_text(total_row.cells[3], _format_peso_documento(calcular_peso_total(produtos)), bold=True, size=7.5, color="0F3D36")
    for idx in (4, 5):
        if idx < len(total_row.cells):
            _set_cell_text(total_row.cells[idx], "", size=7.2)

    _apply_oc_table_geometry(table)


def copy_run_style(src_run, dest_run):
    try:
        dest_run.font.name = src_run.font.name
        dest_run.font.size = src_run.font.size
        dest_run.font.bold = src_run.font.bold
        dest_run.font.italic = src_run.font.italic
        dest_run.font.underline = src_run.font.underline
        if src_run.font.color and src_run.font.color.rgb:
            dest_run.font.color.rgb = src_run.font.color.rgb
    except Exception:
        pass


def fill_motorista_and_placas(doc, cpf, nome, cnh, fone, placa1, placa2, placa3):
    motorista = " - ".join(part for part in [cpf, nome] if str(part or "").strip())
    mapping = {"motorista": motorista, "cnh": cnh, "fone": fone, "1": placa1, "2": placa2, "3": placa3}
    for para in _iter_all_paragraphs(doc):
        if ":" not in para.text:
            continue
        matches = list(LABEL_PATTERN.finditer(para.text))
        if matches:
            src_run = para.runs[0] if para.runs else None
            for run in para.runs:
                run.text = ""
            for idx, m in enumerate(matches):
                key = _label_key_from_text(m.group(0))
                if not key:
                    continue
                if idx > 0:
                    sep_run = para.add_run("\t\t")
                    if src_run:
                        copy_run_style(src_run, sep_run)
                val = mapping.get(key, "")
                label = STANDARDIZED_LABELS.get(key)
                label_run = para.add_run(f"{label}:")
                if src_run:
                    copy_run_style(src_run, label_run)
                label_run.font.bold = True
                if val:
                    val_run = para.add_run(f" {val}")
                    if src_run:
                        copy_run_style(src_run, val_run)
                    val_run.font.bold = False


def _replace_date_in_paragraph(paragraph, new_date):
    for run in paragraph.runs:
        if re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", run.text):
            run.text = re.sub(r"\d{1,2}/\d{1,2}/\d{2,4}", new_date, run.text, 1)
            return True
    return False


def gerar_oc_docx(modelo_path, save_path, produtos, cpf, nome, cnh, fone, placa1, placa2, placa3, data_carregamento):
    doc = Document(modelo_path)
    fill_products_in_existing_table(doc, produtos)
    fill_motorista_and_placas(doc, cpf, nome, cnh, fone, placa1, placa2, placa3)

    hoje = datetime.now().strftime("%d/%m/%Y")
    for p in _iter_all_paragraphs(doc):
        if "Emiss" in p.text and re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", p.text):
            _replace_date_in_paragraph(p, hoje)
            break

    doc.save(save_path)


def fill_carta_frete_docx(doc, dados):
    valor_frete_str = str(dados.get("VALOR_FRETE", ""))
    valor_formatado = formatar_moeda_brasileira(valor_frete_str) if valor_frete_str else ""
    valor_com_moeda = f"R$ {valor_formatado}" if valor_formatado else ""
    replacements = {
        "{{DATA}}": dados.get("DATA", ""),
        "{{CONDUTOR}}": dados.get("CONDUTOR", ""),
        "{{CPF}}": dados.get("CPF", ""),
        "{{PLACA_CAVALO}}": dados.get("PLACA_CAVALO", ""),
        "{{VALOR_FRETE}}": valor_com_moeda,
        "{{AUTORIZACAO_NUM}}": dados.get("AUTORIZACAO_NUM", ""),
    }
    used_placeholders = False
    for paragraph in _iter_all_paragraphs(doc):
        if any(key in paragraph.text for key in replacements):
            used_placeholders = True
            _replace_paragraph_text(paragraph, replacements)
    if used_placeholders:
        return

    if valor_frete_str:
        for table in doc.tables:
            encontrado = False
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        if "R$" in p.text and valor_formatado not in p.text:
                            run = p.add_run(" " + valor_formatado)
                            run.font.name = "Calibri (Corpo)"
                            run.font.size = Pt(14)
                            run.font.bold = True
                            encontrado = True
                            break
                    if encontrado:
                        break
                if encontrado:
                    break
            if encontrado:
                break

    mapa_campos_normais = {
        "DATA": "DATA:",
        "CONDUTOR": "CONDUTOR:",
        "CPF": "CPF:",
        "PLACA_CAVALO": "PLACA CAVALO:",
        "AUTORIZACAO_NUM": "AUTORIZAÇÃO Nº:",
    }

    def preencher_tabela(table):
        for row in table.rows:
            for ci, cell in enumerate(row.cells):
                for subtable in cell.tables:
                    preencher_tabela(subtable)
                for p in cell.paragraphs:
                    for chave, rotulo in mapa_campos_normais.items():
                        valor = str(dados.get(chave, ""))
                        if rotulo in p.text and valor not in p.text:
                            if ci + 1 < len(row.cells):
                                target_cell = row.cells[ci + 1]
                                target_cell.text = ""
                                run = target_cell.add_paragraph(valor).runs[0]
                                run.bold = True
                            else:
                                p.add_run(" " + valor).bold = True

    for table in doc.tables:
        preencher_tabela(table)


# --------------------------------------------------------------------------
# Autorizacao de Carregamento (Fertimaxi)
# --------------------------------------------------------------------------

# O modelo da Fertimaxi e um cartao vertical: rotulo na coluna B, valor na C,
# um bloco por pedido. O arquivo traz dois blocos (linhas 2-15 e 17-30); o
# primeiro e o carimbo - estilo, bordas, altura de linha e mesclagens saem
# dele pra quantos pedidos houver, e o rotulo de cada linha e lido do
# arquivo, nunca reescrito aqui.
AUTORIZACAO_BLOCO_INICIO = 2
AUTORIZACAO_BLOCO_LINHAS = 14
AUTORIZACAO_PASSO = 15  # o bloco e a linha em branco que o separa do proximo
AUTORIZACAO_BLOCOS_POR_PAGINA = 2  # como no modelo
TRANSPORTADOR = "ATLÂNTICO FERTLOG"


def _chave_do_rotulo(texto) -> str:
    """'Modelo Veiculo:' -> 'modelo veiculo'. Sem acento e sem dois-pontos,
    pra um ajuste de grafia no modelo nao desligar o campo."""
    limpo = unicodedata.normalize("NFKD", str(texto or ""))
    limpo = "".join(c for c in limpo if not unicodedata.combining(c))
    return _clean(limpo.replace(":", "")).lower()


def _formatar_cpf_documento(cpf) -> str:
    digitos = re.sub(r"\D", "", str(cpf or ""))
    if len(digitos) != 11:
        return _clean(cpf)
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def _formatar_placa_documento(placa) -> str:
    limpa = re.sub(r"[^A-Za-z0-9]", "", str(placa or "")).upper()
    if len(limpa) != 7:
        return _clean(placa).upper()
    return f"{limpa[:3]}-{limpa[3:]}"


def _valores_autorizacao(produto: dict, motorista, cpf, telefone, placas, modelo_veiculo="") -> dict:
    """{rotulo normalizado: valor} de um bloco."""
    placas_informadas = [_formatar_placa_documento(p) for p in placas or () if str(p or "").strip()]
    contrato = _clean(produto.get("contrato"))
    toneladas = _format_peso_documento(produto.get("toneladas"))
    return {
        "cliente": _clean(produto.get("cliente")),
        "pedido": int(contrato) if contrato.isdigit() else contrato,
        "quantidade": f"{toneladas} t" if toneladas else "",
        "produto": _clean(produto.get("produto")),
        "embalagem": _clean(produto.get("embalagem")),
        "transportador": TRANSPORTADOR,
        "motorista": _clean(motorista),
        "cpf": _formatar_cpf_documento(cpf),
        # A carroceria escolhida na Ordem de Coleta. Nao se deduz pelas
        # placas: cavalo + carreta pode ser graneleiro, grade baixa ou sider.
        "modelo veiculo": _clean(modelo_veiculo).upper(),
        "placa": " / ".join(placas_informadas),
        "telefone": _clean(telefone),
    }


def gerar_autorizacao_xlsx(template_path, save_path, produtos, *, motorista="", cpf="", telefone="", placas=(), modelo_veiculo=""):
    """Preenche o modelo da Fertimaxi: um bloco por pedido.

    A data de carregamento nao entra - o modelo nao tem esse campo, e ela ja
    vai no corpo do e-mail que leva a planilha.
    """
    wb = load_workbook(template_path)
    ws = wb.active
    inicio, linhas, passo = AUTORIZACAO_BLOCO_INICIO, AUTORIZACAO_BLOCO_LINHAS, AUTORIZACAO_PASSO

    # Carimbo: o primeiro bloco do modelo, linha a linha.
    carimbo = [
        {
            "altura": ws.row_dimensions[inicio + r].height,
            "rotulo": ws[f"B{inicio + r}"].value,
            "estilo_b": copy(ws[f"B{inicio + r}"]._style),
            "estilo_c": copy(ws[f"C{inicio + r}"]._style),
        }
        for r in range(linhas)
    ]
    mescladas = sorted(
        m.min_row - inicio for m in ws.merged_cells.ranges
        if inicio <= m.min_row < inicio + linhas and (m.min_col, m.max_col) == (2, 3)
    )
    altura_separador = ws.row_dimensions[inicio + linhas].height
    estilo_neutro = copy(ws["B1"]._style)

    # Limpa os blocos de exemplo inteiros antes de carimbar.
    for m in list(ws.merged_cells.ranges):
        ws.unmerge_cells(str(m))
    for linha in range(inicio, ws.max_row + 1):
        for col in "BC":
            celula = ws[f"{col}{linha}"]
            celula.value = None
            celula._style = copy(estilo_neutro)
        ws.row_dimensions[linha].height = None

    blocos = list(produtos or []) or [{}]
    for i, produto in enumerate(blocos):
        topo = inicio + i * passo
        valores = _valores_autorizacao(produto, motorista, cpf, telefone, placas, modelo_veiculo)
        if i:
            ws.row_dimensions[topo - 1].height = altura_separador
            if i % AUTORIZACAO_BLOCOS_POR_PAGINA == 0:
                ws.row_breaks.append(Break(id=topo - 1))
        for r, modelo in enumerate(carimbo):
            linha = topo + r
            ws.row_dimensions[linha].height = modelo["altura"]
            rotulo = ws[f"B{linha}"]
            rotulo._style = copy(modelo["estilo_b"])
            rotulo.value = modelo["rotulo"]
            ws[f"C{linha}"]._style = copy(modelo["estilo_c"])
            valor = valores.get(_chave_do_rotulo(modelo["rotulo"]))
            if r not in mescladas and valor not in (None, ""):
                ws[f"C{linha}"].value = valor
        for r in mescladas:
            ws.merge_cells(f"B{topo + r}:C{topo + r}")

    ultima = inicio + (len(blocos) - 1) * passo + linhas - 1
    ws.print_area = f"B{inicio}:C{ultima}"
    # Uma pagina de largura e altura livre: com o ajuste do modelo (tudo numa
    # pagina so), cinco pedidos ficariam ilegiveis. As quebras acima mantem
    # dois blocos por pagina.
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    wb.save(save_path)
