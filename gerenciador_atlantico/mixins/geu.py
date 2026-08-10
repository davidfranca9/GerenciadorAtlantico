from ..shared import *
from ..servicos.bsoft_api import *
from ..servicos.comunicacao import *
from ..servicos.documentos import *
from ..servicos.ocr import *
from ..servicos.relatorios import *
from ..servicos.startup import *

class GeuMixin:
    def setup_geu_frame(self, parent_frame):
        """Cria a estrutura da página 'Análise de Fretes' com suas próprias sub-abas internas."""

        # O Notebook interno agora é criado dentro do 'parent_frame'
        # e o estilo das abas internas também é ajustado para consistência.
        style = ttk.Style()
        style.configure("Inner.TNotebook.Tab", 
                        background=FRAME_COLOR, 
                        foreground=GRAY_TEXT_COLOR,
                        font=("Segoe UI", 10, "bold"),
                        padding=(12, 6),
                        borderwidth=0)
        style.map("Inner.TNotebook.Tab", 
                  background=[("selected", BG_COLOR)],
                  foreground=[("selected", ACCENT_COLOR)])

        geu_notebook = ttk.Notebook(parent_frame, style="Inner.TNotebook")
        geu_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Usando ttk.Frame para que as sub-abas herdem o estilo
        frame_lancamentos = ttk.Frame(geu_notebook, style="App.TFrame")
        frame_analise = ttk.Frame(geu_notebook, style="App.TFrame")
        frame_representantes = ttk.Frame(geu_notebook, style="App.TFrame")

        geu_notebook.add(frame_lancamentos, text=" Lançamentos Gerais ")
        geu_notebook.add(frame_analise, text=" Análise de Fretes ")
        geu_notebook.add(frame_representantes, text=" Visão por Representante ")

        # Chama as funções que constroem o conteúdo de cada sub-aba
        self._setup_geu_lancamentos_subtab(frame_lancamentos)
        self._setup_geu_analise_subtab(frame_analise)
        self._setup_geu_representantes_subtab(frame_representantes)

        # Carrega os dados iniciais
        self.carregar_dados_geu()

    def _setup_geu_lancamentos_subtab(self, parent_frame):
        top_frame = ttk.Frame(parent_frame, style="App.TFrame")
        top_frame.pack(fill=tk.X, padx=10, pady=10)
        btn_atualizar = ttk.Button(top_frame, text="🔄 Atualizar Lançamentos", command=self.carregar_dados_geu, style="Outline.TButton")
        btn_atualizar.pack(side=tk.LEFT, padx=(0, 10), ipady=5)
        btn_gerar_relatorio = ttk.Button(top_frame, text="📊 Gerar Relatório Consolidado", command=self.gerar_relatorio_consolidado, style="Outline.TButton")
        btn_gerar_relatorio.pack(side=tk.LEFT, ipady=5)
        btn_adicionar = ttk.Button(top_frame, text="➕ Adicionar Pedido", command=self.abrir_janela_novo_pedido, style="Accent.TButton")
        btn_adicionar.pack(side=tk.RIGHT, ipady=5)

        tree_frame = ttk.Frame(parent_frame, style="App.TFrame")
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        cols = ('Data', 'Representante', 'Cliente', 'Destino', 'Roteiro', 'Produto', 'Peso (Ton)', 'Valor_Frete')
        self.tree_lancamentos = ttk.Treeview(tree_frame, columns=cols, show="headings", style="App.Treeview")

        col_widths = {'Data': 90, 'Representante': 120, 'Cliente': 200, 'Destino': 180, 'Roteiro': 120, 'Produto': 180, 'Peso (Ton)': 100, 'Valor_Frete': 100}
        for col, width in col_widths.items(): self.tree_lancamentos.heading(col, text=col); self.tree_lancamentos.column(col, width=width, anchor='center')
        self.tree_lancamentos.column("Cliente", anchor='w'); self.tree_lancamentos.column("Produto", anchor='w'); self.tree_lancamentos.column("Destino", anchor='w')

        self.tree_lancamentos.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_lancamentos.bind("<MouseWheel>", lambda event, t=self.tree_lancamentos: self._on_treeview_scroll(event, t))

    def _setup_geu_analise_subtab(self, parent_frame):
        """Cria a UI da sub-aba de Análise, focada na consulta do último frete."""
        main_frame = tk.Frame(parent_frame, bg="#012623")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # --- Seção de Consulta no Topo ---
        consulta_frame = tk.Frame(main_frame, bg="#012623")
        consulta_frame.pack(fill=tk.X, pady=(0, 25))
        tk.Label(consulta_frame, text="Consultar Último Frete Para o Destino:", font=("Arial", 12, "bold"), bg="#012623", fg="white").pack(side=tk.LEFT, padx=(10, 5))
        self.entry_geu_consulta_cidade = tk.Entry(consulta_frame, font=("Arial", 12), width=35)
        self.entry_geu_consulta_cidade.pack(side=tk.LEFT, padx=5, ipady=4)
        btn_buscar = tk.Button(consulta_frame, text="🔍 Buscar", command=self.consultar_ultimo_frete_geu, font=("Arial", 11, "bold"), bg="#007bff", fg="white")
        btn_buscar.pack(side=tk.LEFT, padx=5, ipady=4)

        # --- Frame para exibir os resultados ---
        self.frame_geu_resultado_consulta = ttk.LabelFrame(main_frame, text=" Resultado da Consulta ", style='Dark.TLabelframe')
        self.frame_geu_resultado_consulta.pack(fill=tk.X, pady=5, padx=10, ipady=10)
        self.frame_geu_resultado_consulta.columnconfigure(1, weight=1)

        # Labels para os resultados
        self.analise_labels = {}
        campos_analise = ["Destino:", "Data do Pedido:", "Produto:", "Peso (Ton):", "Valor do Frete:", "Valor por Tonelada:"]
        for i, campo in enumerate(campos_analise):
            tk.Label(self.frame_geu_resultado_consulta, text=campo, font=("Arial", 11, "bold"), bg="#012623", fg="white").grid(row=i, column=0, sticky='w', padx=10, pady=6)
            lbl_valor = tk.Label(self.frame_geu_resultado_consulta, text="-", font=("Arial", 11, "italic"), bg="#012623", fg="#FFC107")
            lbl_valor.grid(row=i, column=1, sticky='w', padx=10, pady=6)
            self.analise_labels[campo] = lbl_valor

    def _setup_geu_representantes_subtab(self, parent_frame):
        """Cria a UI da sub-aba de Visão por Representante."""
        top_frame = tk.Frame(parent_frame, bg="#012623")
        top_frame.pack(fill=tk.X, padx=10, pady=10)

        # Frame para o combo e a label
        combo_frame = tk.Frame(top_frame, bg="#012623")
        combo_frame.pack(side=tk.LEFT, padx=(0, 20))

        tk.Label(combo_frame, text="Selecione um Representante:", font=("Arial", 11, "bold"), bg="#012623", fg="white").pack(side=tk.LEFT, padx=(0, 10))
        self.combo_representantes = ttk.Combobox(combo_frame, font=("Arial", 11), state="readonly", width=30)
        self.combo_representantes.pack(side=tk.LEFT)
        self.combo_representantes.bind("<<ComboboxSelected>>", self.atualizar_visao_representante)

        # --- BOTÃO FILTRADO PELO REPRESENTANTE (CORRETO) ---
        btn_gerar_relatorio_rep = tk.Button(top_frame, 
            text="📊 Gerar Relatório Deste Representante (PDF)", 
            command=self.gerar_relatorio_representante_selecionado, 
            font=("Arial", 11, "bold"), bg="#007bff", fg="white")
        btn_gerar_relatorio_rep.pack(side=tk.RIGHT)
        # --------------------------------------------------------

        tree_frame = tk.Frame(parent_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        cols = ('Data', 'Cliente', 'Destino', 'Roteiro', 'Produto', 'Peso (Ton)', 'Valor_Frete')
        self.tree_representantes = ttk.Treeview(tree_frame, columns=cols, show="headings")

        col_widths = {'Data': 90, 'Cliente': 220, 'Destino': 200, 'Roteiro': 120, 'Produto': 200, 'Peso (Ton)': 100, 'Valor_Frete': 100}
        for col, width in col_widths.items():
            self.tree_representantes.heading(col, text=col)
            self.tree_representantes.column(col, width=width, anchor='center')

        self.tree_representantes.column("Cliente", anchor='w')
        self.tree_representantes.column("Produto", anchor='w')
        self.tree_representantes.column("Destino", anchor='w')

        self.tree_representantes.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_representantes.yview)
        self.tree_representantes.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_representantes.configure(yscroll=scrollbar.set)

    def carregar_dados_geu(self):
        """[INICIADOR CENTRAL] Dispara a thread para carregar e processar os dados da Planilha do Geu."""
        self.analise_labels["Destino:"].config(text="Atualizando dados...")
        for tree in [self.tree_lancamentos, self.tree_representantes]:
            for i in tree.get_children():
                tree.delete(i)

        threading.Thread(target=self._worker_carregar_dados_geu, daemon=True).start()

    def _worker_carregar_dados_geu(self):
        """[THREAD] Busca, limpa e processa os dados."""
        try:
            # ATENÇÃO: Verifique se o nome da sua aba de dados é "Lançamentos"
            aba = self._conectar_google_sheets("Lançamentos") 
            if not aba: raise ConnectionError("Falha ao conectar na aba 'Lançamentos'. Verifique o nome da aba na sua planilha.")

            registros = aba.get_all_records()
            if not registros:
                self.ui_queue.put((messagebox.showinfo, ("Planilha do Geu", "Nenhum lançamento encontrado.")))
                self.df_geu = pd.DataFrame()
                return

            df = pd.DataFrame(registros)

            # Renomeia colunas para consistência (da planilha para o código)
            # Se os nomes na sua planilha forem diferentes, ajuste aqui
            mapeamento_colunas = {
                'Data do Pedido': 'Data', 'Nome do Cliente': 'Cliente', 'Destino (Cidade)': 'Destino'
            }
            df.rename(columns=mapeamento_colunas, inplace=True)

            df['Valor_Frete'] = pd.to_numeric(df['Valor_Frete'].astype(str).str.replace('.', '', regex=False).str.replace(',', '.'), errors='coerce')
            df['Peso (Ton)'] = pd.to_numeric(df['Peso (Ton)'].astype(str).str.replace('.', '', regex=False).str.replace(',', '.'), errors='coerce')
            df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
            df.dropna(subset=['Data'], inplace=True)
            df.sort_values(by='Data', ascending=False, inplace=True)

            df['Valor/Ton'] = (df['Valor_Frete'] / df['Peso (Ton)']).fillna(0)
            df = df.fillna('')

            self.df_geu = df.copy()

            self.ui_queue.put((self._atualizar_visao_geral, ()))
            self.ui_queue.put((self.atualizar_visao_representante, ()))
            self.ui_queue.put((lambda: self.analise_labels["Destino:"].config(text="-"), ()))

        except Exception as e:
            traceback.print_exc()
            self.df_geu = pd.DataFrame()
            self.ui_queue.put((messagebox.showerror, ("Erro na Planilha do Geu", f"Ocorreu um erro ao processar os dados:\n\n{e}")))
            self.ui_queue.put((lambda: self.analise_labels["Destino:"].config(text="Falha ao carregar dados."), ()))

    def _atualizar_visao_geral(self):
        """[UI] Preenche a tabela de Lançamentos Gerais."""
        if self.df_geu is None: return
        for i in self.tree_lancamentos.get_children(): self.tree_lancamentos.delete(i)

        for _, row in self.df_geu.iterrows():
            self.tree_lancamentos.insert("", tk.END, values=(
                row['Data'].strftime('%d/%m/%Y'),
                row.get('Representante', ''), row.get('Cliente', ''), row.get('Destino', ''),
                row.get('Roteiro', ''), row.get('Produto', ''),
                f"{row.get('Peso (Ton)', 0):.3f}".replace('.', ',') if pd.notna(row.get('Peso (Ton)')) else '0,000',
                f"{row.get('Valor_Frete', 0):.2f}".replace('.', ',') if pd.notna(row.get('Valor_Frete')) else '0,00',
            ))

    def atualizar_visao_representante(self, event=None):
        """[UI] Filtra e exibe os dados para o representante selecionado."""
        if self.df_geu is None: return
        for i in self.tree_representantes.get_children(): self.tree_representantes.delete(i)

        representantes = sorted(self.df_geu['Representante'].astype(str).unique().tolist())
        if representantes: self.combo_representantes['values'] = representantes

        rep_selecionado = self.combo_representantes.get()
        if not rep_selecionado: return

        df_filtrado = self.df_geu[self.df_geu['Representante'] == rep_selecionado]

        for _, row in df_filtrado.iterrows():
            self.tree_representantes.insert("", tk.END, values=(
                row['Data'].strftime('%d/%m/%Y'),
                row.get('Cliente', ''), row.get('Destino', ''), row.get('Roteiro', ''), row.get('Produto', ''),
                f"{row.get('Peso (Ton)', 0):.3f}".replace('.', ',') if pd.notna(row.get('Peso (Ton)')) else '0,000',
                f"{row.get('Valor_Frete', 0):.2f}".replace('.', ',') if pd.notna(row.get('Valor_Frete')) else '0,00',
            ))

    def consultar_ultimo_frete_geu(self):
        """Busca o último frete para uma cidade e preenche a aba de Análise."""
        for lbl in self.analise_labels.values(): lbl.config(text="-") # Limpa os resultados anteriores

        cidade_busca = self.entry_geu_consulta_cidade.get().strip()
        if not cidade_busca:
            messagebox.showwarning("Busca Vazia", "Por favor, digite um destino para a busca.")
            return
        if self.df_geu is None or self.df_geu.empty:
            messagebox.showerror("Dados Indisponíveis", "Os dados não foram carregados. Clique em 'Atualizar' na aba Lançamentos primeiro.")
            return

        df_cidade = self.df_geu[self.df_geu['Destino'].str.contains(cidade_busca, case=False, na=False)]
        if df_cidade.empty:
            self.analise_labels["Destino:"].config(text=f"Nenhum frete encontrado para '{cidade_busca}'.")
        else:
            ultimo = df_cidade.iloc[0]
            self.analise_labels["Destino:"].config(text=ultimo.get('Destino', ''))
            self.analise_labels["Data do Pedido:"].config(text=ultimo['Data'].strftime('%d/%m/%Y'))
            self.analise_labels["Produto:"].config(text=ultimo.get('Produto', ''))
            self.analise_labels["Peso (Ton):"].config(text=f"{ultimo.get('Peso (Ton)', 0):.3f}".replace('.', ','))
            self.analise_labels["Valor do Frete:"].config(text=f"R$ {ultimo.get('Valor_Frete', 0):.2f}".replace('.', ','))
            self.analise_labels["Valor por Tonelada:"].config(text=f"R$ {ultimo.get('Valor/Ton', 0):.2f}".replace('.', ','))

    def abrir_janela_novo_pedido(self):
        """Abre uma janela para adicionar um novo lançamento."""
        dialog = Toplevel(self.root)
        dialog.title("Adicionar Novo Pedido")
        dialog.geometry("450x480") # Aumentei a altura
        dialog.configure(bg="#012623")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        frame = Frame(dialog, bg="#012623", padx=20, pady=20)
        frame.pack(fill="both", expand=True)

        campos = ['Data', 'Representante', 'Cliente', 'Destino', 'Roteiro', 'Produto', 'Peso (Ton)', 'Valor_Frete']
        entries = {}

        for i, campo in enumerate(campos):
            Label(frame, text=f"{campo.replace('_', ' ')}:", font=("Arial", 11), bg="#012623", fg="white").grid(row=i, column=0, sticky='w', pady=7, padx=5)
            entry = tk.Entry(frame, font=("Arial", 11), width=35)
            entry.grid(row=i, column=1, sticky='ew', pady=7, padx=5)
            entries[campo] = entry

        entries['Data'].insert(0, datetime.now().strftime('%d/%m/%Y'))

        btn_frame = Frame(frame, bg="#012623")
        btn_frame.grid(row=len(campos), column=0, columnspan=2, pady=25)

        btn_salvar = Button(btn_frame, text="Salvar Lançamento", font=("Arial", 12, "bold"), bg="#28A745", fg="white", 
                            command=lambda: self._salvar_novo_pedido(dialog, entries), relief="raised", bd=3, padx=10, pady=5)
        btn_salvar.pack()

    def _salvar_novo_pedido(self, dialog, entries):
        """Coleta, valida e inicia o processo de salvar o novo pedido."""
        try:
            nova_linha = []
            ordem_colunas = ['Data', 'Representante', 'Cliente', 'Destino', 'Roteiro', 'Produto', 'Peso (Ton)', 'Valor_Frete']

            for campo in ordem_colunas:
                valor = entries[campo].get().strip()
                if not valor:
                    messagebox.showwarning("Campo Vazio", f"O campo '{campo}' é obrigatório.", parent=dialog)
                    return
                nova_linha.append(valor)

            float(nova_linha[-2].replace(',', '.'))
            float(nova_linha[-1].replace(',', '.'))

            dialog.destroy()

            threading.Thread(target=self._worker_salvar_novo_pedido, args=(nova_linha,), daemon=True).start()
        except ValueError:
            messagebox.showwarning("Valor Inválido", "Os campos 'Peso (Ton)' e 'Valor_Frete' devem ser números.", parent=dialog)

    def _worker_salvar_novo_pedido(self, nova_linha):
        """[THREAD] Salva a nova linha na Planilha Google."""
        try:
            aba = self._conectar_google_sheets("Lançamentos")
            if not aba: raise ConnectionError("Falha ao conectar para salvar o pedido.")

            aba.append_row(nova_linha, value_input_option='USER_ENTERED')

            self.ui_queue.put((messagebox.showinfo, ("Sucesso", "Novo pedido salvo! A lista será atualizada.")))
            self.ui_queue.put((self.carregar_dados_geu, ()))

        except Exception as e:
            traceback.print_exc()
            self.ui_queue.put((messagebox.showerror, ("Erro ao Salvar", f"Não foi possível salvar na nuvem:\n\n{e}")))

    def _agregar_dados_para_relatorio(self, df):
        """
        [AJUSTADO] Agrega os dados do DataFrame de Lançamentos (df_geu)
        Calcula a média por tonelada e remove colunas não solicitadas.
        """
        if df is None or df.empty:
            return None

        df_relatorio = df.copy()

        # 1. Pré-processamento e Cálculo da Média
        df_relatorio['Peso (Ton)'] = pd.to_numeric(df_relatorio['Peso (Ton)'].astype(str).str.replace(',', '.'), errors='coerce')
        df_relatorio['Valor_Frete'] = pd.to_numeric(df_relatorio['Valor_Frete'].astype(str).str.replace(',', '.'), errors='coerce')
        df_relatorio.dropna(subset=['Peso (Ton)', 'Valor_Frete', 'Data'], inplace=True) 

        # 2. Cálculo dos Totais e Média
        peso_total = df_relatorio['Peso (Ton)'].sum()
        valor_total = df_relatorio['Valor_Frete'].sum()
        media_frete_ton = (valor_total / peso_total) if peso_total > 0 else 0

        # 3. Prepara a lista de itens para a tabela
        lista_itens = []
        for _, row in df_relatorio.iterrows():
            data_formatada = row['Data'].strftime('%d/%m/%Y')
            peso_formatado = f"{row['Peso (Ton)']:.2f}".replace('.', ',')
            valor_formatado = f"R$ {row['Valor_Frete']:.2f}".replace('.', ',')

            # Nota: 'Nro. Pedido' e 'Roteiro Poteiro' foram removidos
            lista_itens.append({
                'Data Pedido': data_formatada,
                'Nro. Pedido': row.get('Nro. Pedido', ''),
                'Cliente': row.get('Cliente', ''),
                'Cidade Dest.': row.get('Destino', ''),
                'Roteiro': row.get('Roteiro', ''),
                'Peso (Ton)': peso_formatado,
                'Valor Frete': valor_formatado,
            })

        # 4. Determina o período
        periodo = "PERÍODO INDEFINIDO"
        if not df_relatorio.empty:
            data_mais_recente = df_relatorio['Data'].max()
            periodo = data_mais_recente.strftime('%B/%Y').upper()

        return {
            'Itens': lista_itens,
            'Peso Total (Ton)': peso_total,
            'Media Frete / Ton': media_frete_ton,
            'Total Geral de Pedidos': len(df_relatorio),
            'Periodo': periodo
        }

    def gerar_relatorio_consolidado(self, df_filtro=None, filtro_aplicado="TODOS OS LANÇAMENTOS"):
        """
        [AJUSTADO] Gera o relatório consolidado (PDF) usando ReportLab.
        Agora aceita um DataFrame filtrado.
        """
        df_a_usar = df_filtro if df_filtro is not None else self.df_geu

        if df_a_usar is None or df_a_usar.empty:
            messagebox.showwarning("Dados Ausentes", "O DataFrame está vazio. Verifique a planilha ou o filtro.")
            return

        # 1. Obter dados do DF (DataFrame)
        dados_relatorio = self._agregar_dados_para_relatorio(df_a_usar)
        if not dados_relatorio:
            messagebox.showwarning("Dados Insuficientes", "Não há dados válidos para gerar o relatório.")
            return

        # 2. Escolher onde salvar o arquivo
        nome_filtro = re.sub(r'[\\/*?:"<>|]', '', filtro_aplicado).replace(" ", "_")
        default_filename = f"Relatorio_Pedidos_{nome_filtro}_{dados_relatorio['Periodo']}_{datetime.now().strftime('%Y%m%d')}.pdf"

        save_path_pdf = filedialog.asksaveasfilename(
            defaultextension=".pdf", 
            filetypes=[("PDF Document", "*.pdf")],
            title=f"Salvar Relatório de {filtro_aplicado} Como...", 
            initialfile=default_filename
        )
        if not save_path_pdf: return

        # 3. Gerar o PDF
        try:
            # Chama a função ReportLab AJUSTADA
            gerar_pdf_reportlab_ajustado(save_path_pdf, dados_relatorio, filtro_aplicado)
            open_file(save_path_pdf)
            messagebox.showinfo("Sucesso", f"Relatório de {filtro_aplicado} gerado com sucesso!")
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Erro na Geração PDF", f"Falha ao gerar o arquivo PDF:\n\n{e}")

    def gerar_relatorio_representante_selecionado(self):
        """
        Filtra os dados pelo representante selecionado e chama a função de geração de relatório.
        """
        rep_selecionado = self.combo_representantes.get()
        if not rep_selecionado:
            messagebox.showwarning("Filtro Ausente", "Por favor, selecione um Representante na lista suspensa.")
            return

        if self.df_geu is None or self.df_geu.empty:
            messagebox.showwarning("Dados Ausentes", "Os dados de Lançamentos não estão carregados.")
            return

        df_filtrado = self.df_geu[self.df_geu['Representante'] == rep_selecionado]

        if df_filtrado.empty:
            messagebox.showinfo("Sem Dados", f"Não há lançamentos para o representante '{rep_selecionado}'.")
            return

        # Chama a função de geração, passando o DataFrame filtrado e o nome do filtro
        filtro_aplicado = f"REPRESENTANTE: {rep_selecionado}"
        self.gerar_relatorio_consolidado(df_filtro=df_filtrado, filtro_aplicado=filtro_aplicado)

    def _open_calendar(self):
        """Abre um calendário pop-up estilizado para selecionar a data."""

        # Cria uma janela pop-up
        top = Toplevel(self.root)
        top.title("Selecione a Data")
        top.geometry("300x250")
        top.configure(bg=BG_COLOR)
        top.transient(self.root)
        top.grab_set()

        # Cria o widget de calendário com as cores do tema
        cal = Calendar(
            top,
            selectmode='day',
            font=("Segoe UI", 10),
            background=BG_COLOR,
            foreground=TEXT_COLOR,
            headersbackground=FRAME_COLOR,
            headersforeground=ACCENT_COLOR,
            normalbackground=FRAME_COLOR,
            normalforeground=TEXT_COLOR,
            othermonthforeground=GRAY_TEXT_COLOR,
            othermonthweforeground=GRAY_TEXT_COLOR,
            selectbackground=ACCENT_COLOR,
            selectforeground=BG_COLOR,
            weekendbackground=FRAME_COLOR,
            weekendforeground=TEXT_COLOR,
            locale='pt_BR'
        )
        cal.pack(pady=10, padx=10, fill="both", expand=True)

        def on_date_select():
            """Atualiza o campo de data e fecha o pop-up."""
            self.data_carregamento_var.set(cal.get_date())
            top.destroy()

        # Botão de confirmação
        btn_ok = ttk.Button(top, text="Confirmar", command=on_date_select, style="Accent.TButton")
        btn_ok.pack(pady=5)

    def _on_treeview_scroll(self, event, tree):
        """Permite a rolagem da tabela com o mouse."""
        if event.delta:
            tree.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _increment_date(self):
        """Aumenta o dia da data de carregamento em 1."""
        try:
            current_date = datetime.strptime(self.data_carregamento_var.get(), '%d/%m/%Y')
            new_date = current_date + timedelta(days=1)
            self.data_carregamento_var.set(new_date.strftime('%d/%m/%Y'))
        except (ValueError, TypeError):
            # Se a data estiver em formato inválido, reseta para hoje
            self.data_carregamento_var.set(datetime.today().strftime('%d/%m/%Y'))

    def _decrement_date(self):
        """Diminui o dia da data de carregamento em 1."""
        try:
            current_date = datetime.strptime(self.data_carregamento_var.get(), '%d/%m/%Y')
            new_date = current_date - timedelta(days=1)
            self.data_carregamento_var.set(new_date.strftime('%d/%m/%Y'))
        except (ValueError, TypeError):
            # Se a data estiver em formato inválido, reseta para hoje
            self.data_carregamento_var.set(datetime.today().strftime('%d/%m/%Y'))

