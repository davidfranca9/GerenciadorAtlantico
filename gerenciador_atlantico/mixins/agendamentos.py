from ..shared import *
from ..servicos.bsoft_api import *
from ..servicos.comunicacao import *
from ..servicos.documentos import *
from ..servicos.ocr import *
from ..servicos.relatorios import *
from ..servicos.startup import *

class AgendamentosMixin:
    def toggle_treeview_selection(self, event):
        item_id = self.tree_agendamentos.identify_row(event.y)
        if not item_id: return
        if item_id in self.tree_agendamentos.selection():
            self.tree_agendamentos.selection_remove(item_id)
        else:
            self.tree_agendamentos.selection_add(item_id)

    def _conectar_google_sheets(self, nome_da_aba):
        try:
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(os.path.abspath(__file__))

            caminho_credenciais = os.path.join(base_path, "credentials.json.json")
            if not os.path.exists(caminho_credenciais):
                caminho_credenciais = "credentials.json.json"
                if not os.path.exists(caminho_credenciais):
                    raise FileNotFoundError("Arquivo 'credentials.json.json' não encontrado.")

            nome_da_planilha = "Controle de carta frete"
            gc = gspread.service_account(filename=caminho_credenciais)
            planilha = gc.open(nome_da_planilha)
            return planilha.worksheet(nome_da_aba)
        except Exception as e:
            if not self.is_closing:
                self.ui_queue.put((messagebox.showerror, ("Erro de Conexão (Google Sheets)", f"Não foi possível conectar à planilha.\n\nDetalhe: {e}")))
            return None

    def adicionar_agendamento_na_planilha(self):
        aba = self._conectar_google_sheets("Agendamentos")
        if aba is None: return
        try:
            produtos_marcados = self._get_produtos_marcados()
            if not produtos_marcados:
                # Não mostra aviso aqui para não interromper o fluxo automático do gerar_oc
                return

            linhas_para_adicionar = []
            nome_motorista = self.entry_nome.get()
            placa_cavalo = self.entry_placa1.get()

            # --- CORREÇÃO DATA ---
            data_agendamento = self.data_carregamento_var.get()
            # ---------------------

            for produto in produtos_marcados:
                nova_linha = [
                    nome_motorista, produto.get("cidade", ""), placa_cavalo,
                    produto.get("contrato", ""), produto.get("cliente", ""), produto.get("produto", ""),
                    str(produto.get("toneladas")).replace(".", ","), data_agendamento,
                    "Aguardando Agendamento", ""
                ]
                linhas_para_adicionar.append(nova_linha)
                self._abater_saldo_pedido_grande(produto)

            aba.append_rows(linhas_para_adicionar, value_input_option='USER_ENTERED')
            print(f"SUCESSO: Agendamento para {nome_motorista} adicionado e saldo abatido.")
        except Exception as e:
            messagebox.showwarning("Aviso de Agendamento", f"Ocorreu um erro ao registrar o agendamento na nuvem:\n\n{e}")
        aba = self._conectar_google_sheets("Agendamentos")
        if aba is None: return
        try:
            produtos_marcados = self._get_produtos_marcados()
            if not produtos_marcados:
                messagebox.showwarning("Aviso", "Nenhum produto selecionado.")
                return

            linhas_para_adicionar = []
            nome_motorista = self.entry_nome.get()
            placa_cavalo = self.entry_placa1.get()
            data_agendamento = f"{self.dia_var.get():02d}/{self.mes_var.get():02d}/{self.ano}"

            for produto in produtos_marcados:
                nova_linha = [
                    nome_motorista, produto.get("cidade", ""), placa_cavalo,
                    produto.get("contrato", ""), produto.get("cliente", ""), produto.get("produto", ""),
                    str(produto.get("toneladas")).replace(".", ","), data_agendamento,
                    "Aguardando Agendamento", ""
                ]
                linhas_para_adicionar.append(nova_linha)
                self._abater_saldo_pedido_grande(produto)

            aba.append_rows(linhas_para_adicionar, value_input_option='USER_ENTERED')
            print(f"SUCESSO: Agendamento para {nome_motorista} adicionado e saldo abatido.")
        except Exception as e:
            messagebox.showwarning("Aviso de Agendamento", f"Ocorreu um erro ao registrar o agendamento na nuvem:\n\n{e}")

    def _thread_carregar_agendamentos(self):
        """[THREAD SECUNDÁRIA] Conecta e busca os dados da planilha. Parte demorada."""
        try:
            aba = self._conectar_google_sheets("Agendamentos")
            if aba:
                registros = aba.get_all_records()
                if not self.is_closing:
                    self.ui_queue.put((self._atualizar_treeview_agendamentos, (registros,)))
        except Exception as e:
            traceback.print_exc()
            if not self.is_closing:
                msg = f"Não foi possível carregar os agendamentos da nuvem:\n\n{e}"
                self.ui_queue.put((messagebox.showerror, ("Erro ao Carregar", msg)))

    def _atualizar_treeview_agendamentos(self, registros):
        """[THREAD PRINCIPAL] Limpa e preenche a tabela (Treeview). Parte rápida."""
        for i in self.tree_agendamentos.get_children():
            self.tree_agendamentos.delete(i)

        viagens = {}
        for reg in registros:
            motorista = str(reg.get('Motorista', '') or '').strip()
            placa = str(reg.get('Placa', '') or '').strip()
            data_agend = str(reg.get('Data_Agendamento', '') or '').strip()
            if not all([motorista, placa]): continue
            chave_viagem = f"{motorista}-{placa}-{data_agend}"
            if chave_viagem not in viagens:
                viagens[chave_viagem] = []
            viagens[chave_viagem].append(reg)

        for chave_viagem, produtos_da_viagem in viagens.items():
            dados_principais = produtos_da_viagem[0]
            locais = sorted(list(set(p.get('Local') for p in produtos_da_viagem if p.get('Local'))))
            pedidos = sorted(list(set(str(p.get('Pedido')) for p in produtos_da_viagem if p.get('Pedido'))))
            clientes = sorted(list(set(p.get('Cliente') for p in produtos_da_viagem if p.get('Cliente'))))

            total_toneladas = 0
            for p in produtos_da_viagem:
                ton_val = p.get('Toneladas')
                if isinstance(ton_val, (int, float)):
                    total_toneladas += float(ton_val)
                elif isinstance(ton_val, str) and ton_val.strip():
                    try: total_toneladas += float(ton_val.replace(',', '.'))
                    except ValueError: continue

            status = dados_principais.get('Status')
            locais_str = locais[0] if len(locais) == 1 else "Diversos"
            pedidos_str = ", ".join(pedidos) if len(pedidos) <= 2 else "Diversos"
            clientes_str = clientes[0] if len(clientes) == 1 else "Diversos"

            tag_cor = ''
            if status == 'Carregou': tag_cor = 'aguardando'
            elif status == 'Cancelado': tag_cor = 'cancelado'
            elif status == 'Agendado': tag_cor = 'agendado'
            elif status == 'Aguardando Agendamento': tag_cor = 'pendente'

            viagem_id = self.tree_agendamentos.insert("", tk.END, values=(
                dados_principais.get('Motorista'), locais_str, dados_principais.get('Placa'),
                pedidos_str, clientes_str, len(produtos_da_viagem),
                f"{total_toneladas:.3f}".replace('.', ','), dados_principais.get('Data_Agendamento'), status
            ), tags=(tag_cor,))

            for produto in produtos_da_viagem:
                tonelada_formatada = "0,000"
                ton_val_prod = produto.get('Toneladas')
                if isinstance(ton_val_prod, (int, float)):
                    tonelada_formatada = f"{float(ton_val_prod):.3f}".replace('.', ',')
                elif isinstance(ton_val_prod, str) and ton_val_prod.strip():
                    try: tonelada_formatada = f"{float(ton_val_prod.replace(',', '.')):.3f}".replace('.', ',')
                    except ValueError: pass

                self.tree_agendamentos.insert(viagem_id, tk.END, values=(
                    "", f"  └─ {produto.get('Local', '')}", "", produto.get('Pedido', ''),
                    produto.get('Cliente', ''), produto.get('Produto', ''),
                    tonelada_formatada, "", ""
                ), tags=('child_row',))

        self.tree_agendamentos.tag_configure('child_row', foreground='gray40')
        print(f"SUCESSO: {len(viagens)} viagens agrupadas carregadas e exibidas.")

    def carregar_agendamentos_da_planilha(self):
        """[INICIADOR] Cria e inicia a thread para carregar os agendamentos sem travar."""
        print("Iniciando carregamento de agendamentos em background...")
        threading.Thread(target=self._thread_carregar_agendamentos, daemon=True).start()

    def atualizar_status_agendamento(self):
        itens_selecionados = self.tree_agendamentos.selection()
        if not itens_selecionados:
            messagebox.showwarning("Aviso", "Por favor, selecione uma ou mais viagens na lista.")
            return

        acao_usuario = self.status_var.get()
        novo_status_para_planilha = ''
        if acao_usuario == 'Carregou': novo_status_para_planilha = 'Carregou'
        elif acao_usuario == 'Cancelado': novo_status_para_planilha = 'Cancelado'
        elif acao_usuario == 'Agendado': novo_status_para_planilha = 'Agendado'
        else: return

        viagens_para_atualizar = set()
        for item_id in itens_selecionados:
            if not self.tree_agendamentos.parent(item_id):
                valores = self.tree_agendamentos.item(item_id, "values")
                motorista, placa, data_agend = str(valores[0]).strip(), str(valores[2]).strip(), str(valores[7]).strip()
                viagens_para_atualizar.add((motorista, placa, data_agend))

        if not messagebox.askyesno("Confirmar Ação", f"Confirmar a alteração de {len(viagens_para_atualizar)} viagem(ns) para '{novo_status_para_planilha}'?"):
            return

        aba = self._conectar_google_sheets("Agendamentos")
        if aba is None: return

        try:
            todos_os_dados = aba.get_all_records()
            updates_em_lote = []
            linhas_afetadas = 0
            data_nova_ui = f"{self.agenda_dia_var.get():02d}/{self.agenda_mes_var.get():02d}/{self.ano}"

            for i, registro in enumerate(todos_os_dados):
                motorista_reg = str(registro.get('Motorista', '') or '').strip()
                placa_reg = str(registro.get('Placa', '') or '').strip()
                data_agend_reg = str(registro.get('Data_Agendamento', '') or '').strip()

                if (motorista_reg, placa_reg, data_agend_reg) in viagens_para_atualizar:
                    num_linha = i + 2
                    status_antigo = registro.get('Status')
                    data_para_salvar = data_nova_ui if novo_status_para_planilha == 'Agendado' else data_agend_reg

                    toneladas_float = 0.0
                    ton_val = registro.get('Toneladas')
                    if isinstance(ton_val, (int, float)): toneladas_float = float(ton_val)
                    elif isinstance(ton_val, str) and ton_val.strip():
                        try: toneladas_float = float(ton_val.replace(',', '.'))
                        except ValueError: pass

                    carga_info = {
                        "contrato": registro.get('Pedido'), "produto": registro.get('Produto'),
                        "toneladas": toneladas_float
                    }

                    if status_antigo in ['Agendado', 'Carregou'] and novo_status_para_planilha == 'Cancelado':
                        self._devolver_saldo_pedido_grande(carga_info)
                    elif status_antigo == 'Cancelado' and novo_status_para_planilha == 'Agendado':
                        self._abater_saldo_pedido_grande(carga_info)

                    updates_em_lote.append({
                        'range': f'H{num_linha}:J{num_linha}',
                        'values': [[
                            data_para_salvar, novo_status_para_planilha,
                            datetime.now().isoformat() if novo_status_para_planilha in ['Carregou', 'Cancelado'] else ""
                        ]]
                    })
                    linhas_afetadas += 1

            if updates_em_lote:
                aba.batch_update(updates_em_lote, value_input_option='USER_ENTERED')
                messagebox.showinfo("Sucesso", f"{linhas_afetadas} linha(s) de agendamento foram atualizadas!")

            self.carregar_agendamentos_da_planilha()
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Erro ao Atualizar", f"Ocorreu um erro ao atualizar a planilha:\n\n{e}")

    def setup_agendamento_frame(self, parent_frame):
        content_frame = ttk.Frame(parent_frame, style="App.TFrame")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        action_frame = ttk.Frame(content_frame, style="App.TFrame")
        action_frame.pack(fill=tk.X, pady=(0, 15))
        btn_reload = ttk.Button(action_frame, text="🔄 Recarregar Agendamentos", command=self.carregar_agendamentos_da_planilha, style="Outline.TButton")
        btn_reload.pack(side=tk.LEFT, ipady=5)
        btn_check_email = ttk.Button(action_frame, text="✉️ Verificar E-mails", command=lambda: threading.Thread(target=verificar_agendamentos_email, args=(self, True), daemon=True).start(), style="Outline.TButton")
        btn_check_email.pack(side=tk.LEFT, padx=10, ipady=5)
        status_update_frame = ttk.Frame(action_frame, style="App.TFrame")
        status_update_frame.pack(side=tk.RIGHT, anchor='e')

        ttk.Label(status_update_frame, text="Alterar status do item selecionado para:", style="App.TLabel").grid(row=0, column=0, columnspan=3, sticky='w', pady=(0,4))

        self.status_var = tk.StringVar(value="Carregou")
        today = datetime.today()
        # Apenas o dia fica editável, mês e ano são fixos (mês atual e ano atual)
        self.agenda_dia_var = tk.IntVar(value=today.day)
        self.agenda_mes_var = tk.IntVar(value=today.month)  # mantido para compatibilidade com outras funções
        self.agenda_ano = today.year

        # Campo de dia (Spinbox) - o usuário altera só o dia
        ttk.Label(status_update_frame, text="Dia:", style="App.TLabel").grid(row=1, column=0, sticky='e', padx=(0,4))
        self.agenda_day_spin = tk.Spinbox(status_update_frame, from_=1, to=31, width=4, textvariable=self.agenda_dia_var, justify='center', font=("Segoe UI", 10))
        self.agenda_day_spin.grid(row=1, column=1, sticky='w')

        # Mostra mês/ano atuais como informação (não editáveis)
        mes_ano_label = ttk.Label(status_update_frame, text=f"Mês/Ano: {self.agenda_mes_var.get():02d}/{self.agenda_ano}", style="App.TLabel")
        mes_ano_label.grid(row=1, column=2, sticky='w', padx=(10,0))

        # status combobox e salvar
        opcoes_status = ["Carregou", "Cancelado", "Agendado"]
        menu_status = ttk.Combobox(status_update_frame, textvariable=self.status_var, values=opcoes_status, state="readonly", font=("Segoe UI", 10))
        menu_status.grid(row=2, column=0, columnspan=2, sticky='w', pady=(8,0))
        btn_confirmar_status = ttk.Button(status_update_frame, text="Salvar", command=self.atualizar_status_agendamento, style="Accent.TButton")
        btn_confirmar_status.grid(row=2, column=2, sticky='e', padx=(10,0), pady=(8,0))

        tree_container = ttk.Frame(content_frame, style="App.TFrame")
        tree_container.pack(fill=tk.BOTH, expand=True)

        cols = ("Motorista", "Local", "Placa", "Pedidos", "Clientes", "Produto/Itens", "Total Ton.", "Data Agend.", "Status")
        self.tree_agendamentos = ttk.Treeview(tree_container, columns=cols, show="headings", style="App.Treeview")
        for col in cols: self.tree_agendamentos.heading(col, text=col)
        self.tree_agendamentos.column("Motorista", width=200, anchor='w'); self.tree_agendamentos.column("Local", width=150, anchor='w'); self.tree_agendamentos.column("Placa", width=100, anchor='center'); self.tree_agendamentos.column("Pedidos", width=120, anchor='center'); self.tree_agendamentos.column("Clientes", width=200, anchor='w'); self.tree_agendamentos.column("Produto/Itens", width=250, anchor='w'); self.tree_agendamentos.column("Total Ton.", width=80, anchor='center'); self.tree_agendamentos.column("Data Agend.", width=120, anchor='center'); self.tree_agendamentos.column("Status", width=100, anchor='center')
        self.tree_agendamentos.tag_configure('aguardando', background='#228B22', foreground='white'); self.tree_agendamentos.tag_configure('cancelado', background='#a61d1d', foreground='white'); self.tree_agendamentos.tag_configure('agendado', background='#E87500', foreground='white'); self.tree_agendamentos.tag_configure('pendente', background='#007bff', foreground='white')

        self.tree_agendamentos.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_agendamentos.bind("<MouseWheel>", lambda event, t=self.tree_agendamentos: self._on_treeview_scroll(event, t))

    def limpar_agendamentos_antigos(self, aba):
        from datetime import datetime, timedelta
        try:
            todos_os_dados = aba.get_all_records()
            linhas_para_apagar = []
            for i, agendamento in enumerate(todos_os_dados):
                timestamp_str = agendamento.get("Timestamp_Exclusao")
                status = agendamento.get("Status")
                if timestamp_str:
                    try:
                        data_marcada = datetime.fromisoformat(timestamp_str)
                        if status == 'Cancelado' and datetime.now() > data_marcada + timedelta(days=1):
                            linhas_para_apagar.append(i + 2)
                        elif status == 'Carregou' and datetime.now() > data_marcada + timedelta(days=2):
                            linhas_para_apagar.append(i + 2)
                    except ValueError: continue
            if linhas_para_apagar:
                for num_linha in sorted(linhas_para_apagar, reverse=True):
                    aba.delete_rows(num_linha)
        except Exception: pass

    def inserir_pedido_grande_na_planilha(self):
        produtos_selecionados = self._get_produtos_marcados()
        if not produtos_selecionados: messagebox.showwarning("Aviso", "Por favor, selecione um ou mais produtos para registrar."); return
        if not messagebox.askyesno("Confirmar Registro", f"Registrar {len(produtos_selecionados)} item(ns) como Pedidos Grandes?"): return
        aba = self._conectar_google_sheets("Pedidos Grandes")
        if aba is None: return
        try:
            linhas_para_adicionar = []
            for produto in produtos_selecionados:
                toneladas_solicitadas = produto.get("toneladas", 0)
                nova_linha = [
                    produto.get("contrato", "N/A"), produto.get("cliente", "N/A"),
                    produto.get("produto", ""), toneladas_solicitadas, 0, toneladas_solicitadas
                ]
                linhas_para_adicionar.append(nova_linha)
            aba.append_rows(linhas_para_adicionar, value_input_option='USER_ENTERED')
            messagebox.showinfo("Sucesso", f"{len(linhas_para_adicionar)} item(ns) de Pedido Grande registrado(s)!")
        except Exception as e:
            messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar o(s) Pedido(s) Grande(s):\n\n{e}")

    def _abater_saldo_pedido_grande(self, produto_da_carga):
        aba = self._conectar_google_sheets("Pedidos Grandes")
        if aba is None: return
        try:
            numero_pedido = produto_da_carga.get("contrato")
            nome_produto = produto_da_carga.get("produto")
            toneladas_a_abater = float(str(produto_da_carga.get("toneladas", 0)).replace(',', '.'))
            registros = aba.get_all_records()
            for i, registro in enumerate(registros):
                if str(registro.get('Pedido')) == str(numero_pedido) and registro.get('Produto') == nome_produto:
                    linha_para_atualizar = i + 2
                    saldo_antigo = float(str(registro.get('Saldo_Restante', '0')).replace(',', '.'))
                    carregado_antigo = float(str(registro.get('Total_Carregado', '0')).replace(',', '.'))
                    novo_saldo = saldo_antigo - toneladas_a_abater
                    novo_carregado = carregado_antigo + toneladas_a_abater
                    aba.update_cell(linha_para_atualizar, 5, f"{novo_carregado:.3f}".replace('.', ','))
                    aba.update_cell(linha_para_atualizar, 6, f"{novo_saldo:.3f}".replace('.', ','))
                    if novo_saldo <= 0:
                        aba.delete_rows(linha_para_atualizar)
                    return
        except Exception: pass

    def _devolver_saldo_pedido_grande(self, produto_da_carga):
        aba = self._conectar_google_sheets("Pedidos Grandes")
        if aba is None: return
        try:
            numero_pedido = produto_da_carga.get("contrato")
            nome_produto = produto_da_carga.get("produto")
            toneladas_a_devolver = float(str(produto_da_carga.get("toneladas", 0)).replace(',', '.'))
            registros = aba.get_all_records()
            for i, registro in enumerate(registros):
                if str(registro.get('Pedido')) == str(numero_pedido) and registro.get('Produto') == nome_produto:
                    linha_para_atualizar = i + 2
                    saldo_antigo = float(str(registro.get('Saldo_Restante', '0')).replace(',', '.'))
                    carregado_antigo = float(str(registro.get('Total_Carregado', '0')).replace(',', '.'))
                    novo_saldo = saldo_antigo + toneladas_a_devolver
                    novo_carregado = carregado_antigo - toneladas_a_devolver
                    aba.update_cell(linha_para_atualizar, 5, f"{novo_carregado:.3f}".replace('.', ','))
                    aba.update_cell(linha_para_atualizar, 6, f"{novo_saldo:.3f}".replace('.', ','))
                    return
        except Exception: pass

    def _thread_carregar_pedidos_grandes(self):
        """[THREAD SECUNDÁRIA] Busca os dados dos pedidos grandes."""
        try:
            aba = self._conectar_google_sheets("Pedidos Grandes")
            if aba:
                lista_de_pedidos = aba.get_all_records()
                if not self.is_closing:
                    self.ui_queue.put((self._atualizar_treeview_pedidos_grandes, (lista_de_pedidos,)))
        except Exception as e:
            if not self.is_closing:
                msg_args = ("Erro ao Carregar", f"Não foi possível carregar os Pedidos Grandes da nuvem:\n\n{e}")
                self.ui_queue.put((messagebox.showerror, msg_args))

    def _atualizar_treeview_pedidos_grandes(self, lista_de_pedidos):
        """[THREAD PRINCIPAL][CORRIGIDO] Apenas limpa e preenche a tabela existente."""
        for i in self.tree_pedidos_grandes.get_children():
            self.tree_pedidos_grandes.delete(i)

        for pedido in lista_de_pedidos:
            try:
                solicitado_str = str(pedido.get('Total_Solicitado', '0'))
                carregado_str = str(pedido.get('Total_Carregado', '0'))
                saldo_str = str(pedido.get('Saldo_Restante', '0'))

                if not solicitado_str.strip(): solicitado_str = '0'
                if not carregado_str.strip(): carregado_str = '0'
                if not saldo_str.strip(): saldo_str = '0'

                total_solicitado = f"{float(solicitado_str.replace(',', '.')):.3f}"
                total_carregado = f"{float(carregado_str.replace(',', '.')):.3f}"
                saldo_restante = f"{float(saldo_str.replace(',', '.')):.3f}"

                valores_linha = [
                    pedido.get('Pedido'), 
                    pedido.get('Cliente'), 
                    pedido.get('Produto'),
                    total_solicitado.replace('.',','), 
                    total_carregado.replace('.',','), 
                    saldo_restante.replace('.',',')
                ]
                self.tree_pedidos_grandes.insert("", tk.END, values=valores_linha)

            except (ValueError, TypeError) as e:
                print(f"Aviso: Ignorando linha de pedido grande com dados inválidos: {pedido} -> {e}")

    def carregar_pedidos_grandes(self):
        """[INICIADOR] Carrega os pedidos grandes sem travar a UI."""
        threading.Thread(target=self._thread_carregar_pedidos_grandes, daemon=True).start()

    def setup_pedidos_grandes_frame(self, parent_frame):
        content_frame = ttk.Frame(parent_frame, style="App.TFrame")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        top_frame = ttk.Frame(content_frame, style="App.TFrame")
        top_frame.pack(fill=tk.X, pady=(0, 15))
        btn_atualizar_pedidos = ttk.Button(top_frame, text="🔄 Recarregar Lista de Pedidos Grandes", command=self.carregar_pedidos_grandes, style="Accent.TButton")
        btn_atualizar_pedidos.pack(fill=tk.X, ipady=8)

        tree_frame = ttk.Frame(content_frame, style="App.TFrame")
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ('Pedido', 'Cliente', 'Produto', 'Total Solicitado', 'Total Carregado', 'Saldo Restante')
        self.tree_pedidos_grandes = ttk.Treeview(tree_frame, columns=cols, show="headings", style="App.Treeview")
        for col in cols: self.tree_pedidos_grandes.heading(col, text=col); self.tree_pedidos_grandes.column(col, width=160, anchor='center')
        self.tree_pedidos_grandes.column('Cliente', width=250, anchor='w'); self.tree_pedidos_grandes.column('Produto', width=250, anchor='w')

        self.tree_pedidos_grandes.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_pedidos_grandes.bind("<MouseWheel>", lambda event, t=self.tree_pedidos_grandes: self._on_treeview_scroll(event, t))

    def _compactar_planilha(self, aba):
        try:
            todos_os_dados = aba.get_all_values()
            if not todos_os_dados: return
            cabecalho = todos_os_dados[0]
            dados_sem_cabecalho = todos_os_dados[1:]
            dados_filtrados = [linha for linha in dados_sem_cabecalho if any(str(celula).strip() for celula in linha)]
            if len(dados_filtrados) < len(dados_sem_cabecalho):
                aba.clear()
                aba.update(range_name='A1', values=[cabecalho] + dados_filtrados, value_input_option='USER_ENTERED')
        except Exception: pass

    def atualizar_agendamento_pela_placa(self, placa, nova_data):
        aba = self._conectar_google_sheets("Agendamentos")
        if aba is None: return False
        try:
            celulas_encontradas = aba.findall(placa, in_column=3)
            if not celulas_encontradas: return False

            for celula in celulas_encontradas:
                linha = celula.row
                status_atual = aba.cell(linha, 9).value 

                if status_atual == "Aguardando Agendamento":
                    aba.update_cell(linha, 8, nova_data)     
                    aba.update_cell(linha, 9, "Agendado") 
                    return True
            return False
        except Exception as e:
            print(f"ERRO CRÍTICO ao atualizar planilha para placa {placa}: {e}")
            traceback.print_exc()
            return False

