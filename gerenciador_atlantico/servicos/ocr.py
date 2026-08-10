from ..shared import *

def obter_texto_do_arquivo_com_azure(caminho_arquivo):
    """Extrai texto de um PDF ou imagem usando Azure OCR."""
    img_bytes = None
    ext = os.path.splitext(caminho_arquivo)[1].lower()

    if ext == ".pdf":
        with fitz.open(caminho_arquivo) as doc:
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
    else:
        with open(caminho_arquivo, "rb") as arquivo:
            img_bytes = arquivo.read()

    client = ImageAnalysisClient(endpoint=AZURE_ENDPOINT, credential=AzureKeyCredential(AZURE_KEY))
    result = client.analyze(image_data=img_bytes, visual_features=[VisualFeatures.READ])
    if not result.read:
        return ""
    return "\n".join(line.text for block in result.read.blocks for line in block.lines)

def extrair_dados_pedido_heringer(texto_completo: str) -> list:
    """[VERSÃO 4 - Multiformato] Extrai produtos de pedidos Heringer, incluindo o layout da Eurochem."""
    if not texto_completo:
        return []

    print("\n--- DEBUG OCR (Pedido Heringer V4 - Multiformato) ---")
    print(texto_completo)
    print("----------------------------------------------------\n")

    produtos_encontrados = []

    # --- TENTATIVA 1: Padrão do formato antigo ---
    padrao_antigo = re.compile(r"(\d{7})\s+(?:(\d{9})\s+)?(FERTILIZANTE.+?)\s+([A-Z\s]+ FILHO)\s+(\d+,\d{2})")
    for match in padrao_antigo.finditer(texto_completo):
        try:
            p = {
                'contrato': match.group(2) if match.group(2) else match.group(1),
                'produto': match.group(3).strip(),
                'cliente': match.group(4).strip(),
                'toneladas': match.group(5).replace(',', '.'),
                'embalagem': "BIG BAG",
                'cidade': ""
            }
            produtos_encontrados.append(p)
        except Exception:
            continue

    # --- TENTATIVA 2: Padrão do novo formato (Eurochem) ---
    # Se o primeiro padrão não encontrou nada, tenta o segundo.
    if not produtos_encontrados:
        try:
            # Extrai os clientes primeiro, pois eles ficam em blocos separados
            cliente_faturamento_match = re.search(r'NOME DO CLIENTE DE FATURAMENTO POR EXTENSO\s+([A-Z\s\d]+)', texto_completo.upper())
            cliente_entrega_match = re.search(r'NOME DO CLIENTE PARA ENTREGA\s+([A-Z\s\d]+)', texto_completo.upper())
            
            # Prioriza o cliente de entrega, se existir
            cliente_final = cliente_entrega_match.group(1).strip() if cliente_entrega_match else (cliente_faturamento_match.group(1).strip() if cliente_faturamento_match else "")
            
            # Extrai os dados da tabela de produtos
            produto_match = re.search(r'FERTILIZANTE[^\n]+', texto_completo.upper())
            embalagem_match = re.search(r'(BAG\s+\d+\s+KG)', texto_completo.upper())
            ordem_match = re.search(r'ORDEM DE\s+VENDA\s+(\d+)', texto_completo.upper())
            quantidade_match = re.search(r'QUANTIDADE\s+(\d+)', texto_completo.upper())
            local_match = re.search(r'LOCAL DE\s+CARREGAMENTO\s+([A-Z\s]+)', texto_completo.upper())
            
            if produto_match and ordem_match and quantidade_match:
                p = {
                    'contrato': ordem_match.group(1).strip(),
                    'produto': produto_match.group(0).strip(),
                    'cliente': cliente_final,
                    'toneladas': quantidade_match.group(1).strip(),
                    'embalagem': embalagem_match.group(1).strip() if embalagem_match else "BAG 1000 KG",
                    'cidade': local_match.group(1).strip() if local_match else ""
                }
                produtos_encontrados.append(p)
                
        except Exception as e:
            print(f"Erro ao processar formato Eurochem: {e}")

    return produtos_encontrados

def extrair_dados_cnh_com_azure_api(texto_completo: str) -> dict:
    """
    [VERSÃO OTIMIZADA POR EXCLUSÃO]
    Extrai dados da CNH a partir de um texto já processado por OCR,
    isolando o protocolo por exclusão.
    """
    if not texto_completo:
        return {}

    print("\n--- INÍCIO DO DEBUG OCR (CNH com Múltiplos Métodos) ---")
    print(texto_completo)
    print("--- FIM DO DEBUG OCR ---\n")

    dados_cnh = {
        "nome": "Não encontrado", "cpf": "Não encontrado",
        "numero": "Não encontrado", "seguro": "Não encontrado",
        "categoria": "Não encontrada", "protocolo": "Não encontrado",
        "dtValidade": "Não encontrada", "dtExpedicao": "Não encontrada",
        "dtPrimeiraExpedicao": "Não encontrada", "dtNascimento": "Não encontrada"
    }

    texto_upper = texto_completo.upper()

    # --- LÓGICA DE EXTRAÇÃO DE NOME E CATEGORIA (MANTIDA) ---
    nome_encontrado = None
    m_nome = re.search(r'-?\s*NOME\s*\n([A-Z\sÇÃÕÁÉÍÓÚÀÂÊÔ,.]+)', texto_upper)
    if m_nome:
        nome_bruto = m_nome.group(1).strip()
        if ' ' in nome_bruto and len(nome_bruto) > 5:
            nome_encontrado = ' '.join(nome_bruto.split())
    if not nome_encontrado:
        m_nome_hab = re.search(r'1ª HABILITAÇÃO\s*\n([A-Z\sÇÃÕÁÉÍÓÚÀÂÊÔ,.]+)', texto_upper)
        if m_nome_hab:
            nome_bruto = m_nome_hab.group(1).strip()
            if ' ' in nome_bruto and len(nome_bruto) > 5:
                nome_encontrado = ' '.join(nome_bruto.split())
    if not nome_encontrado:
        m_nome_final = re.search(r'\b([A-Z]+(?: < [A-Z]+)+)\s*$', texto_upper)
        if m_nome_final:
            nome_com_tags = m_nome_final.group(1).strip()
            nome_encontrado = nome_com_tags.replace(' < ', ' ')
    if nome_encontrado:
        dados_cnh["nome"] = nome_encontrado

    categoria_encontrada = None
    m_cat = re.search(r'CAT\.?\s*HAB\.?\s*\n?([A-Z]{1,2})', texto_upper)
    if m_cat:
        cat_bruta = re.sub(r'[^A-Z]', '', m_cat.group(1))
        if cat_bruta:
            categoria_encontrada = cat_bruta
    if not categoria_encontrada:
        categorias_validas = ['AE', 'AD', 'AC', 'AB', 'E', 'D', 'C']
        for cat in categorias_validas:
            if re.search(r'\b' + cat + r'\b', texto_upper):
                categoria_encontrada = cat
                break
    if categoria_encontrada:
        dados_cnh["categoria"] = categoria_encontrada
    
    # --- FIM DA EXTRAÇÃO DE NOME E CATEGORIA ---

    # --- EXTRAÇÃO DE CPF E DATAS (PARA USO NA EXCLUSÃO) ---
    m_cpf = re.search(r"(\d{3}\.?\d{3}\.?\d{3}-?\d{2})", texto_upper)
    if m_cpf:
        dados_cnh["cpf"] = m_cpf.group(1)
    
    todas_datas = []
    datas_concatenadas = set()
    for d in re.findall(r'(\d{1,2}/\d{1,2}/\d{4})', texto_upper):
        try:
            dt = datetime.strptime(d, "%d/%m/%Y")
            todas_datas.append(dt)
            # Cria a string de data sem barras (para exclusão posterior)
            datas_concatenadas.add(dt.strftime("%d%m%Y"))
        except ValueError:
            continue

    todas_datas = sorted(set(todas_datas))
    def fmt(idx):
        return todas_datas[idx].strftime("%d/%m/%Y") if 0 <= idx < len(todas_datas) else ("Não encontrada" if -len(todas_datas) <= idx < 0 else "Não encontrada")

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


    # --- LÓGICA PARA REGISTRO/SEGURO (11 DÍGITOS) ---
    numeros_11 = set(re.findall(r'\b(\d{11})\b', texto_upper))
    cpf_limpo = re.sub(r'\D', '', dados_cnh["cpf"])
    numeros_11.discard(cpf_limpo)
    if numeros_11:
        dados_cnh["numero"] = numeros_11.pop() 
        dados_cnh["seguro"] = numeros_11.pop() if numeros_11 else "Não encontrado"
    
    # ====================================================================
    # LÓGICA DE EXCLUSÃO PARA O NÚMERO DO ESPELHO/PROTOCOLO (10 DÍGITOS)
    # ====================================================================

    # 1. Encontra todos os números de 10 dígitos (candidatos a protocolo)
    candidatos_10_digitos = set(re.findall(r'\b(\d{10})\b', texto_upper))
    
    # 2. Prepara listas de exclusão
    exclusoes = set()
    
    # Exclui datas (DDMMAAAA, que são 8, mas se forem lidas com mais 2 dígitos aleatórios)
    for data in datas_concatenadas:
        for candidato in candidatos_10_digitos:
            # Se 8 dígitos da data estiverem contidos no 10 dígitos, exclui
            if data in candidato:
                exclusoes.add(candidato)

    # Exclui números que já foram encontrados ou não são protocolos
    # O protocolo da CNH digital sempre é um número de 10 dígitos
    
    # 3. Faz a exclusão
    candidatos_finais = candidatos_10_digitos.difference(exclusoes)

    # 4. Tenta encontrar o Protocolo no contexto de "VÁLIDA EM TODO O TERRITÓRIO NACIONAL"
    m_proto_valida = re.search(r'(?:\d{1,2})?\s*VÁLIDA EM TODO.*?\n?(\d{10})', texto_upper)
    
    if m_proto_valida:
        # Se achou no contexto certo, prioriza ele
        dados_cnh["protocolo"] = m_proto_valida.group(1)
    elif candidatos_finais:
        # Se o contexto falhou, usa o que sobrou após as exclusões
        dados_cnh["protocolo"] = candidatos_finais.pop() 
    else:
        dados_cnh["protocolo"] = "Não encontrado" 

    # ====================================================================
    
    return dados_cnh

def extrair_dados_crlv_com_azure_api(texto_completo: str) -> dict:
    """[VERSÃO FINAL COM FORMATAÇÃO] Extração de carroceria dinâmica e placa formatada."""
    if not texto_completo:
        return {}

    dados_crlv = {}
    texto_upper_com_linhas = texto_completo.upper()
    texto_upper_linha_unica = texto_upper_com_linhas.replace('\n', ' ')
    linhas = texto_upper_com_linhas.split('\n')

    print("\n--- DEBUG OCR (VERSÃO FINAL COM FORMATAÇÃO) ---")
    print(texto_upper_com_linhas)
    print("-----------------------------------------------\n")

    try:
        # --- PLACA [COM FORMATAÇÃO DE HÍFEN] ---
        placas_possiveis = re.findall(r'([A-Z]{3}\d[A-Z0-9]\d{2})', texto_upper_com_linhas)
        if placas_possiveis:
            placa_crua = placas_possiveis[0]
            # Adiciona o hífen se a placa tiver 7 caracteres
            if len(placa_crua) == 7:
                dados_crlv['placa'] = f"{placa_crua[:3]}-{placa_crua[3:]}"
            else:
                dados_crlv['placa'] = placa_crua # Mantém como está se não tiver 7 caracteres

        # --- RENAVAM ---
        match = re.search(r'C[OÓ]DIGO RENAVAM\s*\n\s*(\d{9,11})', texto_upper_com_linhas)
        if not match:
            match = re.search(r'C[OÓ]DIGO RENAVAM\s.*?(\d{11})', texto_upper_linha_unica)
        if match:
            dados_crlv['renavam'] = match.group(1).strip()
            
        # --- EIXOS ---
        match = re.search(r'EIXOS\s*\n\s*(\d+)', texto_upper_com_linhas)
        if not match:
            match = re.search(r'EIXOS\s+.*?\s(\d)\s', texto_upper_linha_unica)
        if match:
            dados_crlv['eixos'] = match.group(1).strip()

        # --- LÓGICA DE PROXIMIDADE (BUSCA INTELIGENTE) ---
        # Marca / Modelo
        try:
            idx = next(i for i, l in enumerate(linhas) if "MARCA / MODELO" in l)
            for linha_busca in linhas[idx+1 : idx+8]:
                encontrada = next((m for m in BSOFT_SIMPLE_BRANDS_LIST if m in linha_busca), None)
                if encontrada:
                    bruto = linha_busca.strip()
                    dados_crlv['marca'] = encontrada
                    dados_crlv['modelo'] = bruto.split(encontrada, 1)[1].strip("/ ").strip()
                    break
        except (StopIteration, IndexError): pass

        # Município (Cidade/Estado)
        try:
            idx = next(i for i, l in enumerate(linhas) if "LOCAL" in l)
            for linha_busca in linhas[idx+1 : idx+8]:
                match_local = re.search(r'([A-Z\s]+)\s+([A-Z]{2})$', linha_busca.strip())
                if match_local and len(match_local.group(1).strip()) > 3:
                    dados_crlv['cidade'] = ' '.join(w.capitalize() for w in match_local.group(1).strip().split())
                    dados_crlv['estado'] = match_local.group(2).strip()
                    break
        except (StopIteration, IndexError): pass

        # Espécie/Tipo (Categoria)
        try:
        # 1. Encontra a linha "ESPÉCIE / TIPO"
            idx = next(i for i, l in enumerate(linhas) if "ESPÉCIE / TIPO" in l)

            # 2. Percorre as linhas abaixo da marcação
            for linha_busca in linhas[idx+1 : idx+11]:
                linha_upper = linha_busca.upper()

                # --- Lógica com os termos exatos fornecidos pelo usuário ---

                # Para CAVALO: "TRACAO CAMINHAO TRATOR" ou "CAMINHAO TRATOR"
                if "TRACAO CAMINHAO TRATOR" in linha_upper or "CAMINHAO TRATOR" in linha_upper:
                    dados_crlv['categoria_veiculo'] = 'CAVALO'
                    break

                # Para TRUCK (ou Toco): "CARGA CAMINHAO"
                elif "CARGA CAMINHAO" in linha_upper:
                    dados_crlv['categoria_veiculo'] = 'TRUCK' 
                    break

                # Para SEMI-REBOQUE
                elif "SEMI-REBOQUE" in linha_upper:
                    dados_crlv['categoria_veiculo'] = 'SEMI-REBOQUE 1'
                    break

        except (StopIteration, IndexError): 
            # Se não encontrou "ESPÉCIE / TIPO" ou falhou na busca
            pass
        
        # --- CARROCERIA (LÓGICA DINÂMICA) ---
        carroceria_encontrada = False
        for codigo, nome in BSOFT_TIPOS_CARROCERIA_NOMES.items():
            palavras_chave = re.split(r'[/ ]', nome.replace('Ú', 'U'))
            for palavra in palavras_chave:
                if len(palavra) > 2 and palavra in texto_upper_linha_unica:
                    dados_crlv['tipo_carroceria'] = nome
                    carroceria_encontrada = True
                    break
            if carroceria_encontrada:
                break

    except Exception as e:
        import traceback
        print(f"ERRO AO EXTRAIR DADOS DO CRLV: {e}")
        traceback.print_exc()

    return dados_crlv

def extrair_dados_rntrc_com_azure_api(texto_completo: str) -> dict:
    """Extrai dados do RNTRC/RNTRC a partir de um texto já processado por OCR."""
    if not texto_completo:
        return {}
    
    dados_rntrc = {}
    texto_upper = texto_completo.upper()

    print("\n--- DEBUG OCR (RNTRC) ---")
    print(texto_upper)
    print("------------------------\n")

    # Extrai RNTRC (formato 00.000.000/0000-00 ou só números)
    match_rntrc = re.search(r'(\d{8,})', texto_upper.replace("RNTRC", "")) # Procura por uma sequência longa de números
    if match_rntrc:
        dados_rntrc['rntrc'] = match_rntrc.group(1).strip()
        
    return dados_rntrc








def parse_pdf_fields(pdf_path, lista_cidades, root_window):
    if not os.path.exists("debug_logs"):
        os.makedirs("debug_logs")
    with pdfplumber.open(pdf_path) as pdf:
        raw_text = "\n".join((p.extract_text(x_tolerance=2, y_tolerance=3) or "") for p in pdf.pages)
        text = raw_text
    cidade = wrapper_extracao_cidade(text, lista_cidades, root_window)
    search_block = text.upper().split("PRODUTOS:")[0]
    m_cliente = re.search(r"CLIENTE:\s*(.+)", text, re.MULTILINE)
    cliente = m_cliente.group(1).strip() if m_cliente else None
    m_pedido = re.search(r"Nr\. Pedido\s+(\d+)", text, re.IGNORECASE)
    if not m_pedido: m_pedido = re.search(r"N°\s+(\d+)", text, re.IGNORECASE)
    if not m_pedido: m_pedido = re.search(r"PIX\s+(\d+)", text, re.IGNORECASE)
    pedido = m_pedido.group(1).strip() if m_pedido else None
    produtos = []
    old_format_lines = [line for line in text.splitlines() if re.match(r"^\d{3,}\s*:?", line.strip()) and re.search(r"\d+,\d{1,4}", line)]
    if old_format_lines:
        for line in old_format_lines:
            m_prod = re.search(r":\s*(.+?)\s+(SACO|BIG BAG|GRANEL)", line, re.IGNORECASE)
            produto_nome = m_prod.group(1).strip() if m_prod else line.strip()
            raw_qtd = re.search(r"\d{1,3}(?:\.\d{3})*,\d{1,4}|\d+,\d{1,4}", line).group()
            qtd = float(raw_qtd.replace(".", "").replace(",", "."))
            line_up = line.upper()
            if "BIG BAG" in line_up: embalagem = "BIG BAG"
            elif "GRANEL" in line_up: embalagem = "GRANEL"
            elif "SACO" in line_up: embalagem = "SACARIA"
            else: embalagem = "DESCONHECIDA"
            produtos.append({ "cliente": cliente, "contrato": pedido, "produto": produto_nome, "toneladas": qtd, "embalagem": embalagem, "cidade": cidade })
    else:
        product_names = [m.group(1).strip() for m in re.finditer(r"^\d{3,}\s*:\s*(.+)", text, re.MULTILINE)]
        detail_lines_text = [line for line in text.splitlines() if ("SACO" in line.upper() or "BIG BAG" in line.upper() or "GRANEL" in line.upper()) and re.search(r"\d+,\d{1,4}", line)]
        details = []
        for line in detail_lines_text:
            match_qtd = re.search(r"\d{1,3}(?:\.\d{3})*,\d{1,4}|\d+,\d{1,4}", line)
            if match_qtd:
                qtd_str = match_qtd.group()
                qtd = float(qtd_str.replace(".", "").replace(",", "."))
            else:
                qtd = 0 
            line_up = line.upper()
            embalagem = "DESCONHECIDA"
            if "BIG BAG" in line_up: embalagem = "BIG BAG"
            elif "GRANEL" in line_up: embalagem = "GRANEL"
            elif "SACO" in line_up: embalagem = "SACARIA"
            details.append({"toneladas": qtd, "embalagem": embalagem})
        num_products = min(len(product_names), len(details))
        for i in range(num_products):
            produtos.append({
                "cliente": cliente, "contrato": pedido, "produto": product_names[i],
                "toneladas": details[i]["toneladas"], "embalagem": details[i]["embalagem"],
                "cidade": cidade
            })
    return produtos

def _find_prod_table(doc):
    for t in doc.tables:
        if t.rows and len(t.rows[0].cells) >= 2:
            header = [c.text.strip().lower() for c in t.rows[0].cells]
            if "pedido" in header[0] and "produto" in header[1]: return t
    return None

def _label_key_from_text(text):
    text = text.strip().lower()
    if 'motorista' in text: return 'motorista'
    if 'cnh' in text: return 'cnh'
    if 'fone' in text or 'telefone' in text: return 'fone'
    if 'placa' in text:
        if re.search(r'^\s*1', text): return '1'
        if re.search(r'^\s*2', text): return '2'
        if re.search(r'^\s*3', text): return '3'
    return None

def normalizar_texto_sem_acento(texto):
    if not isinstance(texto, str):
        texto = str(texto)
    nfkd_form = unicodedata.normalize('NFKD', texto)
    texto_sem_acento = u"".join([c for c in nfkd_form if not unicodedata.combining(c)])
    return texto_sem_acento.upper().strip()

# ==============================================================================
# PASSO 1: Use esta função para carregar os dados completos (com IBGE)
# ==============================================================================
def carregar_cidades_nova_logica(caminho_excel):
    """Lê a planilha de cidades com a coluna de código IBGE e retorna um dicionário."""
    cidades_por_uf = {}
    try:
        # header=None garante que a primeira linha seja lida como dados
        df = pd.read_excel(caminho_excel, header=None)
        # Itera sobre as linhas do DataFrame
        for index, row in df.iterrows():
            try:
                cidade = str(row[0]).strip()
                uf = str(row[1]).strip().upper()
                ibge_code = str(row[2]).strip()
                
                if cidade and uf and ibge_code:
                    if uf not in cidades_por_uf:
                        cidades_por_uf[uf] = []
                    # Armazena o nome original da cidade e o código IBGE
                    cidades_por_uf[uf].append((cidade, ibge_code))
            except (IndexError, KeyError):
                # Ignora linhas que não têm 3 colunas
                print(f"Aviso: Linha {index+1} da planilha de cidades está incompleta e foi ignorada.")
                continue
        # Ordena as cidades dentro de cada UF para consistência
        for uf in cidades_por_uf:
            cidades_por_uf[uf].sort()
        return cidades_por_uf
    except FileNotFoundError:
        messagebox.showerror("Erro Crítico", f"A planilha de cidades não foi encontrada: {caminho_excel}")
        return {}
    except Exception as e:
        messagebox.showerror("Erro Crítico", f"Ocorreu um erro ao ler a planilha de cidades: {e}")
        return {}





# ==============================================================================
# PASSO 2: Substitua encontrar_cidades_candidatas por esta versão ADAPTADA
# ==============================================================================
def encontrar_cidades_candidatas(texto_pdf, cidades_por_uf):
    """
    [VERSÃO FINAL CORRIGIDA] Lógica de busca com filtro para cidade remetente funcionando.
    """
    print("\n\n--- INICIANDO DEBUG DE BUSCA DE CIDADE (LÓGICA AVANÇADA) ---")
    
    lista_plana_cidades = []
    for uf, cidades_tuplas in cidades_por_uf.items():
        for cidade_tupla in cidades_tuplas:
            cidade_original = cidade_tupla[0]
            cidade_normalizada = normalizar_texto_sem_acento(cidade_original)
            lista_plana_cidades.append((cidade_normalizada, uf, cidade_original))

    texto_a_procurar = texto_pdf
    idx_cliente = texto_a_procurar.upper().find("CLIENTE:")
    if idx_cliente != -1:
        texto_a_procurar = texto_a_procurar[idx_cliente:]
    
    texto_a_procurar = texto_a_procurar.replace('\n', ' ')
    texto_normalizado = normalizar_texto_sem_acento(texto_a_procurar)
    
    print(f"\n[DEBUG] O TEXTO A SER PESQUISADO É:\n{texto_normalizado}\n{'-'*50}")

    cidades_encontradas = []
    lista_cidades_ordenada = sorted(lista_plana_cidades, key=lambda x: len(x[0]), reverse=True)

    # --- PLANO A: ESTRATÉGIA PADRÃO OURO ('CIDADE - UF' ou 'CIDADE/UF') ---
    print("[DEBUG] Executando Plano A...")
    for cidade_norm, uf, cidade_orig in lista_cidades_ordenada:
        padrao_flexivel = r'\b' + re.escape(cidade_norm) + r'[\s/-]+' + re.escape(uf) + r'\b'
        match = re.search(padrao_flexivel, texto_normalizado)
        if match:
            posicao = match.start()
            print(f"[DEBUG] SUCESSO (Plano A)! Padrão '{padrao_flexivel}' encontrado.")
            cidades_encontradas.append( (posicao, (cidade_orig, uf)) )

    cidades_ordenadas_a = sorted(cidades_encontradas, key=lambda x: x[0])
    # ↓↓↓ CORREÇÃO APLICADA AQUI ↓↓↓
    cidades_filtradas_a = [(c, u) for p, (c, u) in cidades_ordenadas_a if "CONCEICAO DO JACUIPE" not in normalizar_texto_sem_acento(c) and "JACUIPE" not in normalizar_texto_sem_acento(c)]
    if cidades_filtradas_a:
        print(f"[DEBUG] Resultado do Plano A: {cidades_filtradas_a}")
        print("--- FIM DO DEBUG DE BUSCA DE CIDADE ---\n\n")
        return cidades_filtradas_a

    # --- PLANO B: ESPECIALISTA NO PADRÃO "FRANKENSTEIN" ---
    print("DEBUG - Plano A falhou. Ativando Plano B...")
    # (A lógica do Plano B não precisa de filtro, pois é muito específica)
    bloco_separador = "CONCEICAO DO JACUIPE - BA. E-MAIL COMERCIAL@FERTIMAXI.COM.BR,"
    padrao_quebrado = fr"CIDADE\s+(.*?)\s*{re.escape(bloco_separador)}\s*(.*?)(?:,|$|\sTELEFONES)"
    match = re.search(padrao_quebrado, texto_normalizado)
    if match:
        inicio_cidade = match.group(1).strip()
        fim_cidade_uf = match.group(2).strip()
        nome_reconstruido = f"{inicio_cidade} {fim_cidade_uf}".strip()
        print(f"DEBUG - Plano B encontrou padrão quebrado. Nome reconstruído: '{nome_reconstruido}'")
        for cidade_norm, uf, cidade_orig in lista_cidades_ordenada:
            if cidade_norm in nome_reconstruido and uf in nome_reconstruido:
                print(f"[DEBUG] SUCESSO (Plano B)! Cidade encontrada: {cidade_orig}, {uf}")
                print("--- FIM DO DEBUG DE BUSCA DE CIDADE ---\n\n")
                return [(cidade_orig, uf)]

    # --- PLANO C: BUSCA DE SEGURANÇA ('CIDADE NOME_DA_CIDADE') ---
    print("DEBUG - Plano B falhou. Ativando Plano C...")
    cidades_encontradas_c = []
    for cidade_norm, uf, cidade_orig in lista_cidades_ordenada:
        padrao_contexto = r'CIDADE\s+' + re.escape(cidade_norm) + r'\b'
        match = re.search(padrao_contexto, texto_normalizado)
        if match:
            posicao = match.start()
            print(f"[DEBUG] SUCESSO (Plano C)! Padrão '{padrao_contexto}' encontrado.")
            cidades_encontradas_c.append( (posicao, (cidade_orig, uf)) )
    
    if cidades_encontradas_c:
        cidades_ordenadas_c = sorted(cidades_encontradas_c, key=lambda x: x[0])
        # ↓↓↓ CORREÇÃO APLICADA AQUI TAMBÉM ↓↓↓
        cidades_filtradas_c = [(c, u) for p, (c, u) in cidades_ordenadas_c if "CONCEICAO DO JACUIPE" not in normalizar_texto_sem_acento(c) and "JACUIPE" not in normalizar_texto_sem_acento(c)]
        if cidades_filtradas_c:
            print(f"[DEBUG] Resultado do Plano C: {cidades_filtradas_c}")
            print("--- FIM DO DEBUG DE BUSCA DE CIDADE ---\n\n")
            return cidades_filtradas_c

    print("DEBUG - Nenhum dos planos encontrou uma cidade de cliente válida.")
    print("--- FIM DO DEBUG DE BUSCA DE CIDADE ---\n\n")
    return []





def ask_user_to_choose_nova_logica(options, parent):
    if not options:
        return None, None
    if parent is None:
        return options[0]
    dialog = Toplevel(parent)
    dialog.title("Escolha a Cidade Correta")
    dialog.geometry("400x250")
    dialog.transient(parent)
    dialog.grab_set()
    Label(dialog, text="\nForam encontradas múltiplas cidades.\nPor favor, selecione a correta:\n", font=("Helvetica", 10)).pack()
    selection = StringVar(value=f"{options[0][0]},{options[0][1]}")
    for cidade, uf in options:
        texto_opcao = f"{cidade} - {uf}"
        valor_opcao = f"{cidade},{uf}"
        Radiobutton(dialog, text=texto_opcao, variable=selection, value=valor_opcao, indicatoron=0, width=40, padx=10, pady=5).pack()
    def on_ok():
        dialog.destroy()
    Button(dialog, text="Confirmar", command=on_ok, width=15).pack(pady=20)
    parent.wait_window(dialog)
    cidade_escolhida, uf_escolhida = selection.get().split(',')
    return cidade_escolhida, uf_escolhida

def wrapper_extracao_cidade(texto_pdf, lista_cidades, root_window):
    candidatas = encontrar_cidades_candidatas(texto_pdf, lista_cidades)
    cidade_final, uf_final = (None, None)
    if len(candidatas) == 1:
        cidade_final, uf_final = candidatas[0]
    elif len(candidatas) > 1:
        cidade_final, uf_final = ask_user_to_choose_nova_logica(candidatas, root_window)
    if cidade_final and uf_final:
        cidade_bonita = ' '.join(word.capitalize() for word in cidade_final.split())
        return f"{cidade_bonita}-{uf_final}"
    return ""
