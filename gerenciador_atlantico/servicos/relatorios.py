from ..shared import *

def gerar_pdf_reportlab_ajustado(path_destino, dados_relatorio, filtros_aplicados):
    """
    Cria um PDF do Relatório de Pedidos com um cabeçalho visualmente alinhado e estável,
    posicionando o logo à esquerda e o título no centro da página.
    """
    from reportlab.platypus import Image as ReportLabImage
    
    doc = SimpleDocTemplate(
        path_destino,
        pagesize=landscape(A4),
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch
    )
    styles = getSampleStyleSheet()
    Story = []

    # --- NOVO CABEÇALHO: Simplificado e Robusto ---
    # A melhor prática é usar uma tabela para organizar os elementos do cabeçalho.
    # Criamos uma tabela com 1 linha e 3 colunas: [Logo, Título, Espaço Vazio]
    # A coluna da direita tem a mesma largura do logo para garantir que o título
    # fique perfeitamente centralizado na PÁGINA, e não no espaço restante.

    # 1. Preparar os elementos do cabeçalho
    style_h1 = styles['Heading1']
    style_h1.fontName = 'Arial-Bold'
    style_h1.fontSize = 16
    style_h1.alignment = 1  # 1 = Center

    title_paragraph = Paragraph("ATLÂNTICO FERTLOG", style_h1)
    logo_obj = None
    LOGO_WIDTH = 2.4 * inch
    LOGO_HEIGHT = 1.2 * inch

    try:
        if os.path.exists(LOGO_RELATORIO_PATH):
            logo_obj = ReportLabImage(
                LOGO_RELATORIO_PATH,
                width=LOGO_WIDTH,
                height=LOGO_HEIGHT,
                kind='proportional'
            )
    except Exception as e:
        print(f"Erro ao carregar logo: {e}. Prosseguindo sem a imagem.")
        logo_obj = Paragraph(" ", styles['Normal']) # Usa um parágrafo vazio se a logo falhar

    # 2. Montar a tabela do cabeçalho
    header_data = [[logo_obj, title_paragraph, '']]
    
    # Define a largura das colunas
    page_width = doc.width # Largura útil da página (descontando margens)
    logo_col_width = LOGO_WIDTH
    center_col_width = page_width - (2 * logo_col_width) # Coluna central ocupa o espaço restante

    header_table = Table(header_data, colWidths=[logo_col_width, center_col_width, logo_col_width])
    
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), # Alinha todos os itens verticalmente ao meio
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),      # Alinha o logo (coluna 0) à esquerda
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),    # Alinha o título (coluna 1) ao centro
    ]))
    
    Story.append(header_table)
    Story.append(Spacer(1, 0.2 * inch)) # Espaço entre o cabeçalho e o subtítulo

    # --- 1. Título do Relatório (Subtítulo) ---
    style_h2 = styles['Heading2']
    style_h2.fontName = 'Arial-Bold'
    style_h2.fontSize = 12
    style_h2.alignment = 1  # Centralizado

    titulo_relatorio = f"RELATÓRIO DE PEDIDOS - {dados_relatorio['Periodo']}"
    Story.append(Paragraph(titulo_relatorio, style_h2))
    Story.append(Spacer(1, 0.1 * inch))

    style_normal = styles['Normal']
    style_normal.fontName = 'Arial'
    style_normal.fontSize = 10
    style_normal.alignment = 1

    data_emissao = datetime.now().strftime('%d/%m/%Y')
    filtros_texto = f"Filtros Aplicados: {filtros_aplicados} | Data de Emissão: {data_emissao}"
    Story.append(Paragraph(filtros_texto, style_normal))
    Story.append(Spacer(1, 0.2 * inch))

    # --- 2. Tabela de Detalhes ---
    headers = ["Data Pedido", "Nro. Pedido", "Cliente", "Cidade Dest.", "Roteiro", "Peso (Ton)", "Valor Frete"]
    
    table_data = [headers]
    for item in dados_relatorio['Itens']:
        table_data.append([
            item.get('Data Pedido', ''),
            item.get('Nro. Pedido', ''),
            item.get('Cliente', ''),
            item.get('Cidade Dest.', ''),
            item.get('Roteiro', ''),
            item.get('Peso (Ton)', ''),
            item.get('Valor Frete', ''),
        ])

    col_widths = [1.0*inch, 1.0*inch, 2.5*inch, 1.8*inch, 1.5*inch, 1.0*inch, 1.2*inch]
    t = Table(table_data, colWidths=col_widths)
    
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#04D9C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Arial-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
    ])
    t.setStyle(table_style)
    Story.append(t)
    Story.append(Spacer(1, 0.3 * inch))

    # --- 3. Totais ---
    totais = [
        ["Total Geral de Pedidos: ", str(dados_relatorio['Total Geral de Pedidos'])],
        ["Peso Total (Ton): ", f"{dados_relatorio['Peso Total (Ton)']:.2f}".replace('.', ',')],
        ["Média do Frete/Ton: ", f"R$ {dados_relatorio['Media Frete / Ton']:.2f}".replace('.', ',')],
    ]

    t_totais = Table(totais, colWidths=[2.5*inch, 1.2*inch], hAlign='RIGHT')
    t_totais_style = TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (0, -1), 'Arial'),
        ('FONTNAME', (1, 0), (1, -1), 'Arial-Bold'),
        ('BACKGROUND', (0, 0), (-1, -1), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ])
    t_totais.setStyle(t_totais_style)
    Story.append(t_totais)

    # --- 4. Construir o PDF ---
    doc.build(Story)

def _clean(s): return re.sub(r"\s+", " ", str(s)).strip() if s is not None else ""

def _format_peso(v):
    if v is None: return ""
    try:
        v_str = str(v).replace(',', '.')
        f = float(v_str)
        formatted_str = f"{f:.3f}".rstrip('0').rstrip('.')
        if not formatted_str:
            return "0"
        return formatted_str
    except (ValueError, TypeError):
        return _clean(v)
    
def formatar_moeda_brasileira(valor_str: str) -> str:
    if not valor_str:
        return ""
    try:
        try:
            locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
        except locale.Error:
            locale.setlocale(locale.LC_ALL, 'Portuguese_Brazil.1252')
        valor_limpo = valor_str.replace('.', '').replace(',', '.')
        valor_float = float(valor_limpo)
        valor_formatado = locale.format_string('%.2f', valor_float, grouping=True)
        return valor_formatado
    except (ValueError, locale.Error) as e:
        return valor_str
