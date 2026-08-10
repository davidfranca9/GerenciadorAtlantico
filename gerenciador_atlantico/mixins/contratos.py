from ..shared import *
from ..servicos.bsoft_api import *
from ..servicos.comunicacao import *
from ..servicos.comunicacao import _enviar_email
from ..servicos.documentos import *
from ..servicos.ocr import *
from ..servicos.relatorios import *
from ..servicos.startup import *

class ContratosMixin:
    def limpar_dados_oc(self):
        self.entry_nome.delete(0, tk.END)
        self.entry_cpf.delete(0, tk.END)
        self.entry_cnh.delete(0, tk.END)
        self.entry_fone.delete(0, tk.END)
        self.entry_placa1.delete(0, tk.END)
        self.entry_placa2.delete(0, tk.END)
        self.entry_placa3.delete(0, tk.END)
        messagebox.showinfo("Limpeza", "Todos os dados da aba foram limpos.")

    def enviar_email_planilha_geral(self):
        planilha_geral = EXCEL_FILE
        if not os.path.exists(planilha_geral):
            messagebox.showwarning("Aviso", f"A planilha geral '{os.path.basename(planilha_geral)}' ainda não foi encontrada...")
            return
        destinatarios = [
            "agendamento@fertimaxi.com.br", "paulo.moura@fertimaxi.com.br", "luan.santos@fertimaxi.com.br",
        ]
        try:
            dia = int(self.spin_dia.get())
            mes = int(self.spin_mes.get())
            data_carregamento = f"{dia:02d}/{mes:02d}/{self.ano}"
        except ValueError:
            messagebox.showerror("Erro de Data", "O valor para 'Dia' ou 'Mês' não é um número válido.")
            return

        assunto = f"Autorização de Carregamento - Planilha Geral - {data_carregamento}"
        corpo = f"""
        <html><body><p>Favor agendar motorista para {data_carregamento}</p><br>
        <p>Atenciosamente,<br><b>Setor - Expedição</b><br>ATLANTICO FERTLOG SERVICOS & TRANSPORTES</p>
        </body></html>"""
        anexos = [planilha_geral]
        _enviar_email(destinatarios, assunto, corpo, anexos)

    def enviar_email_com_anexos(self):
        if not self.ultimo_pdf_gerado or not os.path.exists(self.ultimo_pdf_gerado):
            messagebox.showwarning("Aviso", "Você precisa gerar a O.C. antes de enviá-la.")
            return

        # --- CORREÇÃO FORNECEDOR ---
        escolha_fornecedor = self.supplier_var.get()
        if escolha_fornecedor == "Heringer": 
            destinatarios = [
                "expedicao.candeias@heringer.com.br", 
                "faturamento.candeias@heringer.com.br" 
            ]
        else: 
            destinatarios = [
                "agendamento@fertimaxi.com.br", 
                "luan.santos@fertimaxi.com.br", 
                "paulo.moura@fertimaxi.com.br",
            ]
        # ---------------------------

        nome_motorista = self.entry_nome.get() or "Motorista"
        placa_cavalo = self.entry_placa1.get() or "N/A"

        # --- CORREÇÃO DATA ---
        data_carregamento = self.data_carregamento_var.get()
        # ---------------------

        assunto = f"Autorização de {nome_motorista} - Placa {placa_cavalo}"
        corpo = f"""
        <html><body><p>Favor agendar motorista para {data_carregamento}</p><br>
        <p>Atenciosamente,<br><b>Setor - Expedição</b><br>ATLANTICO FERTLOG SERVICOS & TRANSPORTES</p>
        </body></html>"""

        anexos = [self.ultimo_pdf_gerado]

        if self.ultima_planilha_gerada and os.path.exists(self.ultima_planilha_gerada):
            anexos.append(self.ultima_planilha_gerada)

        _enviar_email(destinatarios, assunto, corpo, anexos)

    def selecionar_e_preencher_cnh(self):
        caminho_arquivo = filedialog.askopenfilename(
            title="Selecione o PDF ou Imagem da CNH",
            filetypes=[("Arquivos de CNH", "*.pdf *.jpg *.jpeg *.png *.bmp"),("Todos os arquivos", "*.*")]
        )
        if not caminho_arquivo: return

        # CORREÇÃO: Primeiro, obtemos o texto do arquivo usando a função de OCR
        texto_extraido = self._obter_texto_do_arquivo_com_azure(caminho_arquivo)
        if not texto_extraido:
             # A função _obter_texto_do_arquivo_com_azure já mostra o erro
            return

        # Agora, passamos o texto (e não o caminho) para a função de extração
        dados = extrair_dados_cnh_com_azure_api(texto_extraido)
        if not dados:
            messagebox.showerror("Erro", "Não foi possível extrair dados do texto lido no arquivo.")
            return

        self.entry_nome.delete(0, tk.END); self.entry_cpf.delete(0, tk.END); self.entry_cnh.delete(0, tk.END)
        self.entry_nome.insert(0, dados.get("nome", "")); self.entry_cpf.insert(0, dados.get("cpf", "")); self.entry_cnh.insert(0, dados.get("numero", ""))
        messagebox.showinfo("Sucesso", "Dados da CNH preenchidos com sucesso!")

    def selecionar_e_preencher_crlv(self, event=None):
        """
        [VERSÃO ATUALIZADA] Importa dados de um CRLV e preenche o campo de placa correto
        com base na categoria do veículo (Cavalo/Truck vs. Carreta).
        """
        caminho_arquivo = filedialog.askopenfilename(
            title="Selecione o PDF ou Imagem do CRLV",
            filetypes=[("Arquivos de CRLV", "*.pdf *.jpg *.jpeg *.png *.bmp"), ("Todos os arquivos", "*.*")]
        )
        if not caminho_arquivo:
            return

        texto_extraido = self._obter_texto_do_arquivo_com_azure(caminho_arquivo)
        if not texto_extraido:
            return

        dados_crlv = extrair_dados_crlv_com_azure_api(texto_extraido)
        if not dados_crlv:
            messagebox.showerror("Erro", "Não foi possível extrair os dados do CRLV do arquivo selecionado.")
            return

        placa_encontrada = dados_crlv.get("placa", "")
        categoria_veiculo = dados_crlv.get("categoria_veiculo", "").upper()

        if not placa_encontrada:
            messagebox.showwarning("Aviso", "Nenhuma placa foi encontrada no documento.")
            return

        # --- NOVA LÓGICA DE FILTRO ---
        # Se a categoria for CAVALO ou TRUCK, preenche a Placa 1
        if categoria_veiculo in ["CAVALO", "TRUCK"]:
            if not self.entry_placa1.get():
                self.entry_placa1.delete(0, tk.END)
                self.entry_placa1.insert(0, placa_encontrada)
                messagebox.showinfo("Sucesso", f"Placa de {categoria_veiculo} ({placa_encontrada}) inserida no campo 'Placa Cavalo'.")
            else:
                messagebox.showwarning("Aviso", f"O campo 'Placa Cavalo' já está preenchido. A placa {placa_encontrada} não foi inserida.")

        # Para outras categorias (como SEMI-REBOQUE), preenche Placa 2 ou 3
        else:
            if not self.entry_placa2.get():
                self.entry_placa2.delete(0, tk.END)
                self.entry_placa2.insert(0, placa_encontrada)
                messagebox.showinfo("Sucesso", f"Placa de Carreta ({placa_encontrada}) inserida no campo 'Placa Carreta 1'.")
            elif not self.entry_placa3.get():
                self.entry_placa3.delete(0, tk.END)
                self.entry_placa3.insert(0, placa_encontrada)
                messagebox.showinfo("Sucesso", f"Placa de Carreta ({placa_encontrada}) inserida no campo 'Placa Carreta 2'.")
            else:
                messagebox.showwarning("Aviso", "Todos os campos de placa de carreta já estão preenchidos.")

    def atualizar_planilha_google_sheets(self, dados_carta_frete):
        aba = self._conectar_google_sheets("Carta Frete") 
        if aba is None: return

        try:
            autorizacao_para_buscar = dados_carta_frete.get("AUTORIZACAO_NUM")
            if not autorizacao_para_buscar:
                messagebox.showerror("Erro de Dados", "O campo 'Número da Autorização' está vazio.")
                return

            try:
                celula_encontrada = aba.find(autorizacao_para_buscar, in_column=2)
            except gspread.CellNotFound:
                celula_encontrada = None

            if celula_encontrada:
                linha = celula_encontrada.row
                valor_para_atualizar = dados_carta_frete.get("VALOR_FRETE")
                aba.update_cell(linha, 4, valor_para_atualizar)
            else:
                nova_linha = [[
                    dados_carta_frete.get("DATA"), dados_carta_frete.get("AUTORIZACAO_NUM"),
                    dados_carta_frete.get("CONDUTOR"), dados_carta_frete.get("VALOR_FRETE")
                ]]
                proxima_linha_vazia = len(aba.col_values(1)) + 1
                range_para_atualizar = f'A{proxima_linha_vazia}:D{proxima_linha_vazia}'
                aba.update(range_name=range_para_atualizar, values=nova_linha, value_input_option='USER_ENTERED')

        except Exception as e:
            messagebox.showerror("Erro Inesperado", f"Ocorreu um erro ao atualizar a planilha 'Carta Frete':\n\n{e}")

    def setup_contrato_frame(self, parent_frame, today):
        """Configura a página de Contratos com o novo widget de data e outras correções."""

        content_frame = ttk.Frame(parent_frame, style="App.TFrame")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        top_controls_frame = ttk.Frame(content_frame, style="App.TFrame")
        top_controls_frame.pack(fill=tk.X, pady=(0, 15))

        # --- CORREÇÃO 1: NOVO WIDGET DE DATA COM SETAS E BOTÃO DE CALENDÁRIO ---
        date_frame = ttk.Frame(top_controls_frame, style="App.TFrame")
        date_frame.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(date_frame, text="Data de Carregamento", style="App.TLabel").pack(anchor='w', pady=(0,5))

        date_input_frame = ttk.Frame(date_frame, style="App.TFrame")
        date_input_frame.pack(anchor='w')

        self.data_carregamento_var = tk.StringVar(value=today.strftime("%d/%m/%Y"))
        self.date_entry = ttk.Entry(date_input_frame, textvariable=self.data_carregamento_var, font=("Segoe UI", 10), width=12, justify='center')
        self.date_entry.pack(side=tk.LEFT, ipady=4)

        # Frame para os botões de seta
        spin_buttons_frame = ttk.Frame(date_input_frame)
        spin_buttons_frame.pack(side=tk.LEFT, fill='y', padx=(2, 5))

        up_button = ttk.Button(spin_buttons_frame, text="▲", command=self._increment_date, style="Outline.TButton", width=2)
        up_button.pack(fill='x', expand=True, pady=(0, 1))
        down_button = ttk.Button(spin_buttons_frame, text="▼", command=self._decrement_date, style="Outline.TButton", width=2)
        down_button.pack(fill='x', expand=True)

        # Botão do calendário pop-up
        calendar_button = ttk.Button(date_input_frame, text="🗓️", command=self._open_calendar, style="Outline.TButton", width=3)
        calendar_button.pack(side=tk.LEFT, ipady=1)
        # --- FIM DA CORREÇÃO 1 ---

        # (O resto da função continua igual)
        supplier_frame = ttk.Frame(top_controls_frame, style="App.TFrame")
        supplier_frame.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(supplier_frame, text="Fornecedor", style="App.TLabel").pack(anchor='w', pady=(0,5))
        selector_frame = ttk.Frame(supplier_frame)
        selector_frame.pack(anchor='w')
        rb1 = ttk.Radiobutton(selector_frame, text="Fertimaxi", variable=self.supplier_var, value="Fertimaxi", style="Selector.TRadiobutton", command=self._toggle_supplier_mode)
        rb1.pack(side=tk.LEFT)
        rb2 = ttk.Radiobutton(selector_frame, text="Heringer", variable=self.supplier_var, value="Heringer", style="Selector.TRadiobutton", command=self._toggle_supplier_mode)
        rb2.pack(side=tk.LEFT)
        self.mode_container = ttk.Frame(content_frame, style="App.TFrame")
        self.mode_container.pack(fill=tk.X, pady=10)
        self.mode_container.grid_rowconfigure(0, weight=1)
        self.mode_container.grid_columnconfigure(0, weight=1)
        self.btn_select = ttk.Button(self.mode_container, text="📄 Selecionar Contratos (PDF)", command=self.selecionar_pdfs, style="Accent.TButton")
        self.btn_select.grid(row=0, column=0, sticky="ew", ipady=8)
        self.heringer_frame = ttk.Frame(self.mode_container, style="App.TFrame")
        self.heringer_frame.grid(row=0, column=0, sticky="nsew")
        ttk.Label(content_frame, text="Produtos encontrados (dê um duplo clique para editar as toneladas):", style="Small.TLabel").pack(anchor='w', pady=(10,5))
        tree_container = ttk.Frame(content_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)
        cols = ("select", "produto", "toneladas", "embalagem", "pedido", "cliente", "cidade")
        self.tree = ttk.Treeview(tree_container, columns=cols, show="headings", style="App.Treeview")
        self.tree.heading("select", text="Selecionar"); self.tree.column("select", width=80, anchor="center")
        self.tree.heading("produto", text="Produto"); self.tree.column("produto", width=250, anchor="w")
        self.tree.heading("toneladas", text="Toneladas"); self.tree.column("toneladas", width=100, anchor="center")
        self.tree.heading("embalagem", text="Embalagem"); self.tree.column("embalagem", width=120, anchor="center")
        self.tree.heading("pedido", text="Pedido"); self.tree.column("pedido", width=120, anchor="center")
        self.tree.heading("cliente", text="Cliente"); self.tree.column("cliente", width=250, anchor="w")
        self.tree.heading("cidade", text="Cidade"); self.tree.column("cidade", width=180, anchor="w")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<MouseWheel>", lambda event, t=self.tree: self._on_treeview_scroll(event, t))
        self.tree.bind("<Double-1>", self.editar_toneladas); self.tree.bind("<Button-1>", self.toggle_check)
        bottom_buttons_frame = ttk.Frame(content_frame, style="App.TFrame")
        bottom_buttons_frame.pack(fill=tk.X, pady=(15, 0))
        bottom_buttons_frame.columnconfigure((0, 1, 2), weight=1)
        self.btn_pedido_grande = ttk.Button(bottom_buttons_frame, text="📦 Registrar Pedido Grande", command=self.inserir_pedido_grande_na_planilha, style="Outline.TButton"); self.btn_pedido_grande.grid(row=0, column=0, sticky='ew', padx=(0, 10), ipady=5)
        self.btn_insert = ttk.Button(bottom_buttons_frame, text="📥 Inserir na Planilha", command=self.inserir_produtos, style="Outline.TButton"); self.btn_insert.grid(row=0, column=1, sticky='ew', padx=10, ipady=5)
        self.btn_email_contrato = ttk.Button(bottom_buttons_frame, text="✉️ Enviar Planilha Geral", command=self.enviar_email_planilha_geral, style="Outline.TButton"); self.btn_email_contrato.grid(row=0, column=2, sticky='ew', padx=(10, 0), ipady=5)
        heringer_actions_frame = ttk.Frame(self.heringer_frame, style="App.TFrame")
        heringer_actions_frame.pack(pady=(0, 5))
        btn_import_photo = ttk.Button(heringer_actions_frame, text="📸 Importar da Foto do Pedido", command=self._importar_foto_pedido_heringer, style="Accent.TButton"); btn_import_photo.pack(side=tk.LEFT, padx=10, ipady=5)
        btn_add_produto = ttk.Button(heringer_actions_frame, text="➕ Adicionar Produto à Lista", command=self._adicionar_produto_manual, style="Outline.TButton"); btn_add_produto.pack(side=tk.LEFT, padx=10, ipady=5)
        entry_frame = ttk.Frame(self.heringer_frame, style="App.TFrame")
        entry_frame.pack(pady=(5, 15))
        def add_manual_entry(parent, text, width=20):
            frame = ttk.Frame(parent, style="App.TFrame"); ttk.Label(frame, text=text, style="Small.TLabel").pack(anchor='w'); entry = ttk.Entry(frame, font=("Segoe UI", 10), width=width); entry.pack(anchor='w'); frame.pack(side=tk.LEFT, padx=5, fill='x', expand=True); return entry
        self.entry_heringer_pedido = add_manual_entry(entry_frame, "Nº Pedido:"); self.entry_heringer_produto = add_manual_entry(entry_frame, "Produto:", 40); self.entry_heringer_cliente = add_manual_entry(entry_frame, "Cliente:", 30); self.entry_heringer_ton = add_manual_entry(entry_frame, "Toneladas:"); self.entry_heringer_embalagem = add_manual_entry(entry_frame, "Embalagem:"); self.entry_heringer_cidade = add_manual_entry(entry_frame, "Cidade/UF:")
        self._toggle_supplier_mode()

    def _toggle_supplier_mode(self):
        """Alterna a interface entre o modo Fertimaxi (PDF) e Heringer (Manual) usando grid."""
        self.produtos.clear()
        for i in self.tree.get_children():
            self.tree.delete(i)

        escolha = self.supplier_var.get()
        if escolha == "Fertimaxi":
            self.heringer_frame.grid_remove() # Esconde a UI da Heringer
            self.btn_select.grid()           # Mostra o botão de selecionar PDF
        elif escolha == "Heringer":
            self.btn_select.grid_remove()    # Esconde o botão de selecionar PDF
            self.heringer_frame.grid()       # Mostra a UI da Heringer

    def setup_oc_frame(self, parent_frame):
        # Frame principal para agrupar os conteúdos da página
        main_content_frame = ttk.Frame(parent_frame, style="App.TFrame")
        main_content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # Frame superior para os dados do motorista
        top_frame = ttk.Frame(main_content_frame, style="App.TFrame")
        top_frame.pack(fill=tk.X, pady=(0, 20))

        # --- Coluna da Esquerda (Dados do Motorista) ---
        left_column = ttk.Frame(top_frame, style="App.TFrame")
        left_column.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        ttk.Label(left_column, text="Nome do Motorista:", style="App.TLabel").pack(anchor='w')
        self.entry_nome = ttk.Entry(left_column, font=("Segoe UI", 10))
        self.entry_nome.pack(fill='x', pady=(0, 10))

        ttk.Label(left_column, text="CPF:", style="App.TLabel").pack(anchor='w')
        self.entry_cpf = ttk.Entry(left_column, font=("Segoe UI", 10))
        self.entry_cpf.pack(fill='x', pady=(0, 10))

        ttk.Label(left_column, text="CNH:", style="App.TLabel").pack(anchor='w')
        self.entry_cnh = ttk.Entry(left_column, font=("Segoe UI", 10))
        self.entry_cnh.pack(fill='x', pady=(0, 10))

        ttk.Label(left_column, text="Telefone:", style="App.TLabel").pack(anchor='w')
        self.entry_fone = ttk.Entry(left_column, font=("Segoe UI", 10))
        self.entry_fone.pack(fill='x')

        # --- Coluna da Direita (Placas) ---
        right_column = ttk.Frame(top_frame, style="App.TFrame")
        right_column.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))

        ttk.Label(right_column, text="Placa Cavalo:", style="App.TLabel").pack(anchor='w')
        self.entry_placa1 = ttk.Entry(right_column, font=("Segoe UI", 10))
        self.entry_placa1.pack(fill='x', pady=(0, 10))

        ttk.Label(right_column, text="Placa Carreta 1:", style="App.TLabel").pack(anchor='w')
        self.entry_placa2 = ttk.Entry(right_column, font=("Segoe UI", 10))
        self.entry_placa2.pack(fill='x', pady=(0, 10))

        ttk.Label(right_column, text="Placa Carreta 2:", style="App.TLabel").pack(anchor='w')
        self.entry_placa3 = ttk.Entry(right_column, font=("Segoe UI", 10))
        self.entry_placa3.pack(fill='x')

        # Frame para os botões de importação
        import_buttons_frame = ttk.Frame(main_content_frame, style="App.TFrame")
        import_buttons_frame.pack(fill=tk.X, pady=(0, 15))
        import_buttons_frame.columnconfigure((0, 1), weight=1)

        btn_cnh = ttk.Button(import_buttons_frame, text="📄 Importar Dados da CNH", command=self.selecionar_e_preencher_cnh, style="Outline.TButton")
        btn_cnh.grid(row=0, column=0, sticky='ew', padx=(0, 5), ipady=5)

        btn_crlv = ttk.Button(import_buttons_frame, text="🚗 Importar Dados do CRLV", command=self.selecionar_e_preencher_crlv, style="Outline.TButton")
        btn_crlv.grid(row=0, column=1, sticky='ew', padx=(5, 0), ipady=5)

        # Frame para os botões de ação principal
        action_buttons_frame = ttk.Frame(main_content_frame, style="App.TFrame")
        action_buttons_frame.pack(fill=tk.X, pady=(0, 15))
        action_buttons_frame.columnconfigure((0, 1), weight=1)

        self.btn_oc = ttk.Button(action_buttons_frame, text="✔️ Gerar Ordem de Coleta (O.C.)", command=self.gerar_oc, style="Accent.TButton")
        self.btn_oc.grid(row=0, column=0, sticky='ew', padx=(0, 5), ipady=8)

        self.btn_email_oc = ttk.Button(action_buttons_frame, text="✉️ Enviar O.C. por E-mail", command=self.enviar_email_com_anexos, style="Accent.TButton")
        self.btn_email_oc.grid(row=0, column=1, sticky='ew', padx=(5, 0), ipady=8)

        # Botão de limpeza
        btn_limpar = ttk.Button(main_content_frame, text="🗑️ Limpar Todos os Campos", command=self.limpar_dados_oc, style="Outline.TButton")
        btn_limpar.pack(fill=tk.X, ipady=5)

    def selecionar_pdfs(self):
        files = filedialog.askopenfilenames(title="Selecione os Contratos em PDF", filetypes=[("Arquivos PDF", "*.pdf")])
        if not files: return
        self.produtos.clear(); [self.tree.delete(i) for i in self.tree.get_children()]
        for file in files:
            for p in parse_pdf_fields(file, self.lista_cidades, self.root):
                self.produtos.append(p)
                self.tree.insert("", tk.END, values=("☐", p['produto'], p['toneladas'], p['embalagem'], p.get('contrato',''), p.get('cliente',''), p.get('cidade','')))

    def toggle_check(self, event):
        # A condição de clique na coluna #1 está CORRETA
        if self.tree.identify("region", event.x, event.y) == "cell" and self.tree.identify_column(event.x) == "#1":
            row_id = self.tree.identify_row(event.y)
            if not row_id: # Adiciona uma verificação para evitar erro se clicar fora de uma linha
                return

            # --- CORREÇÃO AQUI ---
            # Use o ID da coluna: "select"
            current = self.tree.set(row_id, "select")
            self.tree.set(row_id, "select", "☑" if current == "☐" else "☐")

    def editar_toneladas(self, event):
        if not self.tree.selection(): return
        item = self.tree.selection()[0]; val = self.tree.item(item, "values")[2]
        win = tk.Toplevel(self.root); win.title("Editar Toneladas"); win.geometry("250x120")
        tk.Label(win, text="Digite a nova quantidade:", font=("Arial", 12)).pack(pady=10)
        var = tk.StringVar(value=val); entry = tk.Entry(win, textvariable=var, font=("Arial", 12)); entry.pack(); entry.focus(); entry.icursor(tk.END)
        def salvar():
            try: self.tree.set(item, column="toneladas", value=float(var.get().replace(",", "."))); win.destroy()
            except ValueError: messagebox.showerror("Erro", "Por favor, insira um número válido.")
        tk.Button(win, text="Salvar", command=salvar, bg="#04BFAD", fg="#012623").pack(pady=5)
        win.transient(self.root); win.grab_set()

    def _get_produtos_marcados(self):
        return [{
            "produto": i[1], 
            "toneladas": str(i[2]), 
            "embalagem": i[3],
            "contrato": str(i[4]), 
            "cliente": i[5], 
            "cidade": i[6]
        } for row_id in self.tree.get_children()
        # CORREÇÃO AQUI: Mudamos de "Selecionar" para "select"
        if self.tree.set(row_id, "select") == "☑" and (i := self.tree.item(row_id)["values"])]

    def inserir_produtos(self):
        produtos_a_inserir = self._get_produtos_marcados()
        if not produtos_a_inserir: 
            messagebox.showwarning("Aviso", "Nenhum produto selecionado.")
            return

        # --- CORREÇÃO DATA ---
        data = self.data_carregamento_var.get()
        # ---------------------

        try: 
            append_rows_to_excel(EXCEL_FILE, produtos_a_inserir, data)
            messagebox.showinfo("Sucesso", f"{len(produtos_a_inserir)} produtos inseridos!")
        except Exception as e: 
            messagebox.showerror("Erro ao Salvar", f"Ocorreu um erro: {e}\nVerifique se a planilha não está aberta.")
        produtos_a_inserir = self._get_produtos_marcados()
        if not produtos_a_inserir: messagebox.showwarning("Aviso", "Nenhum produto selecionado."); return
        data = f"{self.dia_var.get():02d}/{self.mes_var.get():02d}/{self.ano}"
        try: append_rows_to_excel(EXCEL_FILE, produtos_a_inserir, data); messagebox.showinfo("Sucesso", f"{len(produtos_a_inserir)} produtos inseridos!")
        except Exception as e: messagebox.showerror("Erro ao Salvar", f"Ocorreu um erro: {e}\nVerifique se a planilha não está aberta.")

    def gerar_oc(self):
        produtos_sel = self._get_produtos_marcados()
        if not produtos_sel: 
            messagebox.showwarning("Aviso", "Nenhum produto foi selecionado na aba 'Contrato'!")
            return

        nome_motorista = self.entry_nome.get()
        if not nome_motorista: 
            messagebox.showwarning("Aviso", "O nome do condutor é obrigatório.")
            return

        # --- CORREÇÃO 1: LÓGICA DO FORNECEDOR (STRING vs INT) ---
        # O valor da variável é "Fertimaxi" ou "Heringer", não 1 ou 2.
        escolha_fornecedor = self.supplier_var.get()

        if escolha_fornecedor == "Fertimaxi": # Antes era == 1
            template_path = TEMPLATE_OC
            prefixo_arquivo = "OC_"
        elif escolha_fornecedor == "Heringer": # Antes era == 2
            template_path = TEMPLATE_OC_HERINGER
            prefixo_arquivo = "OC_Heringer_"
        else: # Caso padrão/Erro
            template_path = TEMPLATE_OC
            prefixo_arquivo = "OC_"
        # --- FIM DA CORREÇÃO 1 ---

        nome_motorista_sanitized = re.sub(r'[\\/*?:"<>|]', '', nome_motorista)
        default_oc_filename = f"{prefixo_arquivo}{nome_motorista_sanitized}.docx"

        save_path_oc_docx = filedialog.asksaveasfilename(
            defaultextension=".docx", filetypes=[("Word Document", "*.docx")],
            title="Salvar Ordem de Coleta Como...", initialfile=default_oc_filename
        )
        if not save_path_oc_docx: return

        base_name, _ = os.path.splitext(save_path_oc_docx)
        save_path_oc_pdf = base_name + ".pdf"

        placa1 = self.entry_placa1.get()

        # --- CORREÇÃO 2: LEITURA DA DATA ---
        # Usa a variável correta do novo widget de data
        data_carregamento = self.data_carregamento_var.get() 
        # --- FIM DA CORREÇÃO 2 ---

        try:
            gerar_oc_docx(
                template_path,
                save_path_oc_docx, produtos_sel, self.entry_cpf.get(), nome_motorista,
                self.entry_cnh.get(), self.entry_fone.get(), placa1,
                self.entry_placa2.get(), self.entry_placa3.get(), data_carregamento
            )

            try:
                os.system('taskkill /F /IM WINWORD.EXE 2>nul')
                convert(save_path_oc_docx, save_path_oc_pdf)
            except Exception as e:
                messagebox.showerror("Erro de Conversão", f"Falha ao converter para PDF: {e}")
                return

            # Lógica para criar planilha apenas se for Fertimaxi
            if escolha_fornecedor == "Fertimaxi":
                excel_filename = f"Autorização de carregamento {nome_motorista_sanitized}.xlsx"
                excel_save_path = os.path.join(os.path.dirname(save_path_oc_docx), excel_filename)
                criar_planilha_especifica_motorista(
                    excel_save_path, produtos_sel, data_carregamento, nome_motorista, placa1
                )
                self.ultima_planilha_gerada = excel_save_path
            else:
                self.ultima_planilha_gerada = None

            open_file(save_path_oc_pdf)
            self.ultimo_pdf_gerado = save_path_oc_pdf
            messagebox.showinfo("Sucesso", f"Arquivos gerados com sucesso!")

            # Tenta adicionar o agendamento automaticamente
            self.adicionar_agendamento_na_planilha()

        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Erro", f"Ocorreu um erro inesperado: {e}")

    def setup_carta_frete_frame(self, parent_frame):
        # Frame principal para o conteúdo da página
        content_frame = ttk.Frame(parent_frame, style="App.TFrame")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Frame para as entradas de dados
        entries_frame = ttk.Frame(content_frame, style="App.TFrame")
        entries_frame.pack(fill=tk.X, pady=(0, 20))
        entries_frame.columnconfigure((0, 1), weight=1)

        # Campo Valor do Frete
        ttk.Label(entries_frame, text="Valor do Frete (R$):", style="App.TLabel").grid(row=0, column=0, sticky='w')
        self.entry_cf_valor = ttk.Entry(entries_frame, font=("Segoe UI", 10))
        self.entry_cf_valor.grid(row=1, column=0, sticky='ew', padx=(0, 10), pady=(0, 10))

        # Campo Número da Autorização
        ttk.Label(entries_frame, text="Número da Autorização:", style="App.TLabel").grid(row=0, column=1, sticky='w', padx=(10, 0))
        self.entry_cf_autorizacao = ttk.Entry(entries_frame, font=("Segoe UI", 10))
        self.entry_cf_autorizacao.grid(row=1, column=1, sticky='ew', padx=(10, 0), pady=(0, 10))

        # Campo E-mails (Destinatários)
        ttk.Label(entries_frame, text="E-mails (separados por vírgula):", style="App.TLabel").grid(row=2, column=0, columnspan=2, sticky='w')
        self.entry_cf_emails = ttk.Entry(entries_frame, font=("Segoe UI", 10))
        self.entry_cf_emails.insert(0, "financeiro@atlanticofertlog.com.br, ")
        self.entry_cf_emails.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(0, 10))

        # Frame para os botões de ação
        buttons_frame = ttk.Frame(content_frame, style="App.TFrame")
        buttons_frame.pack(fill=tk.X)
        buttons_frame.columnconfigure((0, 1), weight=1)

        # Botão Gerar Carta Frete
        self.btn_cf = ttk.Button(buttons_frame, text="📄 Gerar Carta Frete", command=self.gerar_carta_frete, style="Accent.TButton")
        self.btn_cf.grid(row=0, column=0, sticky='ew', padx=(0, 5), ipady=8)

        # Botão Enviar Carta Frete
        btn_enviar_cf = ttk.Button(buttons_frame, text="✉️ Enviar por E-mail", command=self.enviar_email_carta_frete, style="Accent.TButton")
        btn_enviar_cf.grid(row=0, column=1, sticky='ew', padx=(5, 0), ipady=8)

    def gerar_carta_frete(self):
        nome_motorista = self.entry_nome.get()
        if not nome_motorista:
            messagebox.showwarning("Aviso", "O nome do condutor (na página Ordem de Coleta) é obrigatório.")
            return

        # Pega a data do novo campo de texto unificado
        data_carregamento = self.data_carregamento_var.get()
        if not data_carregamento:
            messagebox.showwarning("Aviso", "A Data de Carregamento (na página Contrato) é obrigatória.")
            return

        dados_para_preencher = {
            "DATA": data_carregamento,
            "CONDUTOR": nome_motorista,
            "CPF": self.entry_cpf.get(),
            "PLACA_CAVALO": self.entry_placa1.get(),
            "VALOR_FRETE": self.entry_cf_valor.get(),
            "AUTORIZACAO_NUM": self.entry_cf_autorizacao.get()
        }

        nome_sanitizado = re.sub(r'[\\/*?:"<>|]', '', nome_motorista)
        default_filename = f"Autorizacao Abastecimento_{nome_sanitizado}.docx"
        save_path_docx = filedialog.asksaveasfilename(
            defaultextension=".docx", filetypes=[("Word Document", "*.docx")],
            title="Salvar Autorização de Abastecimento Como...", initialfile=default_filename
        )
        if not save_path_docx:
            return

        caminho_pdf = os.path.splitext(save_path_docx)[0] + ".pdf"
        try:
            doc = Document(TEMPLATE_CF)
            fill_carta_frete_docx(doc, dados_para_preencher)
            doc.save(save_path_docx)
            try:
                # Garante que o Word feche antes de tentar converter
                os.system('taskkill /F /IM WINWORD.EXE 2>nul')
                time.sleep(1) # Pequena pausa para garantir o fechamento
                convert(save_path_docx, caminho_pdf)
            except Exception as e:
                messagebox.showerror("Erro de Conversão", f"Falha ao converter para PDF: {e}")
                return

            self.ultimo_carta_frete_gerada = caminho_pdf
            open_file(caminho_pdf)
            messagebox.showinfo("Sucesso", "PDF da Carta Frete gerado com sucesso!")
        except FileNotFoundError:
            messagebox.showerror("Erro de Arquivo", f"Modelo da Carta Frete não encontrado: {TEMPLATE_CF}")
        except Exception as e:
            messagebox.showerror("Erro", f"Ocorreu um erro inesperado: {traceback.format_exc()}")

    def enviar_email_carta_frete(self):
        if not self.ultimo_carta_frete_gerada: messagebox.showwarning("Aviso", "Você precisa primeiro gerar a Carta Frete."); return
        destinatarios = ["sonbonamo@gmail.com", "davidfranca9@gmail.com"]
        self.ultimos_destinatarios_cf = destinatarios
        nome_motorista = self.entry_nome.get() or "Motorista"
        placa_cavalo = self.entry_placa1.get() or "N/A"
        assunto = f"AUTORIZACAO CARTA FRETE - {nome_motorista} - {placa_cavalo}"
        corpo = """
        <html><head><style>body { font-family: Calibri, Arial, sans-serif; font-size: 11pt; }</style></head>
        <body><p>Olá,<br>Tudo bem?</p><p>Segue anexo autorização de Carta Frete para abastecimento.</p>
        <p style="color:red;">Obs: Apenas documentos encaminhados previamente via este e-mail terão validade.</p>
        <p>Favor acusar recebimento</p><br><p>Atenciosamente,<br><b>Setor - Expedição</b><br>
        ATLANTICO FERTLOG SERVICOS & TRANSPORTES</p></body></html>"""
        anexos = [self.ultimo_carta_frete_gerada]
        _enviar_email(destinatarios, assunto, corpo, anexos)

    def enviar_correcao_carta_frete(self):
        if not self.ultimo_carta_frete_gerada: messagebox.showwarning("Aviso", "Gere a Carta Frete original primeiro."); return
        try:
            caminho_pdf_final = self.ultimo_carta_frete_gerada
            caminho_docx_temp = os.path.splitext(caminho_pdf_final)[0] + ".docx"
            nome_motorista = self.entry_nome.get()
            dados_para_preencher = {
                "DATA": f"{self.dia_var.get():02d}/{self.mes_var.get():02d}/{self.ano}", "CONDUTOR": nome_motorista,
                "CPF": self.entry_cpf.get(), "PLACA_CAVALO": self.entry_placa1.get(),
                "VALOR_FRETE": self.entry_cf_valor.get(), "AUTORIZACAO_NUM": self.entry_cf_autorizacao.get()
            }
            doc = Document(TEMPLATE_CF)
            fill_carta_frete_docx(doc, dados_para_preencher)
            doc.save(caminho_docx_temp)
            convert(caminho_docx_temp, caminho_pdf_final)
        except Exception as e:
            messagebox.showerror("Erro ao Gerar Correção", f"Não foi possível gerar o PDF corrigido:\n\n{e}"); return
        destinatarios = self.ultimos_destinatarios_cf or ["sonbonamo@gmail.com", "davidfranca9@gmail.com"]
        placa_cavalo = self.entry_placa1.get() or "N/A"
        assunto = f"AUTORIZACAO CARTA FRETE - {nome_motorista} - {placa_cavalo}"
        corpo = """
        <html><head><style>body { font-family: Calibri, Arial, sans-serif; font-size: 11pt; }</style></head>
        <body><p>Segue correção de carta frete</p><p><b style="color:red;">Favor acusar recebimento do e-mail</b></p><br>
        <p>Atenciosamente,<br><b>Setor - Expedição</b><br>ATLANTICO FERTLOG SERVICOS & TRANSPORTES</p></body></html>"""
        anexos = [caminho_pdf_final]
        _enviar_email(destinatarios, assunto, corpo, anexos)
        self.atualizar_planilha_google_sheets(dados_para_preencher)

