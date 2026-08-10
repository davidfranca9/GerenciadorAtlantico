from ..shared import *
from ..servicos.bsoft_api import *
from ..servicos.comunicacao import *
from ..servicos.documentos import *
from ..servicos.ocr import *
from ..servicos.relatorios import *
from ..servicos.startup import *

class BuonnyMixin:
    def setup_buonny_frame(self, parent_frame):
        """Cria toda a interface da funcionalidade Buonny, incluindo a tela de login
        e a interface principal com abas, dentro do frame pai fornecido."""

        # --- Frame de Login (inicialmente visível) ---
        self.buonny_login_frame = ttk.Frame(parent_frame, style="App.TFrame")
        self.buonny_login_frame.pack(fill='both', expand=True, padx=100, pady=50)

        login_content = ttk.Frame(self.buonny_login_frame, style="App.TFrame")
        login_content.place(relx=0.5, rely=0.5, anchor='center')

        ttk.Label(login_content, text="Login na Buonny", font=("Segoe UI", 18, "bold"), style="App.TLabel").pack(pady=10)

        ttk.Label(login_content, text="Apelido (Código):", style="App.TLabel").pack(anchor='w', pady=(10,0))
        self.buonny_user_entry = ttk.Entry(login_content, font=("Segoe UI", 10))
        self.buonny_user_entry.pack(fill='x', ipady=4)

        ttk.Label(login_content, text="Senha:", style="App.TLabel").pack(anchor='w', pady=(10,0))
        self.buonny_pass_entry = ttk.Entry(login_content, font=("Segoe UI", 10)) # Senha visível
        self.buonny_pass_entry.pack(fill='x', ipady=4)

        ttk.Button(login_content, text="Fazer Login na Buonny", command=self._buonny_attempt_login, style="Accent.TButton").pack(fill='x', pady=20, ipady=8)

        # --- Frame Principal da Buonny (inicialmente oculto) ---
        self.buonny_main_frame = ttk.Frame(parent_frame, style="App.TFrame")
        # .pack() será chamado após o login bem-sucedido

        # Notebook para as sub-abas
        buonny_notebook = ttk.Notebook(self.buonny_main_frame, style="Inner.TNotebook")
        buonny_notebook.pack(expand=True, fill='both', padx=5, pady=5)

        buonny_tab1 = ttk.Frame(buonny_notebook, style="App.TFrame", padding=10)
        buonny_tab2 = ttk.Frame(buonny_notebook, style="App.TFrame", padding=10)

        buonny_notebook.add(buonny_tab1, text=' Consulta Rápida ')
        buonny_notebook.add(buonny_tab2, text=' Cadastro Completo de Ficha ')

        # Log de Eventos específico para a Buonny
        log_frame = ttk.LabelFrame(self.buonny_main_frame, text="Log de Eventos Buonny", style="App.TLabelframe")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        self.buonny_result_text = tk.Text(log_frame, height=8, state="disabled", wrap="word", bg=FRAME_COLOR, fg=TEXT_COLOR, relief="flat", borderwidth=0, highlightthickness=0)
        self.buonny_result_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Chama as funções para construir o conteúdo de cada sub-aba
        self._create_buonny_consulta_tab(buonny_tab1)
        self._create_buonny_cadastro_tab(buonny_tab2)

    def _create_buonny_consulta_tab(self, parent):
        """Cria o conteúdo da sub-aba 'Consulta Rápida'."""
        data_frame = ttk.LabelFrame(parent, text="Dados para Consulta", style="App.TLabelframe")
        data_frame.pack(fill=tk.BOTH, expand=True)

        # Layout em Grid
        ttk.Label(data_frame, text="Produto", style="App.TLabel").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Combobox(data_frame, textvariable=self.c_produto_var, values=["BUONNY CHECK"], state="readonly").grid(row=1, column=0, sticky=tk.EW, padx=5)

        ttk.Label(data_frame, text="Código", style="App.TLabel").grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(data_frame, textvariable=self.c_codigo_var, state="readonly").grid(row=1, column=1, sticky=tk.EW, padx=5)

        ttk.Label(data_frame, text="Razão Social", style="App.TLabel").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(data_frame, textvariable=self.c_razao_social_var, state="readonly").grid(row=1, column=2, columnspan=2, sticky=tk.EW, padx=5)

        ttk.Label(data_frame, text="CPF", style="App.TLabel").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        cpf_entry = ttk.Entry(data_frame, textvariable=self.c_cpf_var)
        cpf_entry.grid(row=5, column=0, sticky=tk.EW, padx=5)
        cpf_entry.bind("<FocusOut>", self._buonny_on_cpf_focus_out)

        ttk.Label(data_frame, text="Nome", style="App.TLabel").grid(row=4, column=1, columnspan=3, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(data_frame, textvariable=self.c_nome_var).grid(row=5, column=1, columnspan=3, sticky=tk.EW, padx=5)

        ttk.Label(data_frame, text="Placa do Veículo", style="App.TLabel").grid(row=6, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(data_frame, textvariable=self.c_placa_veiculo_var).grid(row=7, column=0, sticky=tk.EW, padx=5)

        ttk.Label(data_frame, text="Placa da Carreta", style="App.TLabel").grid(row=6, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(data_frame, textvariable=self.c_placa_carreta_var).grid(row=7, column=1, sticky=tk.EW, padx=5)

        ttk.Label(data_frame, text="Tipo da Carga", style="App.TLabel").grid(row=8, column=0, sticky=tk.W, padx=5, pady=5)
        carga_tipo_combo = ttk.Combobox(data_frame, textvariable=self.c_carga_tipo_var, values=sorted(list(self.carga_tipo_map.keys())), state="readonly")
        carga_tipo_combo.grid(row=9, column=0, columnspan=2, sticky=tk.EW, padx=5)

        ttk.Label(data_frame, text="Valor da Carga", style="App.TLabel").grid(row=8, column=2, sticky=tk.W, padx=5, pady=5)
        carga_valor_combo = ttk.Combobox(data_frame, textvariable=self.c_carga_valor_var, values=list(self.carga_valor_map.keys()), state="readonly")
        carga_valor_combo.grid(row=9, column=2, columnspan=2, sticky=tk.EW, padx=5)

        ttk.Label(data_frame, text="Origem", font=("Segoe UI", 10, "bold")).grid(row=10, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        ttk.Label(data_frame, text="Destino", font=("Segoe UI", 10, "bold")).grid(row=10, column=2, columnspan=2, sticky=tk.W, padx=5, pady=5)

        ttk.Label(data_frame, text="Cidade").grid(row=11, column=0, sticky=tk.W, padx=5, pady=2)
        origem_entry = ttk.Entry(data_frame, textvariable=self.c_origem_cidade_var)
        origem_entry.grid(row=12, column=0, sticky=tk.EW, padx=5)
        origem_entry.bind("<FocusOut>", lambda e: self._buonny_on_city_focus_out(e, 'origem'))

        ttk.Label(data_frame, text="Estado").grid(row=11, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(data_frame, textvariable=self.c_origem_estado_var, width=5).grid(row=12, column=1, sticky=tk.W, padx=5)

        ttk.Label(data_frame, text="Cidade").grid(row=11, column=2, sticky=tk.W, padx=5, pady=2)
        destino_entry = ttk.Entry(data_frame, textvariable=self.c_destino_cidade_var)
        destino_entry.grid(row=12, column=2, sticky=tk.EW, padx=5)
        destino_entry.bind("<FocusOut>", lambda e: self._buonny_on_city_focus_out(e, 'destino'))

        ttk.Label(data_frame, text="Estado").grid(row=11, column=3, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(data_frame, textvariable=self.c_destino_estado_var, width=5).grid(row=12, column=3, sticky=tk.W, padx=5)

        data_frame.columnconfigure(2, weight=1); data_frame.columnconfigure(0, weight=1)

        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Button(button_frame, text="Consultar", command=self.buonny_run_consultation, style="Accent.TButton").pack(side=tk.LEFT, pady=10, ipady=5)
        ttk.Button(button_frame, text="Limpar", command=self.buonny_clear_fields_tab1, style="Outline.TButton").pack(side=tk.LEFT, padx=5, pady=10, ipady=5)

    def _create_buonny_cadastro_tab(self, parent):
        """Cria o conteúdo da sub-aba 'Cadastro Completo' com barra de rolagem."""
        canvas = tk.Canvas(parent, bg=BG_COLOR, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview, style="App.Vertical.TScrollbar")
        scrollable_frame = ttk.Frame(canvas, style="App.TFrame")

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=event.width)

        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        parent.bind("<Configure>", _on_frame_configure)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._bind_mousewheel_recursive(scrollable_frame, canvas)

        current_row = 0
        # --- Seção: Dados do Cliente ---
        cliente_frame = ttk.LabelFrame(scrollable_frame, text="Dados do Cliente", padding=10)
        cliente_frame.grid(row=current_row, column=0, padx=10, pady=5, sticky="ew"); current_row += 1
        produtos_map = {"BUONNYCHECK ST": "1", "BUONNYCHEK PLUS": "2"}
        ttk.Label(cliente_frame, text="Produto*:").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Combobox(cliente_frame, textvariable=self.cad_vars['produto'], values=list(produtos_map.keys()), state="readonly").grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Label(cliente_frame, text="Embarcador:").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(cliente_frame, textvariable=self.cad_vars['embarcador']).grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Label(cliente_frame, text="Transportador*:").grid(row=1, column=2, sticky="w", pady=2)
        ttk.Entry(cliente_frame, textvariable=self.cad_vars['transportador']).grid(row=1, column=3, sticky="ew", padx=5)
        cliente_frame.columnconfigure(1, weight=1); cliente_frame.columnconfigure(3, weight=1)

        # --- Seção "Dados Contato" ---
        contato_cliente_frame = ttk.LabelFrame(scrollable_frame, text="Dados Contato", padding=10)
        contato_cliente_frame.grid(row=current_row, column=0, padx=10, pady=5, sticky="ew"); current_row += 1
        tipos_retorno = ["E-MAIL", "TELEFONE", "CELULAR", "0800", "RADIO"]
        ttk.Label(contato_cliente_frame, text="Nome*:").grid(row=0, column=0, sticky="w")
        ttk.Entry(contato_cliente_frame, textvariable=self.cad_vars['contato_nome_1']).grid(row=1, column=0, sticky="ew", padx=5)
        ttk.Label(contato_cliente_frame, text="Tipo Retorno*:").grid(row=0, column=1, sticky="w")
        ttk.Combobox(contato_cliente_frame, textvariable=self.cad_vars['contato_tipo_1'], values=tipos_retorno, state="readonly").grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Label(contato_cliente_frame, text="Dados*:").grid(row=0, column=2, sticky="w")
        ttk.Entry(contato_cliente_frame, textvariable=self.cad_vars['contato_dados_1']).grid(row=1, column=2, sticky="ew", padx=5)
        ttk.Label(contato_cliente_frame, text="Nome*:").grid(row=2, column=0, sticky="w", pady=(10,0))
        ttk.Entry(contato_cliente_frame, textvariable=self.cad_vars['contato_nome_2']).grid(row=3, column=0, sticky="ew", padx=5)
        ttk.Label(contato_cliente_frame, text="Tipo Retorno*:").grid(row=2, column=1, sticky="w", pady=(10,0))
        ttk.Combobox(contato_cliente_frame, textvariable=self.cad_vars['contato_tipo_2'], values=tipos_retorno, state="readonly").grid(row=3, column=1, sticky="ew", padx=5)
        ttk.Label(contato_cliente_frame, text="Dados*:").grid(row=2, column=2, sticky="w", pady=(10,0))
        ttk.Entry(contato_cliente_frame, textvariable=self.cad_vars['contato_dados_2']).grid(row=3, column=2, sticky="ew", padx=5)
        contato_cliente_frame.columnconfigure(0, weight=1); contato_cliente_frame.columnconfigure(2, weight=1)

        # --- Seção: Categoria e Dados do Profissional ---
        prof_frame = ttk.LabelFrame(scrollable_frame, text="Categoria e Dados do Profissional", padding=10)
        prof_frame.grid(row=current_row, column=0, padx=10, pady=5, sticky="ew"); current_row += 1
        cat_prof_map = ["CARRETEIRO", "AGREGADO", "FUNCIONÁRIO/MOTORISTA", "PROPRIETÁRIO", "AJUDANTE"]
        ttk.Label(prof_frame, text="Categoria*:").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Combobox(prof_frame, textvariable=self.cad_vars['categoria_prof'], values=cat_prof_map, state="readonly").grid(row=0, column=1, sticky="w", padx=5)
        # (Restante do formulário detalhado, como na versão anterior) ...

        ttk.Button(scrollable_frame, text="Cadastrar Ficha (Simulação)", command=self.buonny_run_cadastro_ficha, style="Accent.TButton").grid(row=current_row, column=0, pady=20, ipady=8)

    def _buonny_attempt_login(self):
        """Pega os dados da UI e tenta realizar o login na Buonny."""
        username = self.buonny_user_entry.get()
        password = self.buonny_pass_entry.get()
        if not username or not password:
            messagebox.showerror("Erro de Login", "Usuário e senha da Buonny são obrigatórios.")
            return

        for widget in self.buonny_login_frame.winfo_children():
            if isinstance(widget, ttk.Frame):
                for sub_widget in widget.winfo_children():
                    sub_widget.config(state="disabled")

        threading.Thread(target=self._worker_buonny_login, args=(username, password), daemon=True).start()

    def _worker_buonny_login(self, username, password):
        """Worker em thread para fazer o login sem travar a UI."""
        login_ok, message = self._buonny_real_login(username, password)

        def update_ui():
            if login_ok:
                self.buonny_is_logged_in = True
                self.buonny_login_frame.pack_forget()
                self.buonny_main_frame.pack(fill='both', expand=True)
                messagebox.showinfo("Sucesso", "Login na Buonny realizado com sucesso!")
            else:
                messagebox.showerror("Falha no Login", message)
                for widget in self.buonny_login_frame.winfo_children():
                     if isinstance(widget, ttk.Frame):
                        for sub_widget in widget.winfo_children():
                            sub_widget.config(state="normal")

        self.ui_queue.put((update_ui, ()))

    def _buonny_real_login(self, username, password):
        """Executa a chamada de login real."""
        url = "https://informacoes.buonny.com.br/informacoes2/usuarios/login"
        payload = {'data[Usuario][apelido]': username, 'data[Usuario][senha]': password}
        try:
            response = self.buonny_session.post(url, data=payload, timeout=15)
            response.raise_for_status()
            if "login" in response.text.lower() or "usuário ou senha" in response.text.lower():
                return False, "Usuário ou Senha inválidos."
            return True, "Login bem-sucedido!"
        except requests.exceptions.RequestException as e:
            return False, f"Erro de conexão: {e}"

    def _buonny_on_cpf_focus_out(self, event):
        cpf_raw = self.c_cpf_var.get()
        cpf_digits = "".join(filter(str.isdigit, cpf_raw))
        if len(cpf_digits) == 11:
            self.c_cpf_var.set(f"{cpf_digits[:3]}.{cpf_digits[3:6]}.{cpf_digits[6:9]}-{cpf_digits[9:]}")
            self._buonny_log_message(f"Buscando nome para o CPF: {cpf_digits}...")
            # ADAPTAÇÃO: Chama a função de busca de driver da própria classe
            driver_name, message = self.buonny_fetch_driver_info(cpf_digits)
            self._buonny_log_message(message, "blue" if driver_name else "red")
            if driver_name: self.c_nome_var.set(driver_name)
        elif cpf_digits: self._buonny_log_message("CPF digitado é inválido (precisa de 11 dígitos).", "red")

    def _buonny_on_city_focus_out(self, event, city_type):
        if city_type == 'origem':
            city_name = self.c_origem_cidade_var.get()
            if not city_name: return
            self._buonny_log_message(f"Buscando dados para origem: '{city_name}'...")
            # ADAPTAÇÃO: Chama a função de busca de cidade da própria classe
            city_id, state, country, message = self.buonny_fetch_city_id(city_name)
            self.c_origem_cidade_id = city_id
            if city_id:
                self.c_origem_estado_var.set(state or ""); self.c_origem_pais_var.set(country or "")
            self._buonny_log_message(message, "blue" if city_id else "red")
        elif city_type == 'destino':
            city_name = self.c_destino_cidade_var.get()
            if not city_name: return
            self._buonny_log_message(f"Buscando dados para destino: '{city_name}'...")
            city_id, state, country, message = self.buonny_fetch_city_id(city_name)
            self.c_destino_cidade_id = city_id
            if city_id:
                self.c_destino_estado_var.set(state or ""); self.c_destino_pais_var.set(country or "")
            self._buonny_log_message(message, "blue" if city_id else "red")

    def buonny_run_consultation(self):
        self._buonny_log_message("\nIniciando consulta...", "blue")
        if not all([self.c_carga_tipo_var.get(), self.c_carga_valor_var.get(), self.c_origem_cidade_id, self.c_destino_cidade_id, self.c_nome_var.get()]):
            messagebox.showwarning("Atenção", "Todos os campos de pré-consulta (CPF, Cidades, Carga) devem ser preenchidos e validados.")
            return
        threading.Thread(target=self._worker_buonny_run_consultation, daemon=True).start()

    def _worker_buonny_run_consultation(self):
        tipo_id = self.carga_tipo_map.get(self.c_carga_tipo_var.get())
        valor_id = self.carga_valor_map.get(self.c_carga_valor_var.get())
        payload = {
            "data[Ficha][codigo_produto]": "2", "data[cliente][codigo]": self.c_codigo_var.get(),
            "data[Ficha][codigo_cliente_transportador]": self.c_codigo_var.get(),
            "data[Profissional][codigo_documento]": self.c_cpf_var.get(),
            "data[profissional][nome]": self.c_nome_var.get(),
            "data[veiculo][placa]": self.c_placa_veiculo_var.get(), "data[carreta][placa]": self.c_placa_carreta_var.get(),
            "data[Consulta][codigo_carga_tipo]": tipo_id, "data[Consulta][codigo_carga_valor]": valor_id,
            "data[Consulta][descricao_endereco_cidade_carga_origem]": self.c_origem_cidade_var.get(),
            "data[Consulta][abreviacao_endereco_estado_carga_origem]": self.c_origem_estado_var.get(),
            "data[Consulta][abreviacao_endereco_pais_carga_origem]": self.c_origem_pais_var.get(),
            "data[Consulta][descricao_endereco_cidade_carga_destino]": self.c_destino_cidade_var.get(),
            "data[Consulta][abreviacao_endereco_estado_carga_destino]": self.c_destino_estado_var.get(),
            "data[Consulta][abreviacao_endereco_pais_carga_destino]": self.c_destino_pais_var.get(),
            "data[Consulta][codigo_endereco_cidade_carga_origem]": self.c_origem_cidade_id,
            "data[Consulta][codigo_endereco_cidade_carga_destino]": self.c_destino_cidade_id,
        }

        self.ui_queue.put((self._buonny_log_message, ("Enviando Payload...\n" + json.dumps(payload, indent=2), "white")))
        # ADAPTAÇÃO: Chama a função de consulta real da própria classe
        resultado = self.buonny_run_real_consultation(payload)

        def process_result():
            if isinstance(resultado, dict):
                if resultado.get("tipo") == "ACEITEFOTO":
                    self._buonny_log_message("\n--- RESPOSTA INICIAL: ACEITEFOTO ---\n", "darkgoldenrod")
                    self._buonny_log_message(json.dumps(resultado, indent=4, ensure_ascii=False), "darkgoldenrod")
                    photo_url = resultado.get("linkFoto")
                    if photo_url: self.buonny_show_photo_confirmation(photo_url)
                else:
                    self._buonny_log_message("\n--- STATUS FINAL (DIRETO) ---\n", "green")
                    status_msg = resultado.get('mensagem', 'Status não encontrado.')
                    num_consulta = resultado.get('numero_liberacao') or resultado.get('codigo_log_faturamento', '')
                    obs_msg = resultado.get('observacao', '')
                    self._buonny_log_message(f"Status: {status_msg} (Consulta: {num_consulta})", "red" if "INSUFICIÊNCIA" in status_msg.upper() else "green")
                    if obs_msg: self._buonny_log_message(f"Observação: {obs_msg}", "darkgoldenrod")
            else:
                self._buonny_log_message("\n--- RESPOSTA DO SERVIDOR ---\n", "red")
                self._buonny_log_message(resultado, "red")

        self.ui_queue.put((process_result, ()))

    def buonny_show_photo_confirmation(self, url):
        self._buonny_log_message("Baixando foto para confirmação...", "blue")
        image_data = self.buonny_download_image(url)
        if not image_data:
            self._buonny_log_message("Falha ao baixar a imagem.", "red")
            messagebox.showerror("Erro de Imagem", "Não foi possível carregar a foto do motorista.")
            return

        top = tk.Toplevel(self.root)
        top.title("Confirmação de Profissional")
        top.configure(bg=BG_COLOR)

        try:
            pil_image = Image.open(BytesIO(image_data))
            max_height = 350; ratio = max_height / pil_image.height
            new_width = int(pil_image.width * ratio)
            pil_image = pil_image.resize((new_width, max_height), Image.Resampling.LANCZOS)
            tk_image = ImageTk.PhotoImage(pil_image)
            image_label = tk.Label(top, image=tk_image, bg=BG_COLOR)
            image_label.image = tk_image; image_label.pack(pady=10, padx=10)
        except Exception as e:
            self._buonny_log_message(f"Erro ao processar imagem: {e}", "red")
            ttk.Label(top, text="Foto indisponível ou erro ao carregar.", style="App.TLabel").pack(padx=20, pady=20)

        ttk.Label(top, text="A foto apresentada é idêntica ao profissional?", font=("Segoe UI", 12, "bold"), style="App.TLabel").pack(pady=(0, 10))
        button_frame = ttk.Frame(top, style="App.TFrame")
        button_frame.pack(pady=10, fill=tk.X, padx=10)

        def on_confirm():
            self._buonny_log_message("Confirmando foto...", "blue")
            top.destroy()
            final_status = self.buonny_confirm_photo()

            self._buonny_log_message("\n--- STATUS FINAL (PÓS-FOTO) ---\n", "green")
            if isinstance(final_status, dict):
                status_msg = final_status.get('mensagem', 'Status não encontrado.')
                num_consulta = final_status.get('numero_liberacao') or final_status.get('codigo_log_faturamento', '')
                obs_msg = final_status.get('observacao', '')
                self._buonny_log_message(f"Status: {status_msg} (Consulta: {num_consulta})", "green")
                if obs_msg: self._buonny_log_message(f"Observação: {obs_msg}", "darkgoldenrod")
            else:
                self._buonny_log_message(str(final_status), "red")

        ttk.Button(button_frame, text="Sim, confirmo", command=on_confirm, style="Accent.TButton").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5, ipady=5)
        ttk.Button(button_frame, text="Não é ele", command=top.destroy, style="Outline.TButton").pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=5, ipady=5)

    def buonny_clear_fields_tab1(self):
        self.c_cpf_var.set(""); self.c_nome_var.set(""); self.c_placa_veiculo_var.set("")
        self.c_placa_carreta_var.set(""); self.c_origem_cidade_var.set(""); self.c_origem_estado_var.set("")
        self.c_destino_cidade_var.set(""); self.c_destino_estado_var.set(""); self.c_carga_tipo_var.set("PRODUTOS AGRÍCOLAS")
        self.c_carga_valor_var.set(""); self.c_origem_pais_var.set(""); self.c_destino_pais_var.set("")
        self.c_origem_cidade_id = None; self.c_destino_cidade_id = None
        self.buonny_result_text.config(state="normal"); self.buonny_result_text.delete('1.0', tk.END); self.buonny_result_text.config(state="disabled")

    def buonny_run_cadastro_ficha(self):
        self._buonny_log_message("\n--- SIMULAÇÃO DE CADASTRO DE FICHA ---", "purple")
        collected_data = {key: var.get() for key, var in self.cad_vars.items()}
        xml_string = "<soapenv:Envelope ...>\n  <soapenv:Body>\n    <ficha>\n"
        produtos_map = {"BUONNYCHECK ST": "1", "BUONNYCHEK PLUS": "2"}
        produto_cod = produtos_map.get(collected_data.get('produto'), '')
        xml_string += f"      <autenticacao> ... </autenticacao>\n"
        xml_string += f"      <produto>{produto_cod}</produto>\n"
        xml_string += f"      <cnpj_transportador>{collected_data.get('transportador')}</cnpj_transportador>\n"
        xml_string += "      <profissional>\n"
        xml_string += f"        <documento>{collected_data.get('cpf')}</documento>\n"
        xml_string += f"        <nome>{collected_data.get('nome')}</nome>\n"
        xml_string += "        ...\n"
        xml_string += "      </profissional>\n"
        xml_string += "    </ficha>\n  </soapenv:Body>\n</soapenv:Envelope>"
        self._buonny_log_message("O XML a seguir seria enviado (modelo simplificado):", "purple")
        self._buonny_log_message(xml_string)
        self._buonny_log_message("\nSimulação de Sucesso: Ficha de Profissional incluida com sucesso", "green")

