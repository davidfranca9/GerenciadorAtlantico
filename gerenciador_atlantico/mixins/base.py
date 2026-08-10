from ..shared import *
from ..servicos.bsoft_api import *
from ..servicos.comunicacao import *
from ..servicos.documentos import *
from ..servicos.ocr import *
from ..servicos.relatorios import *
from ..servicos.startup import *

class BaseAppMixin:
    def __init__(self, root, lista_cidades):
        self.root = root
        self.is_closing = False
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- DADOS E VARIÁVEIS DE ESTADO ---
        self.cidades_por_uf = carregar_cidades_nova_logica(PLANILHA_CIDADES)
        self.lista_cidades = lista_cidades
        self.ui_queue = queue.Queue()
        self.produtos = []
        self.supplier_var = tk.StringVar(value="Fertimaxi")
        self.nav_buttons = {}
        self.frames = {}
        self.lock_shield = None # Garante que a variável de bloqueio exista
        today = datetime.today()
        self.ano = today.year


        # ==============================================================================
        # ### INÍCIO DO BLOCO DE VARIÁVEIS DA BUONNY - COLE ISTO AQUI ###
        # ==============================================================================
        self.carga_tipo_map = {
            'AÇO': '32', 'AÇUCAR': '18', 'AÇÚCAR': '102', 'ALGODÃO': '44', 'ALGODÃO EM PLUMA': '20', 'ALUMÍNIO': '4', 'AMIDO': '65', 'ARROZ': '8',
            'AUTOPEÇAS': '45', 'AVEIA': '70', 'BACIAS': '63', 'BEBIDAS': '5', 'BICABORNATO DE SÓDIO': '29', 'BOBINAS': '19', 'BOBINAS DE AÇO': '11',
            'CAFÉ': '14', 'CALCÁRIO': '73', 'CALCÍTICO': '72', 'CANOLA': '64', 'CARGA FRACIONADA': '41', 'CARGAS DIVERSAS': '67', 'CEVADA': '76',
            'CHAPAS DE AÇO': '22', 'CHAPAS DE MDF': '37', 'CIGARROS': '12', 'CIMENTO': '39', 'COBRE': '7', 'CONCENTRADO APATÍTICO ÚMIDO': '103',
            'COPOLÍMERO': '52', 'COURO': '43', 'DEFENSIVOS AGRÍCOLAS': '71', 'DIVERSOS': '3', 'DORMENTE': '53', 'DTI DIÓXIDO DE TITANIO': '54',
            'ELETRO/ELETRÔNICOS': '6', 'FARELO': '62', 'FERRO': '33', 'FERTILIZANTE UREIA': '97', 'FERTILIZANTES CLORETO DE POTÁSSIO': '100',
            'FERTILIZANTES E ADUBOS': '77', 'FERTILIZANTES PREMIUM YARA': '95', 'FERTILIZANTES TIPO MAP': '98',
            'FERTILIZANTES TIPO TSP/SUPERFOSFATO/FOSFATO': '99', 'FOSFATO': '74', 'GESSO AGRÍCOLA': '106', 'LAMINADOS': '38', 'LEITE': '21',
            'MAGNETITA': '107', 'MÁQUINAS EM GERAL': '28', 'MEDICAMENTOS': '13', 'MILHO': '75', 'NIQUEL': '55', 'ÓLEO DE SOJA': '24',
            'OUTROS': '42', 'PAPEL': '10', 'PLACAS FOTOVOLTAICAS': '60', 'PNEUS': '46', 'POLIETILENO': '26', 'POLIPROPILENO': '56',
            'PROD. ALIMENTÍCIOS': '15', 'PROD. FRIGORÍFICOS': '16', 'PROD. QUÍMICOS': '17', 'PRODUTOS AGRÍCOLAS': '31',
            'PRODUTOS DE HIGIENE E LIMPEZA': '34', 'PRODUTOS SIDERÚRGICOS': '23', 'PVC': '59', 'RAÇÃO': '50',
            'RAÇÃO ANIMAL': '47', 'REFRATÁRIOS': '57', 'ROCHAS FOSFÁTICAS, OUTRAS ROCHAS E SOLOS': '104', 'SAIBROS, BRITAS E AREIA EM GERAL': '105',
            'SAL': '68', 'SEMENTES': '25', 'SEMENTES EM GERAL': '94', 'SOJA': '9', 'SOJA/SEMENTE DE SOJA/FARELO': '101', 'TECIDOS': '35',
            'TELA': '66', 'TINTAS': '40', 'TIPO DE CARGA 1': '1', 'TIPO DE CARGA 2': '2', 'TRIGO': '30', 'TRIGO EM GRÃOS/SEMENTES/FARELO': '96',
            'TUBOS E CONEXÕES': '49', 'UREIA': '69', 'VASILHAME DE VIDRO': '58', 'VERGALHÃO': '27', 'VIDRO': '36', 'ZINCO': '61'
        }
        self.carga_valor_map = {
            'De R$ 0,01 a R$ 100.000,00': '1', 'De R$ 100.001,00 a R$ 200.000,00': '2', 'De R$ 200.001,00 a R$ 300.000,00': '3',
            'De R$ 300.001,00 a R$ 400.000,00': '4', 'De R$ 400.001,00 a R$ 500.000,00': '5', 'De R$ 500.001,00 a R$ 800.000,00': '6',
            'De R$ 800.001,00 a R$ 1.000.000,00': '7', 'De R$ 1.000.001,00 a R$ 3.000.000,00': '8', 'De R$ 3.000.001,00 a R$ 1.000.000.000,00': '9'
        }

        # --- Variáveis para Aba 1 (Consulta Rápida) ---
        self.c_origem_cidade_id = None; self.c_destino_cidade_id = None
        self.c_produto_var = tk.StringVar(value="BUONNY CHECK")
        self.c_codigo_var = tk.StringVar(value="83406")
        self.c_razao_social_var = tk.StringVar(value="ATLANTICO FERTLOG TRASPORTES E SERVICOS DE CARGAS LTD")
        self.c_transportador_var = tk.StringVar(value="08.187.322/0001-01 - ATLANTICO FERTLOG TRASPORTES E SERVICOS DE CARGAS LTDA")
        self.c_cpf_var = tk.StringVar(); self.c_nome_var = tk.StringVar()
        self.c_placa_veiculo_var = tk.StringVar(); self.c_placa_carreta_var = tk.StringVar()
        self.c_carga_tipo_var = tk.StringVar(value="PRODUTOS AGRÍCOLAS")
        self.c_carga_valor_var = tk.StringVar()
        self.c_origem_cidade_var = tk.StringVar(); self.c_origem_estado_var = tk.StringVar(); self.c_origem_pais_var = tk.StringVar()
        self.c_destino_cidade_var = tk.StringVar(); self.c_destino_estado_var = tk.StringVar(); self.c_destino_pais_var = tk.StringVar()

        # --- Variáveis para Aba 2 (Cadastro) ---
        self.cad_vars = {k: tk.StringVar() for k in [
            'produto', 'embarcador', 'transportador', 'contato_nome_1', 'contato_tipo_1', 'contato_dados_1',
            'contato_nome_2', 'contato_tipo_2', 'contato_dados_2', 'categoria_prof', 'cpf', 'nome', 'celular_prof',
            'nome_mae', 'nome_pai', 'rg_numero', 'rg_uf', 'natural_pais', 'natural_estado', 'natural_cidade',
            'data_nasc', 'cep', 'endereco', 'end_numero', 'end_compl', 'end_cidade', 'end_estado', 'cnh_numero',
            'cnh_categoria', 'cnh_venc', 'cnh_uf', 'cnh_data_primeira', 'cnh_cod_seg', 'veic_placa', 'veic_chassi',
            'veic_renavam', 'prop_doc', 'prop_nome', 'vitima_roubo', 'sofreu_acidente', 'tempo_transportou', 'possui_rastreamento'
        ]}
        self.cad_vars['produto'].set("BUONNYCHECK ST")
        self.cad_vars['transportador'].set("08.187.322/0001-01 - ATLANTICO FERTLOG TRASPORTES E SERVICOS DE CARGAS LTDA")
        self.cad_vars['contato_nome_1'].set("ATLANTICO FERTLOG")
        self.cad_vars['contato_tipo_1'].set("E-MAIL")
        self.cad_vars['contato_dados_1'].set("atlanticofertlog.comercial@gmail.com")
        self.cad_vars['contato_nome_2'].set("CLAUS")
        self.cad_vars['contato_tipo_2'].set("TELEFONE")
        self.cad_vars['contato_dados_2'].set("(71) 99278-5090")

        # --- INÍCIO DA INTEGRAÇÃO BUONNY (Sessão e Headers) ---
        self.buonny_session = requests.Session()
        self.buonny_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://informacoes.buonny.com.br',
            'Referer': 'https://informacoes.buonny.com.br/informacoes2/consulta/consultar',
        }
        self.buonny_session.headers.update(self.buonny_headers)
        self.buonny_is_logged_in = False
        # ==============================================================================
        # ### FIM DO BLOCO DE VARIÁVEIS DA BUONNY ###
        # ==============================================================================

        # --- ESTRUTURA PRINCIPAL DA UI ---
        nav_bar = ttk.Frame(root, style="NavBar.TFrame")
        nav_bar.pack(fill=tk.X, padx=10, pady=(10, 0))

        container = ttk.Frame(root, style="App.TFrame")
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        # --- MONTAGEM DA BARRA DE NAVEGAÇÃO ---
        try:
            img = Image.open(LOGO_APP_PATH)
            img = img.resize((40, 40), Image.Resampling.LANCZOS)
            self.logo_photo = ImageTk.PhotoImage(img)
            logo_label = ttk.Label(nav_bar, image=self.logo_photo, style="NavBar.TLabel")
            logo_label.pack(side=tk.LEFT, padx=(10, 5), pady=5)
        except Exception as e:
            print(f"Erro ao carregar o logo: {e}")

        ttk.Label(nav_bar, text="ATLÂNTICO FERTLOG", style="NavBar.TLabel").pack(side=tk.LEFT, padx=(0, 20))

        # --- CRIAÇÃO DAS PÁGINAS E BOTÕES ---
        PAGES = [
            ("🛡️ BUONNY", "BUONNY"),
            ("📄 CONTRATO", "CONTRATO"),
            ("🚚 ORDEM DE COLETA", "ORDEM DE COLETA"),
            ("💵 CARTA FRETE", "CARTA FRETE"),
            ("📅 AGENDAMENTOS", "AGENDAMENTOS"),
            ("📦 PEDIDOS GRANDES", "PEDIDOS GRANDES"), # Adicionado para clareza
            ("☁️ BSOFT TMS", "BSOFT TMS"),
            ("📊 ANÁLISE DE FRETES", "ANÁLISE DE FRETES")
        ]

        if self._get_mac_address() == ADMIN_MAC_ADDRESS:
            PAGES.append(("⚙️ ADMIN", "ADMIN"))

        for text, page_name in PAGES:
            frame = ttk.Frame(container, style="App.TFrame")
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

            button = ttk.Button(nav_bar, text=text, style="Nav.TButton",
                                command=lambda f=page_name: self.show_frame(f))
            button.pack(side=tk.LEFT, fill=tk.Y, padx=1)
            self.nav_buttons[page_name] = button

        # --- SETUP DO CONTEÚDO DE TODAS AS PÁGINAS (CORRIGIDO) ---
        self.setup_buonny_frame(self.frames["BUONNY"])
        self.setup_contrato_frame(self.frames["CONTRATO"], today)
        self.setup_oc_frame(self.frames["ORDEM DE COLETA"])
        self.setup_carta_frete_frame(self.frames["CARTA FRETE"])
        self.setup_agendamento_frame(self.frames["AGENDAMENTOS"])
        self.setup_pedidos_grandes_frame(self.frames["PEDIDOS GRANDES"]) # Chamada adicionada
        self.setup_bsoft_frame(self.frames["BSOFT TMS"])
        self.setup_geu_frame(self.frames["ANÁLISE DE FRETES"])
        if self._get_mac_address() == ADMIN_MAC_ADDRESS:
            self.setup_admin_frame(self.frames["ADMIN"]) # Garante que a página de admin também seja criada

        # --- INICIALIZAÇÃO DA APLICAÇÃO ---

        self.show_frame("BUONNY")
        self._process_ui_queue()




        # Carrega dados após a UI estar completamente montada
        print("Iniciando carregamento automático dos dados...")
        self.carregar_agendamentos_da_planilha()
        self.carregar_pedidos_grandes() # Esta chamada agora é segura
        print("Carregamento inicial concluído.")
        self.iniciar_verificacao_email_background()
        self.verificar_lock_remoto()

    def _get_mac_address(self):
        """Retorna o endereço MAC da máquina atual."""
        try:
            mac = ':'.join(re.findall('..', '%012x' % uuid.getnode())) 
            return mac.upper()
        except Exception:
            return None

    def show_frame(self, page_name):
        """Mostra uma página e atualiza o estilo do botão de navegação."""
        frame = self.frames[page_name]
        frame.tkraise()

        # Atualiza os estilos dos botões
        for name, button in self.nav_buttons.items():
            if name == page_name:
                button.config(style="ActiveNav.TButton")
            else:
                button.config(style="Nav.TButton")    

    def on_closing(self):
        print("Sinal de fechamento recebido. Encerrando threads...")
        self.is_closing = True
        self.root.destroy()

    def _process_ui_queue(self):
        try:
            task, args = self.ui_queue.get_nowait()
            task(*args)
        except queue.Empty:
            pass
        finally:
            if not self.is_closing:
                self.root.after(100, self._process_ui_queue)

    def _loop_verificar_emails(self):
        """[THREAD SECUNDÁRIA] Loop que verifica e-mails a cada 5 minutos."""
        print("Thread de verificação de e-mail iniciada em background.")
        while not self.is_closing:
            try:
                verificar_agendamentos_email(self)
            except Exception as e:
                print(f"Erro no loop de verificação de e-mail: {e}")

            for _ in range(300):
                if self.is_closing: break
                time.sleep(1)

    def iniciar_verificacao_email_background(self):
        """[INICIADOR] Cria e inicia a thread para verificação de e-mail."""
        email_thread = threading.Thread(target=self._loop_verificar_emails, daemon=True)
        email_thread.start()

    def setup_header(self):
        """Cria o cabeçalho com o logo."""
        try:
            img = Image.open(LOGO_APP_PATH)
            img = img.resize((200, 45), Image.Resampling.LANCZOS)
            self.logo_photo = ImageTk.PhotoImage(img)
            logo_label = ttk.Label(self.header_frame, image=self.logo_photo, style="Header.TLabel")
            logo_label.pack(side=tk.LEFT, padx=10, pady=5)
        except Exception as e:
            print(f"Erro ao carregar logo: {e}")
            fallback_label = ttk.Label(self.header_frame, text="Atlântico Fertlog", style="Header.Title.TLabel")
            fallback_label.pack(side=tk.LEFT, padx=10, pady=5)

    def carregar_logo(self, caminho, max_w=260, max_h=100):
        if os.path.exists(caminho):
            image = Image.open(caminho); w, h = image.size; ratio = min(max_w / w, max_h / h)
            image = image.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)
            self.logo_image = ImageTk.PhotoImage(image); self.logo_label.config(image=self.logo_image)

    def _on_mousewheel(self, event, canvas):
        """
        [NOVO] Manipula o evento da roda do mouse para rolar o canvas verticalmente.
        """
        # A direção da rolagem é invertida em relação ao 'delta' do evento
        # A divisão por 120 normaliza o valor do delta no Windows
        canvas.yview_scroll(-1 * int(event.delta / 120), "units")

    def _bind_mousewheel_recursive(self, widget, canvas):
        """
        [NOVO] Vincula o evento de rolagem do mouse a um widget e a todos os seus filhos.
        """
        widget.bind("<MouseWheel>", lambda event, c=canvas: self._on_mousewheel(event, c))
        for child in widget.winfo_children():
            self._bind_mousewheel_recursive(child, canvas)

