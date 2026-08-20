"""OCR de pedidos/CNH/CRLV via Tesseract (motor local, sem custo) + parsing
de PDF de pedido.

Portado de gerenciador_atlantico/servicos/ocr.py, removendo dependencias de
tkinter (dialogo de escolha de cidade vira retorno de candidatos para o
frontend decidir) e trocando a planilha de cidades por consulta ao Postgres.
"""
from __future__ import annotations

import io
import os
import re
import unicodedata
from datetime import datetime

import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image, ImageChops, ImageFilter, ImageOps

_RESOLUCAO_MINIMA_LADO_MAIOR = 1900


def _preprocessar_imagem(image: Image.Image) -> Image.Image:
    """Prepara a imagem para o Tesseract: corrige orientacao EXIF, amplia
    fotos de baixa resolucao, converte para escala de cinza usando o canal
    mais escuro entre R/G/B (em vez da luminancia padrao, que apaga tinta
    colorida como numeros em vermelho contra fundo claro) e borra levemente
    para atenuar o padrao de seguranca repetido no fundo de documentos como
    a CNH, sem destruir o texto real."""
    image = ImageOps.exif_transpose(image).convert("RGB")

    largura, altura = image.size
    maior_lado = max(largura, altura)
    if maior_lado < _RESOLUCAO_MINIMA_LADO_MAIOR:
        fator = _RESOLUCAO_MINIMA_LADO_MAIOR / maior_lado
        image = image.resize((round(largura * fator), round(altura * fator)), Image.LANCZOS)

    r, g, b = image.split()
    cinza = ImageChops.darker(ImageChops.darker(r, g), b)
    cinza = cinza.filter(ImageFilter.GaussianBlur(radius=0.6))
    return ImageOps.autocontrast(cinza, cutoff=1)


def obter_texto_do_arquivo_ocr(caminho_arquivo: str) -> str:
    ext = os.path.splitext(caminho_arquivo)[1].lower()
    if ext == ".pdf":
        with fitz.open(caminho_arquivo) as doc:
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
        image = Image.open(io.BytesIO(img_bytes))
    else:
        image = Image.open(caminho_arquivo)

    image = _preprocessar_imagem(image)
    texto_bloco = pytesseract.image_to_string(image, lang="por", config="--psm 6")
    texto_esparso = pytesseract.image_to_string(image, lang="por", config="--psm 11")
    return f"{texto_bloco}\n{texto_esparso}"


def extrair_dados_pedido_heringer(texto_completo: str) -> list:
    if not texto_completo:
        return []

    produtos_encontrados = []

    padrao_antigo = re.compile(r"(\d{7})\s+(?:(\d{9})\s+)?(FERTILIZANTE.+?)\s+([A-Z\s]+ FILHO)\s+(\d+,\d{2})")
    for match in padrao_antigo.finditer(texto_completo):
        try:
            produtos_encontrados.append(
                {
                    "contrato": match.group(2) if match.group(2) else match.group(1),
                    "produto": match.group(3).strip(),
                    "cliente": match.group(4).strip(),
                    "toneladas": match.group(5).replace(",", "."),
                    "embalagem": "BIG BAG",
                    "cidade": "",
                }
            )
        except Exception:
            continue

    if not produtos_encontrados:
        try:
            cliente_faturamento_match = re.search(
                r"NOME DO CLIENTE DE FATURAMENTO POR EXTENSO\s+([A-Z\s\d]+)", texto_completo.upper()
            )
            cliente_entrega_match = re.search(r"NOME DO CLIENTE PARA ENTREGA\s+([A-Z\s\d]+)", texto_completo.upper())
            cliente_final = (
                cliente_entrega_match.group(1).strip()
                if cliente_entrega_match
                else (cliente_faturamento_match.group(1).strip() if cliente_faturamento_match else "")
            )
            produto_match = re.search(r"FERTILIZANTE[^\n]+", texto_completo.upper())
            embalagem_match = re.search(r"(BAG\s+\d+\s+KG)", texto_completo.upper())
            ordem_match = re.search(r"ORDEM DE\s+VENDA\s+(\d+)", texto_completo.upper())
            quantidade_match = re.search(r"QUANTIDADE\s+(\d+)", texto_completo.upper())
            local_match = re.search(r"LOCAL DE\s+CARREGAMENTO\s+([A-Z\s]+)", texto_completo.upper())

            if produto_match and ordem_match and quantidade_match:
                produtos_encontrados.append(
                    {
                        "contrato": ordem_match.group(1).strip(),
                        "produto": produto_match.group(0).strip(),
                        "cliente": cliente_final,
                        "toneladas": quantidade_match.group(1).strip(),
                        "embalagem": embalagem_match.group(1).strip() if embalagem_match else "BAG 1000 KG",
                        "cidade": local_match.group(1).strip() if local_match else "",
                    }
                )
        except Exception:
            pass

    return produtos_encontrados


def extrair_dados_cnh_com_azure_api(texto_completo: str) -> dict:
    if not texto_completo:
        return {}

    dados_cnh = {
        "nome": "Nao encontrado",
        "cpf": "Nao encontrado",
        "numero": "Nao encontrado",
        "seguro": "Nao encontrado",
        "categoria": "Nao encontrada",
        "protocolo": "Nao encontrado",
        "dtValidade": "Nao encontrada",
        "dtExpedicao": "Nao encontrada",
        "dtPrimeiraExpedicao": "Nao encontrada",
        "dtNascimento": "Nao encontrada",
    }

    texto_upper = texto_completo.upper()

    nome_encontrado = None
    m_nome = re.search(r"-?\s*NOME\s*\n([A-Z\sÇÃÕÁÉÍÓÚÀÂÊÔ,.]+)", texto_upper)
    if m_nome:
        nome_bruto = m_nome.group(1).strip()
        if " " in nome_bruto and len(nome_bruto) > 5:
            nome_encontrado = " ".join(nome_bruto.split())
    if not nome_encontrado:
        m_nome_hab = re.search(r"1ª HABILITAÇÃO\s*\n([A-Z\sÇÃÕÁÉÍÓÚÀÂÊÔ,.]+)", texto_upper)
        if m_nome_hab:
            nome_bruto = m_nome_hab.group(1).strip()
            if " " in nome_bruto and len(nome_bruto) > 5:
                nome_encontrado = " ".join(nome_bruto.split())
    if not nome_encontrado:
        m_nome_final = re.search(r"\b([A-Z]+(?: < [A-Z]+)+)\s*$", texto_upper)
        if m_nome_final:
            nome_encontrado = m_nome_final.group(1).strip().replace(" < ", " ")
    if nome_encontrado:
        dados_cnh["nome"] = nome_encontrado

    categoria_encontrada = None
    m_cat = re.search(r"CAT\.?\s*HAB\.?\s*\n?([A-Z]{1,2})", texto_upper)
    if m_cat:
        cat_bruta = re.sub(r"[^A-Z]", "", m_cat.group(1))
        if cat_bruta:
            categoria_encontrada = cat_bruta
    if not categoria_encontrada:
        for cat in ["AE", "AD", "AC", "AB", "E", "D", "C"]:
            if re.search(r"\b" + cat + r"\b", texto_upper):
                categoria_encontrada = cat
                break
    if categoria_encontrada:
        dados_cnh["categoria"] = categoria_encontrada

    m_cpf = re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", texto_upper)
    if not m_cpf:
        m_cpf = re.search(r"\b\d{11}\b", texto_upper)
    if m_cpf:
        dados_cnh["cpf"] = m_cpf.group()

    todas_datas = []
    datas_concatenadas = set()
    for d in re.findall(r"(\d{1,2}/\d{1,2}/\d{4})", texto_upper):
        try:
            dt = datetime.strptime(d, "%d/%m/%Y")
            todas_datas.append(dt)
            datas_concatenadas.add(dt.strftime("%d%m%Y"))
        except ValueError:
            continue

    todas_datas = sorted(set(todas_datas))

    def fmt(idx):
        return todas_datas[idx].strftime("%d/%m/%Y") if -len(todas_datas) <= idx < len(todas_datas) else "Nao encontrada"

    if todas_datas:
        if len(todas_datas) >= 4:
            dados_cnh["dtNascimento"] = fmt(0)
            dados_cnh["dtPrimeiraExpedicao"] = fmt(1)
            dados_cnh["dtExpedicao"] = fmt(2)
            dados_cnh["dtValidade"] = fmt(-1)
        elif len(todas_datas) >= 3:
            dados_cnh["dtNascimento"] = fmt(0)
            dados_cnh["dtExpedicao"] = fmt(1)
            dados_cnh["dtValidade"] = fmt(-1)
        elif len(todas_datas) >= 1:
            dados_cnh["dtValidade"] = fmt(-1)

    numeros_11 = set(re.findall(r"\b(\d{11})\b", texto_upper))
    cpf_limpo = re.sub(r"\D", "", dados_cnh["cpf"])
    numeros_11.discard(cpf_limpo)
    if numeros_11:
        dados_cnh["numero"] = numeros_11.pop()
        dados_cnh["seguro"] = numeros_11.pop() if numeros_11 else "Nao encontrado"

    candidatos_10_digitos = set(re.findall(r"\b(\d{10})\b", texto_upper))
    exclusoes = set()
    for data in datas_concatenadas:
        for candidato in candidatos_10_digitos:
            if data in candidato:
                exclusoes.add(candidato)
    candidatos_finais = candidatos_10_digitos.difference(exclusoes)

    m_proto_valida = re.search(r"(?:\d{1,2})?\s*VÁLIDA EM TODO.*?\n?(\d{10})", texto_upper)
    if m_proto_valida:
        dados_cnh["protocolo"] = m_proto_valida.group(1)
    elif candidatos_finais:
        dados_cnh["protocolo"] = candidatos_finais.pop()

    return dados_cnh


def extrair_dados_crlv_com_azure_api(texto_completo: str, marcas_conhecidas: list[str], tipos_carroceria: dict) -> dict:
    if not texto_completo:
        return {}

    dados_crlv = {}
    texto_upper_com_linhas = texto_completo.upper()
    texto_upper_linha_unica = texto_upper_com_linhas.replace("\n", " ")
    linhas = texto_upper_com_linhas.split("\n")

    try:
        placas_possiveis = re.findall(r"([A-Z]{3}\d[A-Z0-9]\d{2})", texto_upper_com_linhas)
        if placas_possiveis:
            placa_crua = placas_possiveis[0]
            dados_crlv["placa"] = f"{placa_crua[:3]}-{placa_crua[3:]}" if len(placa_crua) == 7 else placa_crua

        match = re.search(r"C[OÓ]DIGO RENAVAM\s*\n\s*(\d{9,11})", texto_upper_com_linhas)
        if not match:
            match = re.search(r"C[OÓ]DIGO RENAVAM\s.*?(\d{11})", texto_upper_linha_unica)
        if not match:
            match = re.search(r"\b\d{11}\b", texto_upper_linha_unica)
        if match:
            dados_crlv["renavam"] = match.group(1) if match.groups() else match.group()

        match = re.search(r"EIXOS\s*\n\s*(\d+)", texto_upper_com_linhas)
        if not match:
            match = re.search(r"EIXOS\s+.*?\s(\d)\s", texto_upper_linha_unica)
        if match:
            dados_crlv["eixos"] = match.group(1).strip()

        marca_encontrada = None
        try:
            idx = next(i for i, l in enumerate(linhas) if "MARCA / MODELO" in l)
            for linha_busca in linhas[idx + 1 : idx + 8]:
                encontrada = next((m for m in marcas_conhecidas if m in linha_busca), None)
                if encontrada:
                    marca_encontrada = encontrada
                    dados_crlv["marca"] = encontrada
                    dados_crlv["modelo"] = linha_busca.strip().split(encontrada, 1)[1].strip("/ ").strip()
                    break
        except (StopIteration, IndexError):
            pass
        if not marca_encontrada:
            for linha_busca in linhas:
                encontrada = next((m for m in marcas_conhecidas if m in linha_busca), None)
                if encontrada:
                    dados_crlv["marca"] = encontrada
                    resto = linha_busca.strip().split(encontrada, 1)[-1].strip("/ ").strip()
                    if resto:
                        dados_crlv["modelo"] = resto
                    break

        local_encontrado = False
        try:
            idx = next(i for i, l in enumerate(linhas) if "LOCAL" in l)
            for linha_busca in linhas[idx + 1 : idx + 8]:
                match_local = re.search(r"([A-Z\s]+)\s+([A-Z]{2})$", linha_busca.strip())
                if match_local and len(match_local.group(1).strip()) > 3:
                    dados_crlv["cidade"] = " ".join(w.capitalize() for w in match_local.group(1).strip().split())
                    dados_crlv["estado"] = match_local.group(2).strip()
                    local_encontrado = True
                    break
        except (StopIteration, IndexError):
            pass
        if not local_encontrado:
            match_local = re.search(r"\b([A-ZÀ-Ú][A-ZÀ-Ú\s]{3,40})\s+([A-Z]{2})\s+\d{1,2}/\d{1,2}/\d{1,4}", texto_upper_linha_unica)
            if match_local:
                dados_crlv["cidade"] = " ".join(w.capitalize() for w in match_local.group(1).strip().split())
                dados_crlv["estado"] = match_local.group(2).strip()

        categoria_encontrada = False
        try:
            idx = next(i for i, l in enumerate(linhas) if "ESPÉCIE / TIPO" in l)
            for linha_busca in linhas[idx + 1 : idx + 11]:
                linha_upper = linha_busca.upper()
                if "TRACAO CAMINHAO TRATOR" in linha_upper or "CAMINHAO TRATOR" in linha_upper:
                    dados_crlv["categoria_veiculo"] = "CAVALO"
                    categoria_encontrada = True
                    break
                if "CARGA CAMINHAO" in linha_upper:
                    dados_crlv["categoria_veiculo"] = "TRUCK"
                    categoria_encontrada = True
                    break
                if "SEMI-REBOQUE" in linha_upper:
                    dados_crlv["categoria_veiculo"] = "SEMI-REBOQUE 1"
                    categoria_encontrada = True
                    break
        except (StopIteration, IndexError):
            pass
        if not categoria_encontrada:
            if "TRACAO CAMINHAO TRATOR" in texto_upper_linha_unica or "CAMINHAO TRATOR" in texto_upper_linha_unica:
                dados_crlv["categoria_veiculo"] = "CAVALO"
            elif "SEMI-REBOQUE" in texto_upper_linha_unica:
                dados_crlv["categoria_veiculo"] = "SEMI-REBOQUE 1"
            elif "CARGA CAMINHAO" in texto_upper_linha_unica:
                dados_crlv["categoria_veiculo"] = "TRUCK"

        match_carroceria = re.search(r"CARROCERIA\s+([A-ZÀ-Ú/]+)", texto_upper_linha_unica)
        nomes_validos = {nome.replace("Ú", "U"): nome for nome in tipos_carroceria.values()}
        if match_carroceria and match_carroceria.group(1) in nomes_validos:
            dados_crlv["tipo_carroceria"] = nomes_validos[match_carroceria.group(1)]
        else:
            for _codigo, nome in tipos_carroceria.items():
                if nome == "NÃO APLICAVEL":
                    continue
                palavras_chave = re.split(r"[/ ]", nome.replace("Ú", "U"))
                if any(len(p) > 2 and p in texto_upper_linha_unica for p in palavras_chave):
                    dados_crlv["tipo_carroceria"] = nome
                    break
    except Exception:
        pass

    return dados_crlv


def extrair_dados_rntrc_com_azure_api(texto_completo: str) -> dict:
    if not texto_completo:
        return {}
    dados_rntrc = {}
    texto_upper = texto_completo.upper()
    match_rntrc = re.search(r"(\d{8,})", texto_upper.replace("RNTRC", ""))
    if match_rntrc:
        dados_rntrc["rntrc"] = match_rntrc.group(1).strip()
    return dados_rntrc


def classificar_documento(texto: str) -> str:
    upper = normalizar_texto_sem_acento(texto)
    if "CARTEIRA NACIONAL DE HABILITA" in upper:
        return "CNH"
    if "CERTIFICADO DE REGISTRO E LICENCIAMENTO" in upper:
        return "CRLV"
    if "RNTRC" in upper or "TRANSPORTADORES RODOVIARIOS DE CARGAS" in upper:
        return "RNTRC"
    return "DESCONHECIDO"


def normalizar_texto_sem_acento(texto: str) -> str:
    if not isinstance(texto, str):
        texto = str(texto)
    nfkd_form = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd_form if not unicodedata.combining(c)).upper().strip()


def encontrar_cidades_candidatas(texto_pdf: str, cidades: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """cidades: lista de (nome, uf) vinda do banco."""
    lista_plana = [(normalizar_texto_sem_acento(nome), uf, nome) for nome, uf in cidades]

    texto_a_procurar = texto_pdf
    idx_cliente = texto_a_procurar.upper().find("CLIENTE:")
    if idx_cliente != -1:
        texto_a_procurar = texto_a_procurar[idx_cliente:]
    texto_a_procurar = texto_a_procurar.replace("\n", " ")
    texto_normalizado = normalizar_texto_sem_acento(texto_a_procurar)

    lista_ordenada = sorted(lista_plana, key=lambda x: len(x[0]), reverse=True)

    def filtrar_jacuipe(pares):
        return [
            (c, u)
            for c, u in pares
            if "CONCEICAO DO JACUIPE" not in normalizar_texto_sem_acento(c) and "JACUIPE" not in normalizar_texto_sem_acento(c)
        ]

    encontradas = []
    for cidade_norm, uf, cidade_orig in lista_ordenada:
        padrao = r"\b" + re.escape(cidade_norm) + r"[\s/-]+" + re.escape(uf) + r"\b"
        match = re.search(padrao, texto_normalizado)
        if match:
            encontradas.append((match.start(), (cidade_orig, uf)))
    filtradas = filtrar_jacuipe([c for _p, c in sorted(encontradas, key=lambda x: x[0])])
    if filtradas:
        return filtradas

    encontradas_c = []
    for cidade_norm, uf, cidade_orig in lista_ordenada:
        padrao = r"CIDADE\s+" + re.escape(cidade_norm) + r"\b"
        match = re.search(padrao, texto_normalizado)
        if match:
            encontradas_c.append((match.start(), (cidade_orig, uf)))
    filtradas_c = filtrar_jacuipe([c for _p, c in sorted(encontradas_c, key=lambda x: x[0])])
    return filtradas_c


def parse_pdf_fields(pdf_path: str, cidades: list[tuple[str, str]]) -> dict:
    """Retorna {"produtos": [...], "cidades_candidatas": [...]} deixando a
    escolha final da cidade (quando ambigua) para o frontend."""
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join((p.extract_text(x_tolerance=2, y_tolerance=3) or "") for p in pdf.pages)

    candidatas = encontrar_cidades_candidatas(text, cidades)
    cidade = ""
    if len(candidatas) == 1:
        nome, uf = candidatas[0]
        cidade = f"{' '.join(w.capitalize() for w in nome.split())}-{uf}"

    m_cliente = re.search(r"CLIENTE:\s*(.+)", text, re.MULTILINE)
    cliente = m_cliente.group(1).strip() if m_cliente else None
    m_pedido = re.search(r"Nr\. Pedido\s+(\d+)", text, re.IGNORECASE)
    if not m_pedido:
        m_pedido = re.search(r"N°\s+(\d+)", text, re.IGNORECASE)
    if not m_pedido:
        m_pedido = re.search(r"PIX\s+(\d+)", text, re.IGNORECASE)
    pedido = m_pedido.group(1).strip() if m_pedido else None

    produtos = []
    old_format_lines = [
        line for line in text.splitlines() if re.match(r"^\d{3,}\s*:?", line.strip()) and re.search(r"\d+,\d{1,4}", line)
    ]
    if old_format_lines:
        for line in old_format_lines:
            m_prod = re.search(r":\s*(.+?)\s+(SACO|BIG BAG|GRANEL)", line, re.IGNORECASE)
            produto_nome = m_prod.group(1).strip() if m_prod else line.strip()
            raw_qtd = re.search(r"\d{1,3}(?:\.\d{3})*,\d{1,4}|\d+,\d{1,4}", line).group()
            qtd = float(raw_qtd.replace(".", "").replace(",", "."))
            line_up = line.upper()
            embalagem = "GRANEL" if "GRANEL" in line_up else "BIG BAG" if "BIG BAG" in line_up else "SACARIA" if "SACO" in line_up else "DESCONHECIDA"
            produtos.append({"cliente": cliente, "contrato": pedido, "produto": produto_nome, "toneladas": qtd, "embalagem": embalagem, "cidade": cidade})
    else:
        product_names = [m.group(1).strip() for m in re.finditer(r"^\d{3,}\s*:\s*(.+)", text, re.MULTILINE)]
        detail_lines = [
            line
            for line in text.splitlines()
            if ("SACO" in line.upper() or "BIG BAG" in line.upper() or "GRANEL" in line.upper()) and re.search(r"\d+,\d{1,4}", line)
        ]
        details = []
        for line in detail_lines:
            match_qtd = re.search(r"\d{1,3}(?:\.\d{3})*,\d{1,4}|\d+,\d{1,4}", line)
            qtd = float(match_qtd.group().replace(".", "").replace(",", ".")) if match_qtd else 0
            line_up = line.upper()
            embalagem = "GRANEL" if "GRANEL" in line_up else "BIG BAG" if "BIG BAG" in line_up else "SACARIA" if "SACO" in line_up else "DESCONHECIDA"
            details.append({"toneladas": qtd, "embalagem": embalagem})
        for i in range(min(len(product_names), len(details))):
            produtos.append(
                {
                    "cliente": cliente,
                    "contrato": pedido,
                    "produto": product_names[i],
                    "toneladas": details[i]["toneladas"],
                    "embalagem": details[i]["embalagem"],
                    "cidade": cidade,
                }
            )

    return {"produtos": produtos, "cidades_candidatas": [{"cidade": c, "uf": u} for c, u in candidatas]}
