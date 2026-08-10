from ..shared import *
from ..servicos.bsoft_api import *
from ..servicos.bsoft_api import _get_timestamp
from ..servicos.comunicacao import *
from ..servicos.documentos import *
from ..servicos.ocr import *
from ..servicos.relatorios import *
from ..servicos.startup import *

class BsoftMixin:
    def setup_bsoft_frame(self, parent_frame):
        """[VERSÃO CORRIGIDA] UI da Bsoft adaptada para o novo layout, com correção de expansão."""

        # --- Estrutura de Rolagem ---
        self.bsoft_main_canvas = tk.Canvas(parent_frame, bg=BG_COLOR, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(parent_frame, orient="vertical", command=self.bsoft_main_canvas.yview, style="App.Vertical.TScrollbar")

        scrollable_frame = ttk.Frame(self.bsoft_main_canvas, style="App.TFrame")
        scrollable_frame.bind("<Configure>", lambda e: self.bsoft_main_canvas.configure(scrollregion=self.bsoft_main_canvas.bbox("all")))

        canvas_window = self.bsoft_main_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        self.bsoft_main_canvas.bind("<Configure>", lambda e: self.bsoft_main_canvas.itemconfig(canvas_window, width=e.width))

        self.bsoft_main_canvas.configure(yscrollcommand=scrollbar.set)

        self.bsoft_main_canvas.pack(side="left", fill="both", expand=True) 
        scrollbar.pack(side="right", fill="y")

        # --- Conteúdo Principal (dentro do frame rolável) ---
        inner_content_frame = ttk.Frame(scrollable_frame, style="App.TFrame")
        inner_content_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # Configura as colunas para se expandirem e preencher o espaço
        inner_content_frame.columnconfigure(0, weight=1)
        inner_content_frame.columnconfigure(1, weight=1)

        # --- Botões de Ação Superiores ---
        top_actions_frame = ttk.Frame(inner_content_frame, style="App.TFrame")
        top_actions_frame.grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky="w")
        btn_import_oc = ttk.Button(top_actions_frame, text="📄 Importar da O.C.", command=self._handle_importar_oc, style="Outline.TButton")
        btn_import_oc.pack(side=tk.LEFT, padx=(0, 10))
        btn_import_docs = ttk.Button(top_actions_frame, text="📥 Importar Documentos", command=self._importar_e_preencher_documentos, style="Outline.TButton")
        btn_import_docs.pack(side=tk.LEFT, padx=(0, 10))
        btn_limpar = ttk.Button(top_actions_frame, text="❌ Limpar Campos", command=self._limpar_campos_bsoft, style="Outline.TButton")
        btn_limpar.pack(side=tk.LEFT)

        # --- Seção de Dados do Motorista ---
        motorista_labelframe = ttk.LabelFrame(inner_content_frame, text=" Dados Pessoais e CNH do Motorista ")
        motorista_labelframe.grid(row=1, column=0, columnspan=2, pady=10, sticky="ew")
        motorista_labelframe.columnconfigure(1, weight=1); motorista_labelframe.columnconfigure(3, weight=1)

        def add_bsoft_row(parent, label_text, row, col, widget_type='entry', default_value=None):
            ttk.Label(parent, text=label_text, style="App.TLabel").grid(row=row, column=col*2, sticky='w', padx=10, pady=(8, 2))
            if widget_type == 'entry':
                widget = ttk.Entry(parent, font=("Segoe UI", 10))
                if default_value:
                    widget.insert(0, default_value)
            elif widget_type == 'combo':
                widget = ttk.Combobox(parent, font=("Segoe UI", 10), state="readonly")
                if default_value:
                    widget.set(default_value)
            widget.grid(row=row, column=col*2 + 1, sticky='ew', padx=10)
            return widget

        self.bsoft_entry_nome = add_bsoft_row(motorista_labelframe, "Nome Completo:", 0, 0)
        self.bsoft_entry_cpf = add_bsoft_row(motorista_labelframe, "CPF:", 1, 0)
        self.bsoft_entry_fone = add_bsoft_row(motorista_labelframe, "Celular:", 2, 0)
        self.bsoft_entry_dt_nascimento = add_bsoft_row(motorista_labelframe, "Data de Nascimento:", 3, 0)
        self.bsoft_entry_cnh_rntrc = add_bsoft_row(motorista_labelframe, "RNTRC do Motorista:", 4, 0)
        self.bsoft_entry_cnh_registro = add_bsoft_row(motorista_labelframe, "Nº Registro CNH:", 0, 1)
        self.bsoft_entry_seguro_cnh = add_bsoft_row(motorista_labelframe, "Seguro CNH:", 1, 1)
        self.bsoft_entry_cnh_categoria = add_bsoft_row(motorista_labelframe, "Categoria:", 2, 1)
        self.bsoft_entry_cnh_espelho = add_bsoft_row(motorista_labelframe, "Nº do Espelho:", 3, 1)
        self.bsoft_entry_cnh_validade = add_bsoft_row(motorista_labelframe, "Validade CNH:", 4, 1)
        self.bsoft_entry_cnh_emissao = add_bsoft_row(motorista_labelframe, "Data de Emissão:", 5, 1)
        self.bsoft_entry_cnh_primeira_hab = add_bsoft_row(motorista_labelframe, "1ª Habilitação:", 6, 1)

        # --- Seção de Endereço ---
        endereco_labelframe = ttk.LabelFrame(inner_content_frame, text=" Endereço do Motorista ")
        endereco_labelframe.grid(row=2, column=0, columnspan=2, pady=10, sticky="ew")
        endereco_labelframe.columnconfigure(1, weight=1); endereco_labelframe.columnconfigure(3, weight=1)
        self.bsoft_end_cep = add_bsoft_row(endereco_labelframe, "CEP:", 0, 0)
        self.bsoft_end_cep.bind("<FocusOut>", self._handle_cep_lookup)
        # ... (Restante das definições de widgets de endereço, veículo, proprietário, etc. continua aqui)
        self.bsoft_end_logradouro = add_bsoft_row(endereco_labelframe, "Logradouro (Rua):", 1, 0)
        self.bsoft_end_numero = add_bsoft_row(endereco_labelframe, "Número:", 2, 0)
        self.bsoft_end_bairro = add_bsoft_row(endereco_labelframe, "Bairro:", 3, 0)
        self.bsoft_end_estado = add_bsoft_row(endereco_labelframe, "Estado:", 4, 0, 'combo')
        self.bsoft_end_estado['values'] = sorted(list(self.cidades_por_uf.keys()))
        self.bsoft_end_estado.bind('<<ComboboxSelected>>', lambda event, s='end': self._atualizar_cidades_combobox(event, s))
        self.bsoft_end_cidade = add_bsoft_row(endereco_labelframe, "Cidade:", 5, 0, 'combo')
        self.bsoft_end_complemento = add_bsoft_row(endereco_labelframe, "Complemento:", 6, 0)
        self.bsoft_end_inscricaoEstadual = add_bsoft_row(endereco_labelframe, "Inscrição Estadual:", 0, 1, default_value="ISENTO")
        self.bsoft_end_inscricaoMunicipal = add_bsoft_row(endereco_labelframe, "Inscrição Municipal:", 1, 1, default_value="ISENTO")
        self.bsoft_end_tipoEndereco = add_bsoft_row(endereco_labelframe, "Tipo Endereço:", 2, 1, 'combo', default_value="Nacional")
        self.bsoft_end_tipoEndereco['values'] = ["Nacional", "Estrangeiro"]
        self.bsoft_end_enderecoPreferencial = add_bsoft_row(endereco_labelframe, "Endereço Preferencial:", 3, 1, 'combo', default_value="Sim")
        self.bsoft_end_enderecoPreferencial['values'] = ["Sim", "Não"]
        self.bsoft_end_cobrancaPreferencial = add_bsoft_row(endereco_labelframe, "Cobrança Preferencial:", 4, 1, 'combo', default_value="Não")
        self.bsoft_end_cobrancaPreferencial['values'] = ["Sim", "Não"]
        self.bsoft_end_inscricaoEstadualNaoContribuinte = add_bsoft_row(endereco_labelframe, "IE Não Contribuinte:", 5, 1, 'combo', default_value="Sim")
        self.bsoft_end_inscricaoEstadualNaoContribuinte['values'] = ["Sim", "Não"]

        def _criar_secao_veiculo(parent, titulo, sufixo_variavel):
            labelframe = ttk.LabelFrame(parent, text=titulo)
            labelframe.columnconfigure(1, weight=1); labelframe.columnconfigure(3, weight=1)
            placa_var = tk.StringVar()
            placa_var.trace_add("write", lambda name, index, mode, var=placa_var: self._formatar_placa(var, name, mode))
            ttk.Label(labelframe, text="Placa:", style="App.TLabel").grid(row=0, column=0, sticky='w', padx=10, pady=(8, 2))
            placa_entry = ttk.Entry(labelframe, font=("Segoe UI", 10), textvariable=placa_var)
            placa_entry.grid(row=0, column=1, sticky='ew', padx=10)
            widgets = {'placa_var': placa_var}
            widgets['renavam'] = add_bsoft_row(labelframe, "RENAVAM:", 1, 0)
            widgets['eixos'] = add_bsoft_row(labelframe, "Qtd. de Eixos:", 2, 0)
            widgets['estado'] = add_bsoft_row(labelframe, "Estado:", 3, 0, 'combo')
            widgets['estado']['values'] = sorted(list(self.cidades_por_uf.keys()))
            widgets['estado'].bind('<<ComboboxSelected>>', lambda event, s=sufixo_variavel: self._atualizar_cidades_combobox(event, s))
            widgets['cidade'] = add_bsoft_row(labelframe, "Cidade:", 4, 0, 'combo')
            widgets['marca'] = add_bsoft_row(labelframe, "Marca:", 0, 1, 'combo')
            widgets['marca']['values'] = []
            widgets['modelo'] = add_bsoft_row(labelframe, "Modelo:", 1, 1)
            categoria_combo = add_bsoft_row(labelframe, "Categoria do Veículo:", 2, 1, 'combo')
            categoria_combo['values'] = sorted(list(BSOFT_CATEGORY_TO_SIMPLE_BRANDS_MAP.keys()))
            categoria_combo.bind('<<ComboboxSelected>>', lambda event, s=sufixo_variavel: self._atualizar_campos_dependentes(event, s))
            categoria_combo.bind('<<ComboboxSelected>>', lambda event, s=sufixo_variavel: self._atualizar_tipo_rodado_automatico(event, s), add='+')
            categoria_combo.bind('<<ComboboxSelected>>', lambda event, s=sufixo_variavel: self._on_category_selected(event, s), add='+')
            widgets['categoria_veiculo'] = categoria_combo
            widgets['tipo_rodado'] = add_bsoft_row(labelframe, "Tipo Rodado:", 3, 1, 'combo')
            widgets['tipo_rodado']['values'] = list(BSOFT_TIPOS_RODADO_NOMES.values())
            widgets['tipo_carroceria'] = add_bsoft_row(labelframe, "Tipo Carroceria:", 4, 1, 'combo')
            widgets['tipo_carroceria']['values'] = list(BSOFT_TIPOS_CARROCERIA_NOMES.values())
            widgets['tipo_equipamento'] = add_bsoft_row(labelframe, "Tipo de Equipamento:", 5, 1, 'combo')
            widgets['tipo_equipamento']['values'] = sorted(list(BSOFT_TIPOS_EQUIPAMENTO.keys()))
            for nome, widget in widgets.items():
                setattr(self, f"bsoft_entry_{nome}_{sufixo_variavel}", widget)
            return labelframe

        cavalo_labelframe = _criar_secao_veiculo(inner_content_frame, " Dados do Cavalo Mecânico (Placa 1) ", "cavalo")
        cavalo_labelframe.grid(row=3, column=0, columnspan=2, pady=10, sticky="ew")

        self.add_reboque1_var = tk.BooleanVar(value=False)
        check_reboque1 = ttk.Checkbutton(inner_content_frame, text="Adicionar Reboque 1 (Placa 2)", variable=self.add_reboque1_var, command=self._toggle_reboque1_fields)
        check_reboque1.grid(row=4, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        self.reboque1_labelframe = _criar_secao_veiculo(inner_content_frame, " Dados do Reboque 1 (Placa 2) ", "reboque1")
        self.reboque1_labelframe.grid(row=5, column=0, columnspan=2, pady=10, sticky="ew")

        self.add_reboque2_var = tk.BooleanVar(value=False)
        check_reboque2 = ttk.Checkbutton(self.reboque1_labelframe, text="Adicionar Reboque 2 (Placa 3)", variable=self.add_reboque2_var, command=self._toggle_reboque2_fields)
        check_reboque2.grid(row=6, column=0, columnspan=4, padx=10, pady=10, sticky="w")

        self.reboque2_labelframe = _criar_secao_veiculo(inner_content_frame, " Dados do Reboque 2 (Placa 3) ", "reboque2")
        self.reboque2_labelframe.grid(row=6, column=0, columnspan=2, pady=10, sticky="ew")

        self.reboque1_labelframe.grid_remove()
        self.reboque2_labelframe.grid_remove()

        check_frame = ttk.Frame(inner_content_frame, style="App.TFrame")
        check_frame.grid(row=7, column=0, columnspan=2, padx=10, pady=(15, 5), sticky="w")

        self.bsoft_motorista_eh_proprietario_var = tk.BooleanVar(value=True)
        check_prop = ttk.Checkbutton(check_frame, text="Motorista é o proprietário do(s) veículo(s)", variable=self.bsoft_motorista_eh_proprietario_var, command=self._toggle_proprietario_fields)
        check_prop.pack(anchor='w')

        self.proprietario_labelframe = ttk.LabelFrame(inner_content_frame, text=" Dados do Proprietário (se for diferente do motorista) ")
        self.proprietario_labelframe.grid(row=8, column=0, columnspan=2, pady=10, sticky="ew")
        self.proprietario_labelframe.columnconfigure(1, weight=1)
        self.bsoft_entry_prop_cnpj = add_bsoft_row(self.proprietario_labelframe, "CPF / CNPJ do Proprietário:", 0, 0)
        self.bsoft_entry_prop_razao_social = add_bsoft_row(self.proprietario_labelframe, "Razão Social / Nome:", 1, 0)
        self.bsoft_entry_prop_rntrc = add_bsoft_row(self.proprietario_labelframe, "RNTRC do Proprietário:", 2, 0)
        self.bsoft_combo_prop_tipo = add_bsoft_row(self.proprietario_labelframe, "Tipo Transportadora (PJ):", 3, 0, 'combo')
        self.bsoft_combo_prop_tipo['values'] = ["ETC", "CTC", "Equiparado"]

        self.btn_buscar_cnpj = ttk.Button(self.proprietario_labelframe, text="Buscar por CNPJ", command=self._handle_cnpj_lookup, style="Outline.TButton")
        self.btn_buscar_cnpj.grid(row=0, column=2, padx=10, pady=5, sticky='w')

        final_action_frame = ttk.Frame(inner_content_frame, style="App.TFrame")
        final_action_frame.grid(row=9, column=0, columnspan=2, sticky="ew", padx=10, pady=20)

        self.btn_cadastrar_tudo = ttk.Button(final_action_frame, text="🚀 Cadastrar Tudo na Bsoft", command=self._handle_cadastrar_tudo, style="Accent.TButton")
        self.btn_cadastrar_tudo.pack(fill='x', ipady=8)

        self._toggle_proprietario_fields()

        self.bsoft_main_canvas.bind("<MouseWheel>", lambda event, c=self.bsoft_main_canvas: self._on_mousewheel(event, c))
        self._bind_mousewheel_recursive(scrollable_frame, self.bsoft_main_canvas)

    def _on_category_selected(self, event, sufixo_veiculo):
        """
        [VERSÃO 2.0] Filtra o combobox de Marcas com base na Categoria selecionada, usando nomes simples.
        """
        try:
            categoria_combo = getattr(self, f'bsoft_entry_categoria_veiculo_{sufixo_veiculo}')
            marca_combo = getattr(self, f'bsoft_entry_marca_{sufixo_veiculo}')

            categoria_selecionada = categoria_combo.get()

            # Agora busca no novo mapa de nomes simples
            marcas_validas = BSOFT_CATEGORY_TO_SIMPLE_BRANDS_MAP.get(categoria_selecionada, [])

            marca_combo['values'] = sorted(marcas_validas)
            marca_combo.set('')

        except Exception as e:
            print(f"Erro ao filtrar marcas dinamicamente: {e}")

    def _puxar_dados_para_bsoft(self):
        """Copia os dados da aba O.C. para a aba Bsoft."""
        self._limpar_campos_bsoft()
        self.bsoft_entry_nome.insert(0, self.entry_nome.get())
        self.bsoft_entry_cpf.insert(0, self.entry_cpf.get())
        self.bsoft_entry_cnh.insert(0, self.entry_cnh.get())
        self.bsoft_entry_fone.insert(0, self.entry_fone.get())
        messagebox.showinfo("Sucesso", "Dados puxados da aba 'Ordem de Coleta'!")

    def _limpar_campos_bsoft(self):
        """[VERSÃO COM ENDEREÇO] Limpa todos os campos da interface Bsoft, incluindo endereço."""
        # Limpa campos de motorista
        self.bsoft_entry_nome.delete(0, tk.END)
        self.bsoft_entry_cpf.delete(0, tk.END)
        self.bsoft_entry_fone.delete(0, tk.END)
        self.bsoft_entry_dt_nascimento.delete(0, tk.END)
        self.bsoft_entry_cnh_rntrc.delete(0, tk.END)
        self.bsoft_entry_cnh_registro.delete(0, tk.END)
        self.bsoft_entry_seguro_cnh.delete(0, tk.END)
        self.bsoft_entry_cnh_categoria.delete(0, tk.END)
        self.bsoft_entry_cnh_espelho.delete(0, tk.END)
        self.bsoft_entry_cnh_validade.delete(0, tk.END)
        self.bsoft_entry_cnh_emissao.delete(0, tk.END)
        self.bsoft_entry_cnh_primeira_hab.delete(0, tk.END)

        # Limpa campos de endereço
        self.bsoft_end_cep.delete(0, tk.END)
        self.bsoft_end_logradouro.delete(0, tk.END)
        self.bsoft_end_numero.delete(0, tk.END)
        self.bsoft_end_bairro.delete(0, tk.END)
        self.bsoft_end_estado.set('')
        self.bsoft_end_cidade.set('')
        self.bsoft_end_cidade['values'] = []
        self.bsoft_end_complemento.delete(0, tk.END)
        self.bsoft_end_inscricaoEstadual.delete(0, tk.END); self.bsoft_end_inscricaoEstadual.insert(0, "ISENTO")
        self.bsoft_end_inscricaoMunicipal.delete(0, tk.END); self.bsoft_end_inscricaoMunicipal.insert(0, "ISENTO")
        self.bsoft_end_tipoEndereco.set("Nacional")
        self.bsoft_end_enderecoPreferencial.set("Sim")
        self.bsoft_end_cobrancaPreferencial.set("Não")
        self.bsoft_end_inscricaoEstadualNaoContribuinte.set("Sim")

        # Limpa campos de veículo
        for sufixo in ['cavalo', 'reboque1', 'reboque2']:
            getattr(self, f'bsoft_entry_placa_var_{sufixo}').set("")
            getattr(self, f'bsoft_entry_renavam_{sufixo}').delete(0, tk.END)
            getattr(self, f'bsoft_entry_eixos_{sufixo}').delete(0, tk.END)
            getattr(self, f'bsoft_entry_modelo_{sufixo}').delete(0, tk.END)
            getattr(self, f'bsoft_entry_marca_{sufixo}').set('')
            getattr(self, f'bsoft_entry_categoria_veiculo_{sufixo}').set('')
            getattr(self, f'bsoft_entry_tipo_rodado_{sufixo}').set('')
            getattr(self, f'bsoft_entry_tipo_carroceria_{sufixo}').set('')
            getattr(self, f'bsoft_entry_estado_{sufixo}').set('')
            getattr(self, f'bsoft_entry_cidade_{sufixo}').set('')
            getattr(self, f'bsoft_entry_cidade_{sufixo}')['values'] = []

        # Limpa campos do proprietário (PJ)
        self.bsoft_entry_prop_cnpj.delete(0, tk.END)
        self.bsoft_entry_prop_razao_social.delete(0, tk.END)
        self.bsoft_entry_prop_rntrc.delete(0, tk.END)
        self.bsoft_combo_prop_tipo.set('')

        self.add_reboque1_var.set(False); self.add_reboque2_var.set(False)
        self._toggle_reboque1_fields()
        self.bsoft_motorista_eh_proprietario_var.set(True)
        self._toggle_proprietario_fields()
        self.dados_proprietario_pj_completo = None

    def _handle_cadastrar_bsoft(self):
        """Recolhe os dados da aba Bsoft, formata e chama a função de cadastro da API."""
        dt_nasc_br = self.bsoft_entry_dt_nascimento.get()
        dt_nasc_api = ""
        if dt_nasc_br:
            try:
                dt_obj = datetime.strptime(dt_nasc_br, '%d/%m/%Y')
                dt_nasc_api = dt_obj.strftime('%Y-%m-%d')
            except ValueError:
                messagebox.showwarning("Data Inválida", "O formato da Data de Nascimento deve ser DD/MM/AAAA.")
                return

        dados = {
            "nome": self.bsoft_entry_nome.get(),
            "cpf": re.sub(r'\D', '', self.bsoft_entry_cpf.get()),
            "cnh": self.bsoft_entry_cnh_registro.get(),
            "fone": re.sub(r'\D', '', self.bsoft_entry_fone.get()),
            "dtNascimento": dt_nasc_api,
            "is_owner": self.bsoft_is_owner_var.get()
        }

        if not all([dados['nome'], dados['cpf']]):
            messagebox.showwarning("Dados Incompletos", "Por favor, preencha pelo menos o Nome e o CPF do motorista.")
            return

        threading.Thread(target=cadastrar_pessoa_fisica_bsoft, args=(dados,), daemon=True).start()

    def _handle_importar_oc(self):
        """Abre uma O.C. em .docx ou .pdf, lê os dados do motorista e TODAS as placas."""
        caminho_oc = filedialog.askopenfilename(
            title="Selecione o arquivo da Ordem de Coleta (.docx ou .pdf)",
            filetypes=[("Documentos de O.C.", "*.docx *.pdf"), ("Todos os arquivos", "*.*")]
        )
        if not caminho_oc:
            return

        try:
            texto_completo_oc = ""
            extensao = os.path.splitext(caminho_oc)[1].lower()

            if extensao == '.docx':
                doc = Document(caminho_oc)
                texto_completo_oc = "\n".join([p.text for p in doc.paragraphs])
            elif extensao == '.pdf':
                with pdfplumber.open(caminho_oc) as pdf:
                    texto_das_paginas = [page.extract_text() for page in pdf.pages]
                    texto_completo_oc = "\n".join(filter(None, texto_das_paginas))
            else:
                messagebox.showerror("Tipo de Arquivo Inválido", f"O formato '{extensao}' não é suportado.")
                return

            dados_encontrados = {}
            texto_upper = texto_completo_oc.upper()

            if 'MOTORISTA:' in texto_upper:
                match_motorista = re.search(r'MOTORISTA:\s*([\d.-]+)\s*–\s*([A-Z\s]+)', texto_upper)
                if match_motorista:
                    dados_encontrados['cpf'] = match_motorista.group(1).strip()
                    dados_encontrados['nome'] = match_motorista.group(2).strip()
            if 'CNH:' in texto_upper:
                match_cnh = re.search(r'CNH:\s*(\d+)', texto_upper)
                if match_cnh: dados_encontrados['cnh'] = match_cnh.group(1).strip()
            if 'FONE:' in texto_upper:
                match_fone = re.search(r'FONE:\s*([\d\s()-]+)', texto_upper)
                if match_fone: dados_encontrados['fone'] = match_fone.group(1).strip()

            match_placa1 = re.search(r'1ª\s*PLACA:\s*([A-Z0-9-]+)', texto_upper)
            if match_placa1: dados_encontrados['placa_cavalo'] = match_placa1.group(1).strip()

            match_placa2 = re.search(r'2ª\s*PLACA:\s*([A-Z0-9-]+)', texto_upper)
            if match_placa2: dados_encontrados['placa_carreta1'] = match_placa2.group(1).strip()

            match_placa3 = re.search(r'3ª\s*PLACA:\s*([A-Z0-9-]+)', texto_upper)
            if match_placa3: dados_encontrados['placa_carreta2'] = match_placa3.group(1).strip()

            self._limpar_campos_bsoft()
            self.bsoft_entry_nome.insert(0, dados_encontrados.get("nome", ""))
            self.bsoft_entry_cpf.insert(0, dados_encontrados.get("cpf", ""))
            self.bsoft_entry_cnh_registro.insert(0, dados_encontrados.get("cnh", ""))
            self.bsoft_entry_fone.insert(0, dados_encontrados.get("fone", ""))
            self.bsoft_entry_placa_cavalo.insert(0, dados_encontrados.get("placa_cavalo", ""))
            self.bsoft_entry_placa_carreta1.insert(0, dados_encontrados.get("placa_carreta1", ""))
            self.bsoft_entry_placa_carreta2.insert(0, dados_encontrados.get("placa_carreta2", ""))

            messagebox.showinfo("Sucesso", "Dados importados com sucesso da Ordem de Coleta!")

        except Exception as e:
            messagebox.showerror("Erro de Leitura", f"Não foi possível ler o arquivo da O.C.\n\nDetalhe: {e}")

    def _importar_e_preencher_documentos(self):
        """Função principal para importar, classificar e preencher múltiplos documentos."""
        caminhos = filedialog.askopenfilenames(
            title="Selecione os Documentos (CNH, CRLV, RNTRC)",
            filetypes=[("Documentos", "*.pdf *.jpg *.jpeg *.png *.bmp"), ("Todos os arquivos", "*.*")]
        )
        if not caminhos:
            return

        self.btn_cadastrar_tudo.config(state="disabled", text="Processando Docs...")
        # Usar uma thread para não travar a interface
        threading.Thread(target=self._worker_processar_documentos, args=(caminhos,), daemon=True).start()

    def _worker_processar_documentos(self, caminhos):
        """Worker em thread para processar os documentos em background."""
        dados_finais = {}
        lista_dados_crlv = []

        for caminho in caminhos:
            texto_ocr = self._obter_texto_do_arquivo_com_azure(caminho)
            if not texto_ocr:
                continue

            tipo_doc = self._classificar_documento_pelo_texto(texto_ocr)
            print(f"Arquivo '{os.path.basename(caminho)}' classificado como: {tipo_doc}")

            if tipo_doc == 'CNH':
                dados_finais.update(extrair_dados_cnh_com_azure_api(texto_ocr))
            elif tipo_doc == 'CRLV':
                lista_dados_crlv.append(extrair_dados_crlv_com_azure_api(texto_ocr))
            elif tipo_doc == 'RNTRC':
                dados_finais.update(extrair_dados_rntrc_com_azure_api(texto_ocr))

        # Envia a tarefa de preenchimento para a thread principal da UI
        self.ui_queue.put((self._popular_form_bsoft, (dados_finais, lista_dados_crlv)))

    def _popular_form_bsoft(self, dados_motorista, lista_crlv):
        """[VERSÃO CORRIGIDA 2] Preenche o formulário da Bsoft com todos os dados, incluindo Qtd. de Eixos."""

        self._limpar_campos_bsoft()

        # Preenche dados do motorista (CNH e RNTRC)
        self.bsoft_entry_nome.insert(0, dados_motorista.get("nome", ""))
        self.bsoft_entry_cpf.insert(0, dados_motorista.get("cpf", ""))
        self.bsoft_entry_dt_nascimento.insert(0, dados_motorista.get("dtNascimento", ""))
        self.bsoft_entry_cnh_rntrc.insert(0, dados_motorista.get("rntrc", ""))
        self.bsoft_entry_cnh_registro.insert(0, dados_motorista.get("numero", ""))
        self.bsoft_entry_seguro_cnh.insert(0, dados_motorista.get("seguro", ""))
        self.bsoft_entry_cnh_categoria.insert(0, dados_motorista.get("categoria", ""))
        self.bsoft_entry_cnh_espelho.insert(0, dados_motorista.get("protocolo", ""))
        self.bsoft_entry_cnh_validade.insert(0, dados_motorista.get("dtValidade", ""))
        self.bsoft_entry_cnh_emissao.insert(0, dados_motorista.get("dtExpedicao", ""))
        self.bsoft_entry_cnh_primeira_hab.insert(0, dados_motorista.get("dtPrimeiraExpedicao", ""))

        # Preenche dados dos veículos (CRLV)
        sufixos = ['cavalo', 'reboque1', 'reboque2']
        for i, dados_veiculo in enumerate(lista_crlv):
            if i >= len(sufixos):
                break

            sufixo = sufixos[i]

            if sufixo == 'reboque1':
                self.add_reboque1_var.set(True)
                self._toggle_reboque1_fields()
            elif sufixo == 'reboque2':
                self.add_reboque2_var.set(True)
                self._toggle_reboque2_fields()

            # Preenche os campos do veículo
            getattr(self, f'bsoft_entry_placa_var_{sufixo}').set(dados_veiculo.get("placa", ""))
            getattr(self, f'bsoft_entry_renavam_{sufixo}').insert(0, dados_veiculo.get("renavam", ""))
            getattr(self, f'bsoft_entry_marca_{sufixo}').set(dados_veiculo.get("marca", ""))
            getattr(self, f'bsoft_entry_modelo_{sufixo}').insert(0, dados_veiculo.get("modelo", ""))

            # NOVO: Preenche Qtd de Eixos
            eixos_entry = getattr(self, f'bsoft_entry_eixos_{sufixo}')
            eixos_entry.delete(0, tk.END)
            eixos_entry.insert(0, dados_veiculo.get("eixos", ""))

            # Preenche Categoria e dispara a atualização dos campos dependentes
            categoria_combo = getattr(self, f'bsoft_entry_categoria_veiculo_{sufixo}')
            categoria_combo.set(dados_veiculo.get("categoria_veiculo", ""))
            self._atualizar_campos_dependentes(None, sufixo)
            self._atualizar_tipo_rodado_automatico(None, sufixo)

            # Preenche Tipo de Carroceria
            carroceria_combo = getattr(self, f'bsoft_entry_tipo_carroceria_{sufixo}')
            carroceria_combo.set(dados_veiculo.get("tipo_carroceria", ""))

            # Preenche Estado e Cidade
            estado_valor = dados_veiculo.get("estado", "")
            if estado_valor:
                estado_combo = getattr(self, f'bsoft_entry_estado_{sufixo}')
                estado_combo.set(estado_valor)
                self._atualizar_cidades_combobox(None, sufixo)

                cidade_combo = getattr(self, f'bsoft_entry_cidade_{sufixo}')
                cidade_combo.set(dados_veiculo.get("cidade", ""))

        self.btn_cadastrar_tudo.config(state="normal", text="🚀 Cadastrar Tudo na Bsoft")
        messagebox.showinfo("Sucesso", "Documentos processados e campos preenchidos!")

    def _toggle_proprietario_fields(self):
        """Mostra ou oculta a seção de dados do proprietário com base no checkbox."""
        if self.bsoft_motorista_eh_proprietario_var.get():
            self.proprietario_labelframe.grid_remove()
        else:
            self.proprietario_labelframe.grid()

    def _buscar_pessoa_por_cpf(self, cpf):
        cpf_limpo = re.sub(r'\D', '', cpf)
        if not cpf_limpo:
            print(f"{_get_timestamp()} [BUSCA PF] CPF recebido para busca estava vazio ou inválido.")
            return None

        endpoint_url = f"https://atlanticofertlog.bsoft.app/services/index.php/pessoas/v1/pessoas/fisicas/{cpf_limpo}"
        auth = (BSOFT_API_USER, BSOFT_API_PASSWORD)

        print(f"\n{_get_timestamp()} [BUSCA PF] --- INICIANDO BUSCA DE PESSOA POR CPF ---")
        print(f"{_get_timestamp()} [BUSCA PF] Buscando com CPF limpo: '{cpf_limpo}'")
        print(f"{_get_timestamp()} [BUSCA PF] URL da busca: {endpoint_url}")

        try:
            response = requests.get(endpoint_url, auth=auth, timeout=20)

            print(f"{_get_timestamp()} [BUSCA PF] Status da resposta da busca: {response.status_code}")
            print(f"{_get_timestamp()} [BUSCA PF] Conteúdo da resposta da busca: {response.text}")

            if response.status_code == 200 and response.text and response.json():
                print(f"{_get_timestamp()} [BUSCA PF] Motorista encontrado na Bsoft.")
                print(f"{_get_timestamp()} [BUSCA PF] --- FIM DA BUSCA ---\n")
                return response.json()[0].get("id")
            else:
                print(f"{_get_timestamp()} [BUSCA PF] Motorista não encontrado (status não foi 200 ou resposta foi vazia).")
                print(f"{_get_timestamp()} [BUSCA PF] --- FIM DA BUSCA ---\n")
                return None
        except Exception as e:
            print(f"{_get_timestamp()} [BUSCA PF] ERRO INESPERADO: {e}")
            print(f"{_get_timestamp()} [BUSCA PF] --- FIM DA BUSCA ---\n")
            return None

    def _buscar_pessoa_juridica_por_cnpj(self, cnpj):
        """Busca uma pessoa jurídica na Bsoft pelo CNPJ e retorna seu ID."""
        cnpj_limpo = re.sub(r'\D', '', cnpj)
        if not cnpj_limpo or len(cnpj_limpo) != 14:
            return None

        endpoint_url = f"https://atlanticofertlog.bsoft.app/services/index.php/pessoas/v1/pessoas/juridicas/{cnpj_limpo}"
        auth = (BSOFT_API_USER, BSOFT_API_PASSWORD)

        try:
            response = requests.get(endpoint_url, auth=auth, timeout=20)
            if response.status_code == 200 and response.json():
                return response.json()[0].get("id")
            else:
                return None
        except requests.exceptions.RequestException:
            return None

    def _handle_cadastrar_tudo(self):
        """Função INICIADORA que dispara o processo de cadastro em uma nova thread."""
        self.btn_cadastrar_tudo.config(state="disabled", text="Cadastrando...")
        threading.Thread(target=self._worker_cadastrar_tudo, daemon=True).start()

    def _toggle_reboque1_fields(self):
        """Mostra ou oculta a seção de dados do Reboque 1."""
        if self.add_reboque1_var.get():
            self.reboque1_labelframe.grid()
        else:
            self.reboque1_labelframe.grid_remove()
            self.add_reboque2_var.set(False)
            self._toggle_reboque2_fields()

    def _toggle_reboque2_fields(self):
        """Mostra ou oculta a seção de dados do Reboque 2."""
        if self.add_reboque2_var.get():
            self.reboque2_labelframe.grid()
        else:
            self.reboque2_labelframe.grid_remove()

    def _formatar_placa(self, var, name, mode):
        """[VERSÃO FINAL - HÍFEN OBRIGATÓRIO] Adiciona o hífen automaticamente para TODAS as placas de 7 caracteres."""

        # Previne chamadas recursivas que podem acontecer com o .set()
        if hasattr(self, '_formatting_placa') and self._formatting_placa:
            return
        self._formatting_placa = True

        value = var.get()

        # 1. Sanitiza a entrada: remove hifens e deixa em maiúsculo
        cleaned_value = value.replace('-', '').upper()

        # Limita o tamanho para 7 caracteres
        if len(cleaned_value) > 7:
            cleaned_value = cleaned_value[:7]

        new_value = cleaned_value

        # 2. Se a placa limpa tiver 7 caracteres, adiciona o hífen após o terceiro caractere
        if len(cleaned_value) == 7:
            new_value = f"{cleaned_value[:3]}-{cleaned_value[3:]}"

        # 3. Atualiza o campo na tela apenas se houver alguma mudança
        if new_value != value:
            var.set(new_value)

        self._formatting_placa = False

    def _atualizar_cidades_combobox(self, event, sufixo):
        """
        [VERSÃO CORRIGIDA] Preenche o combobox de cidades com base no estado.
        Agora trata o sufixo 'end' para o endereço do motorista corretamente.
        """
        # --- INÍCIO DA LÓGICA DE CORREÇÃO ---
        if sufixo == 'end':
            # Se for o endereço do motorista, usa os nomes de atributo específicos.
            estado_combo = self.bsoft_end_estado
            cidades_combobox = self.bsoft_end_cidade
        else:
            # Se for um veículo, constrói o nome do atributo dinamicamente (comportamento original).
            estado_combo = getattr(self, f'bsoft_entry_estado_{sufixo}')
            cidades_combobox = getattr(self, f'bsoft_entry_cidade_{sufixo}')
        # --- FIM DA LÓGICA DE CORREÇÃO ---

        estado_selecionado = estado_combo.get()

        if estado_selecionado in self.cidades_por_uf:
            # Pega apenas os nomes das cidades para exibir no combobox
            lista_nomes_cidades = [cidade[0] for cidade in self.cidades_por_uf[estado_selecionado]]
            cidades_combobox['values'] = sorted(lista_nomes_cidades)
            cidades_combobox.set('') # Limpa a seleção anterior
        else:
            cidades_combobox['values'] = []
            cidades_combobox.set('')

    def _atualizar_campos_dependentes(self, event, sufixo_veiculo):
        """Preenche automaticamente o campo Tipo de Equipamento com base na Categoria."""
        try:
            categoria_combo = getattr(self, f'bsoft_entry_categoria_veiculo_{sufixo_veiculo}')
            equipamento_combo = getattr(self, f'bsoft_entry_tipo_equipamento_{sufixo_veiculo}')

            categoria_selecionada = categoria_combo.get()
            categoria_id = BSOFT_CATEGORIAS_VEICULO.get(categoria_selecionada)

            if categoria_id is None:
                return

            # --- Atualiza Tipo de Equipamento ---
            equipamento_id = BSOFT_CATEGORY_TO_EQUIPMENT_MAP.get(categoria_id)
            equipamento_desc = ""
            if equipamento_id:
                equipamento_desc = next((desc for desc, eid in BSOFT_TIPOS_EQUIPAMENTO.items() if eid == equipamento_id), "")
            equipamento_combo.set(equipamento_desc)

        except Exception as e:
            print(f"Erro ao atualizar campos dependentes: {e}")

    def _worker_cadastrar_tudo(self):
           """
           [VERSÃO FINAL COM POLLING ATIVO E LOGS]
           Cria a pessoa, verifica ativamente se ela já está disponível na API, 
           e só então adiciona o endereço e prossegue com o fluxo.
           """
           try:
               self.ui_queue.put((lambda: self.btn_cadastrar_tudo.config(text="1/5: Preparando dados..."), ()))

               def formatar_data_para_api(data_str):
                   if not data_str or data_str in ["Não encontrada", "Formato inválido"]: return None
                   try: return datetime.strptime(data_str, '%d/%m/%Y').strftime('%Y-%m-%d')
                   except ValueError: return None

               # --- Etapa 1: Coletar dados do Motorista ---
               dados_motorista_completos = {
                   "nome": self.bsoft_entry_nome.get().strip(), "cpf": re.sub(r'\D', '', self.bsoft_entry_cpf.get()),
                   "fone": re.sub(r'\D', '', self.bsoft_entry_fone.get()), "is_owner": self.bsoft_motorista_eh_proprietario_var.get(),
                   "rntrc": self.bsoft_entry_cnh_rntrc.get().strip(), "dtNascimento": formatar_data_para_api(self.bsoft_entry_dt_nascimento.get().strip()),
                   "cnh": {
                       "numero": self.bsoft_entry_cnh_registro.get().strip(), "seguro": self.bsoft_entry_seguro_cnh.get().strip(),
                       "categoria": self.bsoft_entry_cnh_categoria.get().strip(), "protocolo": self.bsoft_entry_cnh_espelho.get().strip(),
                       "dtValidade": formatar_data_para_api(self.bsoft_entry_cnh_validade.get().strip()),
                       "dtExpedicao": formatar_data_para_api(self.bsoft_entry_cnh_emissao.get().strip()),
                       "dtPrimeiraExpedicao": formatar_data_para_api(self.bsoft_entry_cnh_primeira_hab.get().strip())
                   }
               }
               if not dados_motorista_completos["cpf"] or not dados_motorista_completos["nome"]:
                   raise ValueError("O Nome e o CPF do Motorista são obrigatórios.")

               # --- Etapa 2: Validar e Salvar Motorista ---
               self.ui_queue.put((lambda: self.btn_cadastrar_tudo.config(text="2/5: Validando motorista..."), ()))
               motorista_cpf_limpo = dados_motorista_completos.get("cpf")
               motorista_id_existente = self._buscar_pessoa_por_cpf(motorista_cpf_limpo)

               resposta_motorista = atualizar_pessoa_fisica_bsoft(motorista_cpf_limpo, dados_motorista_completos) if motorista_id_existente else cadastrar_pessoa_fisica_bsoft(dados_motorista_completos)

               if not resposta_motorista or not resposta_motorista.get('codPessoa'):
                   raise Exception("Falha ao criar ou atualizar o motorista na Bsoft.")
               motorista_id_final = resposta_motorista.get('codPessoa')

               # --- Etapa 3: Salvar Endereço do Motorista (com verificação) ---
               self.ui_queue.put((lambda: self.btn_cadastrar_tudo.config(text="3/5: Aguardando API..."), ()))

               # Se for um motorista novo, verifica ativamente se ele já está disponível antes de prosseguir
               if not motorista_id_existente:
                   print(f"{_get_timestamp()} [WORKER] Verificando disponibilidade do novo motorista na API...")
                   tentativas = 0
                   max_tentativas = 10 # Tenta por até 20 segundos
                   while tentativas < max_tentativas:
                       time.sleep(2) # Espera 2 segundos entre cada tentativa
                       if self._buscar_pessoa_por_cpf(motorista_cpf_limpo):
                           print(f"{_get_timestamp()} [WORKER] Motorista ID {motorista_id_final} encontrado na API após { (tentativas + 1) * 2 } segundos.")
                           break
                       tentativas += 1
                       print(f"{_get_timestamp()} [WORKER] Tentativa {tentativas}/{max_tentativas}... Motorista ainda não encontrado.")
                   if tentativas == max_tentativas:
                       raise Exception(f"API da Bsoft não disponibilizou o motorista ID {motorista_id_final} após {max_tentativas * 2} segundos.")

               # Coleta os dados de endereço e faz a chamada
               endereco_estado_motorista = self.bsoft_end_estado.get()
               endereco_cidade_motorista = self.bsoft_end_cidade.get()
               cidade_motorista_normalizada = normalizar_texto_sem_acento(endereco_cidade_motorista)
               cod_ibge_motorista = next((ibge for cidade, ibge in self.cidades_por_uf.get(endereco_estado_motorista, []) if normalizar_texto_sem_acento(cidade) == cidade_motorista_normalizada), None)
               cep_original_motorista = self.bsoft_end_cep.get()
               cep_limpo_motorista = re.sub(r'\D', '', cep_original_motorista)
               cep_formatado_motorista = f"{cep_limpo_motorista[:5]}-{cep_limpo_motorista[5:]}" if len(cep_limpo_motorista) == 8 else cep_limpo_motorista
               dados_endereco_motorista = {
                   "tipoEndereco": "N", "cep": cep_formatado_motorista, "bairro": self.bsoft_end_bairro.get(), 
                   "cidade": endereco_cidade_motorista, "estado": endereco_estado_motorista, "numero": self.bsoft_end_numero.get(),
                   "complemento": self.bsoft_end_complemento.get(), "logradouro": self.bsoft_end_logradouro.get(),
                   "cobrancaPreferencial": "S", "enderecoPreferencial": "S", "codIBGE": cod_ibge_motorista,
                   "inscricaoMunicipal": "ISENTO", "inscricaoEstadual": "ISENTO", "inscricaoEstadualNaoContribuinte": "S"
               }
               cadastrar_endereco_bsoft(motorista_id_final, dados_endereco_motorista)

               # --- Etapa 4: Validar e Salvar Proprietário (se necessário) ---
               self.ui_queue.put((lambda: self.btn_cadastrar_tudo.config(text="4/5: Validando proprietário..."), ()))
               proprietario_id_final = motorista_id_final

               if not self.bsoft_motorista_eh_proprietario_var.get():
                   TIPO_TRANSPORTADORA_PJ_MAP = {"ETC": "E", "CTC": "C", "Equiparado": "EQ"}
                   cpf_cnpj_prop = self.bsoft_entry_prop_cnpj.get().strip()
                   id_prop_limpo = re.sub(r'\D', '', cpf_cnpj_prop)
                   if len(id_prop_limpo) != 14: raise ValueError(f"O CNPJ '{cpf_cnpj_prop}' do proprietário é inválido.")

                   dados_empresa = { "cnpj": id_prop_limpo, "razao_social": self.bsoft_entry_prop_razao_social.get().strip(), "tipoTransportadora": TIPO_TRANSPORTADORA_PJ_MAP.get(self.bsoft_combo_prop_tipo.get()), "rntrc": self.bsoft_entry_prop_rntrc.get().strip() }
                   if not all(dados_empresa.values()): raise ValueError("Todos os campos do Proprietário PJ são obrigatórios.")

                   proprietario_encontrado_id = self._buscar_pessoa_juridica_por_cnpj(id_prop_limpo)
                   resposta_pj = atualizar_pessoa_juridica_bsoft(id_prop_limpo, dados_empresa) if proprietario_encontrado_id else cadastrar_pessoa_juridica_bsoft(dados_empresa)

                   if not resposta_pj or not resposta_pj.get('codPessoa'): raise Exception("Falha ao salvar o proprietário (PJ) na Bsoft.")
                   proprietario_id_final = resposta_pj.get('codPessoa')

                   if self.dados_proprietario_pj_completo and self.dados_proprietario_pj_completo.get('cnpj') == id_prop_limpo:
                       dados_api = self.dados_proprietario_pj_completo
                       if dados_api.get('inscricoes_estaduais'):
                           for ie in dados_api['inscricoes_estaduais']:
                               if ie.get('ativo'): dados_empresa['inscricao_estadual'] = ie.get('inscricao_estadual'); break

                       estado_pj, cidade_pj_nome = dados_api.get('uf', ''), dados_api.get('municipio', '')
                       cidade_pj_normalizada = normalizar_texto_sem_acento(cidade_pj_nome)
                       cod_ibge_pj = next((ibge for cidade, ibge in self.cidades_por_uf.get(estado_pj, []) if normalizar_texto_sem_acento(cidade) == cidade_pj_normalizada), None)
                       cep_pj_original = dados_api.get('cep', ''); cep_pj_limpo = re.sub(r'\D', '', cep_pj_original)
                       cep_pj_formatado = f"{cep_pj_limpo[:5]}-{cep_pj_limpo[5:]}" if len(cep_pj_limpo) == 8 else cep_pj_limpo
                       dados_endereco_pj = {
                           "tipoEndereco": "N", "cep": cep_pj_formatado, "bairro": dados_api.get('bairro', ''),
                           "cidade": cidade_pj_nome, "estado": estado_pj, "numero": dados_api.get('numero', ''),
                           "complemento": dados_api.get('complemento', ''), "logradouro": dados_api.get('logradouro', ''),
                           "codIBGE": cod_ibge_pj,
                           "inscricaoMunicipal": "ISENTO",
                           "inscricaoEstadual": dados_empresa.get('inscricao_estadual', "ISENTO"),
                           "inscricaoEstadualNaoContribuinte": "S",
                           "enderecoPreferencial": "S",
                           "cobrancaPreferencial": "S"
                       }
                       print(f"{_get_timestamp()} [WORKER] Pausa de 5 segundos para garantir a replicação do PJ na API...")
                       time.sleep(5)
                       cadastrar_endereco_bsoft(proprietario_id_final, dados_endereco_pj)

               # --- Etapa 5: Cadastrar Veículos ---
               self.ui_queue.put((lambda: self.btn_cadastrar_tudo.config(text="5/5: Cadastrando veículos..."), ()))
               rntrc_final = dados_motorista_completos.get("rntrc") if self.bsoft_motorista_eh_proprietario_var.get() else self.bsoft_entry_prop_rntrc.get().strip()
               veiculos_a_cadastrar = []
               for sufixo in ['cavalo', 'reboque1', 'reboque2']:
                   if sufixo.startswith('reboque') and not getattr(self, f'add_{sufixo}_var').get(): continue
                   placa_valor = getattr(self, f'bsoft_entry_placa_var_{sufixo}').get().strip()
                   if not placa_valor: continue

                   estado_veiculo = getattr(self, f'bsoft_entry_estado_{sufixo}').get()
                   cidade_veiculo_nome = getattr(self, f'bsoft_entry_cidade_{sufixo}').get()
                   if not estado_veiculo or not cidade_veiculo_nome: raise ValueError(f"O Estado e a Cidade são obrigatórios para o veículo de placa {placa_valor}.")

                   cidade_veiculo_normalizada = normalizar_texto_sem_acento(cidade_veiculo_nome)
                   cidade_veiculo_ibge = next((ibge for cidade, ibge in self.cidades_por_uf.get(estado_veiculo, []) if normalizar_texto_sem_acento(cidade) == cidade_veiculo_normalizada), None)
                   if not cidade_veiculo_ibge: raise ValueError(f"Não foi possível encontrar o código IBGE para {cidade_veiculo_nome} - {estado_veiculo}.")

                   categoria_selecionada = getattr(self, f'bsoft_entry_categoria_veiculo_{sufixo}').get()
                   categoria_id = BSOFT_CATEGORIAS_VEICULO.get(categoria_selecionada)

    # --- NOVA LÓGICA PARA BUSCAR O ID DA MARCA ---
                   marca_selecionada_nome = getattr(self, f'bsoft_entry_marca_{sufixo}').get()
                   categoria_selecionada_nome = getattr(self, f'bsoft_entry_categoria_veiculo_{sufixo}').get()

                         # Cria a chave de busca combinada (ex: ('SCANIA', 'BITRUCK'))
                   chave_busca = (marca_selecionada_nome, categoria_selecionada_nome)

                         # Procura o ID no novo dicionário de busca
                   marca_id_final = BSOFT_MARCA_ID_LOOKUP.get(chave_busca)

                   if not marca_id_final:
                       raise ValueError(f"Não foi possível encontrar um Código de Marca para a combinação: {marca_selecionada_nome} e {categoria_selecionada_nome}")
                         # --- FIM DA NOVA LÓGICA ---

                   dados_veiculo_dict = { 
                       "placa": placa_valor, "renavam": getattr(self, f'bsoft_entry_renavam_{sufixo}').get().strip(), 
                       "rntrc": rntrc_final, "tara": "9000", "capacidadeCarga": "32000", "capM3": "32", 
                       "modeloVeiculo": getattr(self, f'bsoft_entry_modelo_{sufixo}').get().strip(), 
                       "quantidadeEixos": getattr(self, f'bsoft_entry_eixos_{sufixo}').get().strip(), 
                       "marcaVeiculo": marca_id_final,
                       "categoriaVeiculo": categoria_id, "grupoVeiculo": 2, 
                       "tipoRodado": get_key_from_value(BSOFT_TIPOS_RODADO_NOMES, getattr(self, f'bsoft_entry_tipo_rodado_{sufixo}').get()), 
                       "tipoCarroceria": get_key_from_value(BSOFT_TIPOS_CARROCERIA_NOMES, getattr(self, f'bsoft_entry_tipo_carroceria_{sufixo}').get()), 
                       "tipoEquipamento": BSOFT_TIPOS_EQUIPAMENTO.get(getattr(self, f'bsoft_entry_tipo_equipamento_{sufixo}').get()), 
                       "motoristaEhProprietario": self.bsoft_motorista_eh_proprietario_var.get(), 
                       "estado": estado_veiculo, "cidade": cidade_veiculo_ibge, 
                       "proprietario_id": proprietario_id_final, 
                       "motorista_documento": motorista_cpf_limpo,
                       "motoristaId": motorista_id_final,  # Motorista ID
                       "arrendatarioId": proprietario_id_final  # Proprietário ID (dono do veículo/arrendatário)
                   }
                   veiculos_a_cadastrar.append(dados_veiculo_dict)

               if not veiculos_a_cadastrar:
                   if messagebox.askyesno("Nenhum Veículo", f"O cadastro de '{dados_motorista_completos['nome']}' foi salvo com sucesso, mas nenhum veículo foi adicionado. Deseja continuar mesmo assim?"):
                       pass
                   else:
                       raise Exception("Processo cancelado pelo usuário por falta de veículo.")

               sucessos = 0
               for dados_veiculo in veiculos_a_cadastrar:
                   resultado = cadastrar_veiculo_bsoft(dados_veiculo)
                   if resultado: sucessos += 1
                   time.sleep(1)

               msg_final = f"Processo concluído com sucesso!\n{sucessos} veículo(s) salvos para '{dados_motorista_completos['nome']}'."
               self.ui_queue.put((messagebox.showinfo, ("Sucesso", msg_final)))

           except ValueError as ve:
               self.ui_queue.put((messagebox.showwarning, ("Dados Incompletos", str(ve))))
           except Exception as e:
               traceback.print_exc()
               self.ui_queue.put((messagebox.showerror, ("Erro no Processo", str(e))))
           finally:
               self.ui_queue.put((lambda: self.btn_cadastrar_tudo.config(state="normal", text="🚀 Cadastrar Tudo na Bsoft"), ()))

    def _obter_texto_do_arquivo_com_azure(self, caminho_arquivo):
        """Usa a API da Azure para extrair texto de uma imagem ou PDF."""
        img_bytes = None
        try:
            ext = os.path.splitext(caminho_arquivo)[1].lower()
            if ext == '.pdf':
                with fitz.open(caminho_arquivo) as doc:
                    page = doc.load_page(0)
                    pix = page.get_pixmap(dpi=300)
                    img_bytes = pix.tobytes("png")
            else:
                with open(caminho_arquivo, "rb") as f:
                    img_bytes = f.read()

            client = ImageAnalysisClient(endpoint=AZURE_ENDPOINT, credential=AzureKeyCredential(AZURE_KEY))
            result = client.analyze(image_data=img_bytes, visual_features=[VisualFeatures.READ])

            return "\n".join([ln.text for blk in result.read.blocks for ln in blk.lines]) if result.read else ""
        except Exception as e:
            self.ui_queue.put((messagebox.showerror, ("Erro na API da Azure", f"Falha ao processar o arquivo:\n\n{e}")))
            return None

    def _atualizar_tipo_rodado_automatico(self, event, sufixo_veiculo):
        """Preenche automaticamente o campo Tipo Rodado com base no ID da Categoria."""
        try:
            categoria_combo = getattr(self, f'bsoft_entry_categoria_veiculo_{sufixo_veiculo}')
            rodado_combo = getattr(self, f'bsoft_entry_tipo_rodado_{sufixo_veiculo}')

            # 1. Pega o texto selecionado na tela (ex: "CAVALO")
            categoria_selecionada_texto = categoria_combo.get()
            if not categoria_selecionada_texto:
                return

            # 2. Converte o texto para o ID correspondente (ex: "CAVALO" -> 1)
            categoria_id = BSOFT_CATEGORIAS_VEICULO.get(categoria_selecionada_texto)
            if categoria_id is None:
                return

            # 3. Usa o mapa de IDs para encontrar o ID do rodado (ex: 1 -> '03')
            #    O padrão é '00' (NÃO APLICÁVEL)
            rodado_id_correspondente = BSOFT_CATEGORY_ID_TO_RODADO_ID_MAP.get(categoria_id, '00')

            # 4. Converte o ID do rodado de volta para o texto de exibição (ex: '03' -> "CAVALO MECANICO")
            rodado_texto_correspondente = BSOFT_TIPOS_RODADO_NOMES.get(rodado_id_correspondente, 'NÃO APLICÁVEL')

            # 5. Define o valor na tela
            rodado_combo.set(rodado_texto_correspondente)

        except Exception as e:
            print(f"Erro ao atualizar tipo de rodado automaticamente: {e}")

    def _adicionar_produto_manual(self):
        """Adiciona um produto inserido manualmente à lista e à treeview."""
        try:
            pedido = self.entry_heringer_pedido.get()
            produto = self.entry_heringer_produto.get()
            cliente = self.entry_heringer_cliente.get()
            toneladas_str = self.entry_heringer_ton.get().replace(',', '.')
            embalagem = self.entry_heringer_embalagem.get()
            cidade = self.entry_heringer_cidade.get()

            if not all([pedido, produto, cliente, toneladas_str, embalagem, cidade]):
                messagebox.showwarning("Campos Vazios", "Por favor, preencha todos os campos do produto.")
                return

            toneladas = float(toneladas_str)

            p = {
                "cliente": cliente, "contrato": pedido, "produto": produto, 
                "toneladas": toneladas, "embalagem": embalagem, "cidade": cidade
            }

            self.produtos.append(p)
            self.tree.insert("", tk.END, values=("☑", p['produto'], p['toneladas'], p['embalagem'], p.get('contrato',''), p.get('cliente',''), p.get('cidade','')))

            # Limpa os campos após adicionar
            self.entry_heringer_pedido.delete(0, tk.END)
            self.entry_heringer_produto.delete(0, tk.END)
            self.entry_heringer_cliente.delete(0, tk.END)
            self.entry_heringer_ton.delete(0, tk.END)
            self.entry_heringer_embalagem.delete(0, tk.END)
            self.entry_heringer_cidade.delete(0, tk.END)
            self.entry_heringer_pedido.focus_set()

        except ValueError:
            messagebox.showerror("Erro de Valor", "A quantidade de toneladas deve ser um número válido.")
        except Exception as e:
            messagebox.showerror("Erro", f"Ocorreu um erro inesperado: {e}")

    def _classificar_documento_pelo_texto(self, texto):
        """Identifica o tipo de documento com base em palavras-chave no texto."""
        texto_upper = texto.upper()
        if "CARTEIRA NACIONAL DE HABILITA" in texto_upper:
            return 'CNH'
        if "CERTIFICADO DE REGISTRO E LICENCIAMENTO" in texto_upper:
            return 'CRLV'
        if "RNTRC" in texto_upper or "TRANSPORTADORES RODOVIÁRIOS DE CARGAS" in texto_upper:
            return 'RNTRC'
        return 'DESCONHECIDO'

    def _importar_foto_pedido_heringer(self):
        """Abre uma foto, extrai os dados do pedido Heringer e preenche os campos."""
        caminho = filedialog.askopenfilename(
            title="Selecione a Foto do Pedido Heringer",
            filetypes=[("Imagens", "*.jpg *.jpeg *.png *.bmp"), ("Todos os arquivos", "*.*")]
        )
        if not caminho:
            return

        texto_ocr = self._obter_texto_do_arquivo_com_azure(caminho)
        if not texto_ocr:
            messagebox.showerror("Erro de Leitura", "Não foi possível extrair texto da imagem selecionada.")
            return

        produtos_extraidos = extrair_dados_pedido_heringer(texto_ocr)

        if not produtos_extraidos:
            messagebox.showwarning("Nenhum Produto Encontrado", "Não foi possível identificar produtos no formato esperado na imagem.")
            return

        # Se encontrou múltiplos produtos, adiciona todos à lista de uma vez
        if len(produtos_extraidos) > 1:
            for p in produtos_extraidos:
                self.produtos.append(p)
                self.tree.insert("", tk.END, values=("☑", p.get('produto'), p.get('toneladas'), p.get('embalagem'), p.get('contrato'), p.get('cliente'), p.get('cidade')))
            messagebox.showinfo("Sucesso", f"{len(produtos_extraidos)} produtos foram extraídos e adicionados à lista!")

        # Se encontrou apenas um produto, preenche os campos para conferência
        else:
            produto_unico = produtos_extraidos[0]
            self.entry_heringer_pedido.delete(0, tk.END)
            self.entry_heringer_produto.delete(0, tk.END)
            self.entry_heringer_cliente.delete(0, tk.END)
            self.entry_heringer_ton.delete(0, tk.END)

            self.entry_heringer_pedido.insert(0, produto_unico.get("contrato", ""))
            self.entry_heringer_produto.insert(0, produto_unico.get("produto", ""))
            self.entry_heringer_cliente.insert(0, produto_unico.get("cliente", ""))
            self.entry_heringer_ton.insert(0, str(produto_unico.get("toneladas", "")).replace('.',','))
            messagebox.showinfo("Sucesso", "Dados extraídos! Por favor, confira os campos e preencha o que falta (Embalagem, Cidade) antes de adicionar à lista.")

    def _handle_cep_lookup(self, event=None):
        """
        [INICIADOR] Pega o CEP digitado e inicia a busca em uma thread.
        É acionado quando o usuário sai do campo CEP.
        """
        cep = self.bsoft_end_cep.get()
        cep_limpo = re.sub(r'\D', '', cep)

        if len(cep_limpo) == 8:
            # Mostra um feedback visual para o usuário
            self.bsoft_end_cep.config(state="disabled")
            self.ui_queue.put((lambda: self.bsoft_end_cep.config(state="readonly"), ()))
            # Inicia a busca em background para não travar a UI
            threading.Thread(target=self._worker_buscar_cep, args=(cep_limpo,), daemon=True).start()
        elif len(cep_limpo) > 0:
            messagebox.showwarning("CEP Inválido", "O CEP deve conter 8 dígitos.")

    def _worker_buscar_cep(self, cep):
        """
        [THREAD SECUNDÁRIA] Faz a requisição à API BrasilAPI (VERSÃO ATUALIZADA).
        """
        # A URL foi alterada para o endpoint do BrasilAPI
        url = f"https://brasilapi.com.br/api/cep/v1/{cep}"
        try:
            response = requests.get(url, timeout=10)
            # O raise_for_status() agora vai capturar o erro 404 caso o CEP não exista
            response.raise_for_status()
            dados_cep = response.json()

            # A verificação de erro do ViaCEP não é mais necessária.
            # Se a resposta foi bem-sucedida, envia os dados para a UI.
            self.ui_queue.put((self._preencher_endereco_pelo_cep, (dados_cep,)))

        except requests.exceptions.HTTPError as e:
            # Trata especificamente o erro de CEP não encontrado (404)
            if e.response.status_code == 404:
                msg_args = ("CEP não encontrado", f"O CEP '{cep}' não foi encontrado na base de dados.")
                self.ui_queue.put((messagebox.showinfo, msg_args))
            else:
                msg_args = ("Erro na Requisição", f"A API retornou um erro inesperado.\n\nCódigo: {e.response.status_code}")
                self.ui_queue.put((messagebox.showerror, msg_args))
        except requests.exceptions.RequestException as e:
            msg_args = ("Erro de Rede", f"Não foi possível conectar à BrasilAPI.\n\nErro: {e}")
            self.ui_queue.put((messagebox.showerror, msg_args))
        finally:
            # Reabilita o campo de CEP na UI, independentemente do resultado
            self.ui_queue.put((lambda: self.bsoft_end_cep.config(state="normal"), ()))

    def _preencher_endereco_pelo_cep(self, dados_cep):
        """
        [THREAD PRINCIPAL] Preenche os campos de endereço com os dados da BrasilAPI (VERSÃO ATUALIZADA).
        """
        self.bsoft_end_logradouro.delete(0, tk.END)
        self.bsoft_end_bairro.delete(0, tk.END)
        self.bsoft_end_complemento.delete(0, tk.END) # BrasilAPI não retorna complemento, então limpamos

        # ATENÇÃO: As chaves do JSON foram atualizadas para corresponder à BrasilAPI
        self.bsoft_end_logradouro.insert(0, dados_cep.get('street', ''))
        self.bsoft_end_bairro.insert(0, dados_cep.get('neighborhood', ''))

        estado_uf = dados_cep.get('state', '')
        cidade_nome = dados_cep.get('city', '')

        if estado_uf:
            self.bsoft_end_estado.set(estado_uf)
            self._atualizar_cidades_combobox(None, 'end') 
            if cidade_nome:
                self.bsoft_end_cidade.set(cidade_nome)

        self.bsoft_end_numero.focus_set()

    def _handle_cnpj_lookup(self):
        """
        [INICIADOR] Pega o CNPJ, valida e inicia a busca em uma nova thread.
        """
        cnpj = self.bsoft_entry_prop_cnpj.get()
        cnpj_limpo = re.sub(r'\D', '', cnpj)

        if len(cnpj_limpo) != 14:
            messagebox.showwarning("CNPJ Inválido", "O CNPJ deve conter 14 dígitos.")
            return

        # Desabilita o botão para evitar cliques múltiplos
        self.btn_buscar_cnpj.config(state="disabled", text="Buscando...")

        # Inicia a busca em background
        threading.Thread(target=self._worker_buscar_cnpj, args=(cnpj_limpo,), daemon=True).start()

    def _worker_buscar_cnpj(self, cnpj):
        """
        [THREAD SECUNDÁRIA][VERSÃO 2] Faz a requisição à API e guarda a resposta completa.
        """
        url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            dados_cnpj = response.json()

            # --- LÓGICA ALTERADA ---
            # Guarda a resposta completa para uso posterior no cadastro
            self.dados_proprietario_pj_completo = dados_cnpj

            # Envia apenas os dados necessários para preencher a UI
            self.ui_queue.put((self._preencher_dados_cnpj, (dados_cnpj,)))

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                msg_args = ("CNPJ não encontrado", f"O CNPJ '{cnpj}' não foi encontrado na base de dados.")
                self.ui_queue.put((messagebox.showinfo, msg_args))
            else:
                msg_args = ("Erro na Requisição", f"A API retornou um erro inesperado.\n\nCódigo: {e.response.status_code}")
                self.ui_queue.put((messagebox.showerror, msg_args))
        except requests.exceptions.RequestException as e:
            msg_args = ("Erro de Rede", f"Não foi possível conectar à BrasilAPI para consultar o CNPJ.\n\nErro: {e}")
            self.ui_queue.put((messagebox.showerror, msg_args))
        finally:
            self.ui_queue.put((lambda: self.btn_buscar_cnpj.config(state="normal", text="Buscar por CNPJ"), ()))

    def _preencher_dados_cnpj(self, dados_cnpj):
        """
        [THREAD PRINCIPAL] Preenche o campo de Razão Social com os dados da API.
        """
        razao_social = dados_cnpj.get('razao_social', '')

        self.bsoft_entry_prop_razao_social.delete(0, tk.END)
        self.bsoft_entry_prop_razao_social.insert(0, razao_social)

        # Move o foco para o próximo campo para agilizar a digitação
        self.bsoft_entry_prop_rntrc.focus_set()

