from ..shared import *

def send_email_message(destinatarios, assunto, corpo, anexos=None):
    anexos = anexos or []
    msg = MIMEMultipart()
    msg["From"] = EMAIL_REMETENTE
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo, "html"))

    for caminho_arquivo in anexos:
        if not os.path.exists(caminho_arquivo):
            continue
        ctype, encoding = mimetypes.guess_type(caminho_arquivo)
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        with open(caminho_arquivo, "rb") as attachment:
            part = MIMEBase(maintype, subtype)
            part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=os.path.basename(caminho_arquivo))
        msg.attach(part)

    server = smtplib.SMTP("smtp.gmail.com", 587)
    try:
        server.starttls()
        server.login(EMAIL_REMETENTE, SENHA_APP_EMAIL)
        server.sendmail(EMAIL_REMETENTE, destinatarios, msg.as_string())
    finally:
        server.quit()

    return True

def verificar_agendamentos_email(app_instance, is_manual=False):
    """Verifica e-mails de confirmação de agendamento e atualiza a planilha."""
    meses = {
        'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6,
        'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12
    }
    
    try:
        mb = MailBox(EMAIL_IMAP_SERVER)
        mb.login(EMAIL_REMETENTE, SENHA_APP_EMAIL_LEITURA, initial_folder='INBOX')

        emails_encontrados = mb.fetch(A('UNSEEN', from_=EMAIL_FABRICA), reverse=True)
        
        atualizacoes_feitas = 0
        ano_atual = datetime.now().year

        for msg in emails_encontrados:
            if app_instance.is_closing: break
            
            placa, data_agendada = None, None
            
            match_placa = re.search(r"Placa\s+([A-Z0-9]{7})", msg.subject, re.IGNORECASE)
            if not match_placa:
                match_placa = re.search(r"([A-Z0-9]{7})\s*$", msg.subject.strip())
            
            if match_placa:
                placa = match_placa.group(1).strip().upper()

            corpo_email = msg.text or msg.html
            match_data = re.search(r"(\d{1,2})/([a-z]{3})", corpo_email, re.IGNORECASE)
            
            if match_data:
                dia, mes_abbr = match_data.group(1), match_data.group(2).lower()
                if mes_abbr in meses:
                    num_mes = meses[mes_abbr]
                    data_agendada = f"{dia.zfill(2)}/{num_mes:02d}/{ano_atual}"

            if placa and data_agendada:
                if app_instance.atualizar_agendamento_pela_placa(placa, data_agendada):
                    atualizacoes_feitas += 1
        
        mb.logout()
        
        if app_instance.is_closing: return

        if atualizacoes_feitas > 0:
            print(f"VERIFICAÇÃO DE E-MAIL: {atualizacoes_feitas} agendamentos atualizados.")
            # CORREÇÃO: Passa uma tupla vazia como argumento
            app_instance.ui_queue.put((app_instance.carregar_agendamentos_da_planilha, ()))
            if is_manual:
                # CORREÇÃO: Agrupa os argumentos do messagebox em uma tupla
                msg_args = ("E-mails Verificados", f"{atualizacoes_feitas} novo(s) agendamento(s) encontrado(s) e atualizado(s)!")
                app_instance.ui_queue.put((messagebox.showinfo, msg_args))
        else:
            print("VERIFICAÇÃO DE E-MAIL: Nenhuma novidade.")
            if is_manual:
                # CORREÇÃO: Agrupa os argumentos do messagebox em uma tupla
                msg_args = ("E-mails Verificados", "Nenhum novo agendamento encontrado.")
                app_instance.ui_queue.put((messagebox.showinfo, msg_args))

    except Exception as e:
        print(f"ERRO AO LER E-MAILS: {e}")
        if is_manual and not app_instance.is_closing:
            # CORREÇÃO: Agrupa os argumentos do messagebox em uma tupla
            error_args = ("Erro ao Ler E-mails", f"Ocorreu um erro ao verificar os e-mails:\n\n{e}")
            app_instance.ui_queue.put((messagebox.showerror, error_args))

def _enviar_email(destinatarios, assunto, corpo, anexos=[]):
    try:
        messagebox.showinfo("Enviando...", "Preparando para enviar o e-mail. Por favor, aguarde.")
        send_email_message(destinatarios, assunto, corpo, anexos)
        messagebox.showinfo("Sucesso!", f"E-mail enviado com sucesso para {destinatarios}!")
        return True
    except smtplib.SMTPAuthenticationError:
        messagebox.showerror("Erro de Autenticação", "Não foi possível fazer login. Verifique se o e-mail e a 'Senha de App' estão corretos.")
        return False
    except Exception as e:
        messagebox.showerror("Erro de Envio", f"Ocorreu um erro inesperado ao enviar o e-mail:\n\n{e}")
        return False
