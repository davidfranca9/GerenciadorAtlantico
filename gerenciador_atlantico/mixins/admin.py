from ..shared import *
from ..servicos.bsoft_api import *
from ..servicos.comunicacao import *
from ..servicos.documentos import *
from ..servicos.ocr import *
from ..servicos.relatorios import *
from ..servicos.startup import *

class AdminMixin:
    def verificar_lock_remoto(self):
        """
        [VERSÃO FINAL E SEGURA] Verifica o status do lock e se re-agenda
        de forma segura sem a necessidade de múltiplas threads.
        """
        # Define a função de trabalho que será executada em uma thread separada.
        def worker():
            try:
                # Bypass do admin (comente para testar, descomente para usar)
                if self._get_mac_address() == ADMIN_MAC_ADDRESS:
                     print("Máquina Admin detectada. Verificação de bloqueio ignorada.")
                     return

                # Conecta e lê a planilha
                aba = self._conectar_google_sheets("Config")
                if aba:
                    lock_status = aba.acell('A1').value
                    print(f"Verificação de status: '{lock_status}' encontrado na planilha.")

                    # Decide se bloqueia ou desbloqueia a tela usando a fila da UI
                    if lock_status == "LOCK":
                        if not (self.lock_shield and self.lock_shield.winfo_exists()):
                            self.ui_queue.put((self._show_lock_overlay, ()))
                    else: # Se for 'UNLOCK' ou qualquer outra coisa
                        if self.lock_shield and self.lock_shield.winfo_exists():
                            self.ui_queue.put((self._hide_lock_overlay, ()))

            except Exception as e:
                print(f"ERRO no loop de verificação de bloqueio: {e}")

        # Inicia a verificação em uma thread para não travar a interface
        threading.Thread(target=worker, daemon=True).start()

        # Agenda a PRÓXIMA chamada a esta mesma função de forma segura
        if not self.is_closing:
            # Tempo em milissegundos (30000 = 30 segundos)
            self.root.after(30000, self.verificar_lock_remoto)

    def toggle_system_lock(self, show_message=True):
        """Verifica o status na nuvem e age (trava ou destrava)."""
        # if self._get_mac_address() == ADMIN_MAC_ADDRESS:
        #     print("Máquina Admin detectada. Bloqueio ignorado.")
        #     return

        aba = self._conectar_google_sheets("Config")
        if not aba:
            return

        try:
            lock_status = aba.acell('A1').value
            if lock_status == "LOCK":
                if not self.lock_overlay:
                    self.ui_queue.put((self._show_lock_overlay, ()))
            else: 
                if self.lock_overlay:
                    self.ui_queue.put((self._hide_lock_overlay, ()))
        except Exception as e:
            print(f"Erro ao verificar o lock: {e}")

    def _show_lock_overlay(self):
        """[VERSÃO 3.0 - COMPLETA] Cria e ativa o 'escudo' sobre as abas."""
        # Se o escudo já existe na tela, não faz nada.
        if self.lock_shield and self.lock_shield.winfo_exists():
            return

        print("Ação: ATIVANDO bloqueio visual...")

        # 1. Cria o frame do escudo
        self.lock_shield = tk.Frame(self.root, bg="#012623")

        # 2. Cria os textos e botões DENTRO do escudo
        tk.Label(self.lock_shield, text="SISTEMA BLOQUEADO", font=("Arial", 22, "bold"), bg="#012623", fg="#DC3545").pack(pady=(150, 20), padx=20)
        tk.Label(self.lock_shield, text="O acesso foi restringido pelo administrador.", font=("Arial", 12), bg="#012623", fg="white").pack(pady=5, padx=20)
        tk.Button(self.lock_shield, text="Digitar Senha de Liberação", command=self._ask_for_override_password, font=("Arial", 10, "bold"), bg="#FFC107", fg="#012623").pack(pady=20)

        # 3. Posiciona o escudo sobre as abas para bloqueá-las
        self.lock_shield.place(in_=self.notebook, relx=0, rely=0, relwidth=1, relheight=1)

    def _ask_for_override_password(self):
        """Cria uma pequena janela de diálogo para o usuário digitar a senha."""
        # Cria a janela de diálogo
        self.password_dialog = Toplevel(self.root)
        self.password_dialog.title("Senha de Liberação")
        self.password_dialog.geometry("300x150")
        self.password_dialog.configure(bg="#012623")

        # Centraliza na janela principal
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 150
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 75
        self.password_dialog.geometry(f"+{x}+{y}")

        # Garante que esta janela fique na frente e capture o foco
        self.password_dialog.transient(self.root)
        self.password_dialog.grab_set()

        Label(self.password_dialog, text="Digite a senha mestra:", font=("Arial", 11), bg="#012623", fg="white").pack(pady=10)

        self.lock_password_entry = tk.Entry(self.password_dialog, font=("Arial", 12), show='*')
        self.lock_password_entry.pack(pady=5, padx=20, fill='x')
        self.lock_password_entry.focus_set()
        self.lock_password_entry.bind("<Return>", lambda event: self._check_override_password())
        # O botão OK agora chama a mesma função de verificação de antes
        unlock_button = tk.Button(self.password_dialog, text="Desbloquear", command=self._check_override_password,
                                  font=("Arial", 10, "bold"), bg="#28A745", fg="white")
        unlock_button.pack(pady=10)

        self.lock_error_label = Label(self.password_dialog, text="", font=("Arial", 10, "bold"), bg="#012623", fg="yellow")
        self.lock_error_label.pack(pady=5)

    def _hide_lock_overlay(self):
        """[VERSÃO 3.0 - COMPLETA] Destrói o 'escudo' de bloqueio para liberar a tela."""
        # Se o escudo existir, destrói ele e limpa a variável
        if self.lock_shield and self.lock_shield.winfo_exists():
            print("Ação: DESATIVANDO bloqueio visual...")
            self.lock_shield.destroy()
            self.lock_shield = None

    def _check_override_password(self):
        """[INICIADOR] Pega a senha digitada e inicia a verificação em background."""
        entered_password = self.lock_password_entry.get()
        if not entered_password: return
        self.lock_password_entry.config(state="disabled")
        threading.Thread(target=self._worker_verificar_senha, args=(entered_password,), daemon=True).start()

    def _worker_verificar_senha(self, entered_password):
        """
        [VERSÃO FINAL] Verifica senhas e garante que a janela de diálogo seja fechada em todos os casos.
        """

        def close_dialog():
            if hasattr(self, 'password_dialog') and self.password_dialog.winfo_exists():
                self.password_dialog.destroy()

        # Verifica a senha de bypass do Administrador
        if entered_password == ADMIN_OVERRIDE_PASSWORD and self._get_mac_address() == ADMIN_MAC_ADDRESS:
            print("Senha de Administrador correta. Desbloqueio imediato.")
            self.ui_queue.put((messagebox.showinfo, ("Acesso Permitido", "Acesso de Administrador concedido.")))
            self.ui_queue.put((self._hide_lock_overlay, ()))
            self.ui_queue.put((lambda: self.notebook.select(self.frame_admin), ()))
            self.ui_queue.put(close_dialog) # Garante que a janela feche
            return

        # Verifica a senha da planilha
        aba = self._conectar_google_sheets("Config")
        if not aba:
            self.ui_queue.put((messagebox.showerror, ("Erro de Conexão", "Não foi possível conectar à planilha 'Config'.")))
            self.ui_queue.put(close_dialog) # Garante que a janela feche
            return
        try:
            senha_correta_planilha = aba.acell('B1').value
            if entered_password == senha_correta_planilha:
                aba.update_acell('A1', 'UNLOCK')
                self.ui_queue.put((messagebox.showinfo, ("Sucesso", "Sistema desbloqueado para todos!"),))
                self.ui_queue.put(close_dialog) # Garante que a janela feche
            else:
                # Se a senha estiver incorreta, reabilita o campo de entrada
                self.ui_queue.put((lambda: self.lock_error_label.config(text="Senha incorreta!"),))
                self.ui_queue.put((lambda: self.lock_password_entry.config(state="normal"),))
                self.ui_queue.put((lambda: self.lock_password_entry.delete(0, tk.END),))
        except Exception as e:
            self.ui_queue.put((messagebox.showerror, ("Erro", f"Não foi possível verificar a senha:\n\n{e}")))
            self.ui_queue.put(close_dialog) # Garante que a janela feche

    def setup_admin_frame(self):
        """Cria a interface da aba de Administração."""
        admin_frame = tk.Frame(self.frame_admin, bg="#012623")
        admin_frame.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)
        tk.Label(admin_frame, text="Controle Remoto do Sistema", font=("Arial", 14, "bold"), bg="#012623", fg="#DC3545").pack(pady=10)
        self.lock_button = tk.Button(admin_frame, text="Bloquear / Desbloquear Sistema", command=self._admin_toggle_lock_status,
                                     font=("Arial", 12, "bold"), bg="#FFC107", fg="#012623", width=40, height=2)
        self.lock_button.pack(pady=10)
        ttk.Separator(admin_frame, orient='horizontal').pack(fill='x', pady=20)
        tk.Label(admin_frame, text="Alterar Senha Mestra de Desbloqueio", font=("Arial", 14, "bold"), bg="#012623", fg="#04D9C4").pack(pady=10)
        Label(admin_frame, text="Nova Senha:", font=("Arial", 11), bg="#012623", fg="white").pack()
        self.admin_new_password_entry = tk.Entry(admin_frame, font=("Arial", 12), width=30)
        self.admin_new_password_entry.pack(pady=5)
        btn_save_pass = tk.Button(admin_frame, text="Salvar Nova Senha na Nuvem", command=self._handle_salvar_nova_senha, font=("Arial", 10, "bold"), bg="#007BFF", fg="white")
        btn_save_pass.pack(pady=10)

    def _admin_toggle_lock_status(self):
        """[INICIADOR] Inicia uma thread para alterar o status de bloqueio na planilha."""
        self.lock_button.config(state="disabled", text="Aguarde...")
        threading.Thread(target=self._worker_toggle_lock, daemon=True).start()

    def _worker_toggle_lock(self):
        """[THREAD SECUNDÁRIA] Conecta na planilha, lê o status, inverte e salva."""
        aba = self._conectar_google_sheets("Config")
        if not aba:
            self.ui_queue.put((messagebox.showerror, ("Erro de Conexão", "Não foi possível conectar à planilha 'Config'.")))
            self.ui_queue.put((lambda: self.lock_button.config(state='normal', text='Tentar Novamente'), ()))
            return
        try:
            current_status = aba.acell('A1').value
            new_status = "UNLOCK" if current_status == "LOCK" else "LOCK"

            aba.update_acell('A1', new_status)

            msg_args = ("Sucesso", f"O sistema foi alterado para: {new_status}")

            if new_status == "LOCK": 
                btn_config = {'text': 'Sistema BLOQUEADO (Clique para Desbloquear)', 'bg': '#DC3545', 'state': 'normal'}
            else: 
                btn_config = {'text': 'Sistema DESBLOQUEADO (Clique para Bloquear)', 'bg': '#28A745', 'state': 'normal'}

            config_task = lambda: self.lock_button.config(**btn_config)

            self.ui_queue.put((messagebox.showinfo, msg_args))
            self.ui_queue.put((config_task, ()))

        except Exception as e:
            self.ui_queue.put((messagebox.showerror, ("Erro", f"Não foi possível alterar o status:\n\n{e}")))
            self.ui_queue.put((lambda: self.lock_button.config(state='normal', text='Tentar Novamente'), ()))

    def _handle_salvar_nova_senha(self):
        """[INICIADOR] Inicia o processo de salvar a nova senha mestra."""
        nova_senha = self.admin_new_password_entry.get()
        if not nova_senha or len(nova_senha) < 6:
            messagebox.showwarning("Senha Inválida", "A nova senha deve ter pelo menos 6 caracteres.")
            return

        if messagebox.askyesno("Confirmar", "Tem a certeza que deseja alterar a senha mestra do sistema?"):
            threading.Thread(target=self._worker_salvar_nova_senha, args=(nova_senha,), daemon=True).start()

    def _worker_salvar_nova_senha(self, nova_senha):
        """[THREAD SECUNDÁRIA] Salva a nova senha na planilha."""
        print(f"A alterar a senha mestra para: {nova_senha}")
        aba = self._conectar_google_sheets("Config")
        if aba:
            try:
                aba.update_acell('B1', nova_senha)
                self.ui_queue.put((messagebox.showinfo, ("Sucesso", "Senha mestra alterada com sucesso!")))
                self.ui_queue.put((self.admin_new_password_entry.delete, (0, tk.END)))
            except Exception as e:
                self.ui_queue.put((messagebox.showerror, ("Erro", f"Não foi possível salvar a nova senha:\n\n{e}")))

