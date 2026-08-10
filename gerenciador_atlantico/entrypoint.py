from .aplicacao import PDFInserterApp
from .servicos.ocr import carregar_cidades_nova_logica
from .servicos.startup import rotina_de_inicializacao
from .shared import *


def main():
    global root
    from datetime import timedelta

    CIDADES_VALIDAS = carregar_cidades_nova_logica(PLANILHA_CIDADES)
    if not CIDADES_VALIDAS:
        messagebox.showwarning("Aviso", "A lista de cidades n?o foi carregada.")

    configurar_dpi_windows()
    root = tk.Tk()
    ajustar_escala_tk(root)
    root.geometry("1200x800")
    root.minsize(1100, 750)
    root.title("Atl?ntico Fertlog - Gerenciador de Cargas")
    root.configure(bg=BG_COLOR)

    style = ttk.Style(root)
    style.theme_use("clam")

    NAV_BAR_COLOR = "#20C4B4"
    NAV_BUTTON_ACTIVE_COLOR = "#1A9A8D"

    style.configure(".", background=BG_COLOR, foreground=TEXT_COLOR, fieldbackground=FRAME_COLOR, borderwidth=0)
    style.configure("App.TFrame", background=BG_COLOR)

    style.configure("NavBar.TFrame", background=NAV_BAR_COLOR)
    style.configure("NavBar.TLabel", background=NAV_BAR_COLOR, foreground=BG_COLOR, font=("Segoe UI", 14, "bold"))

    style.layout('TButton', [('Button.border', {'sticky': 'nswe', 'border': '1', 'children': [
        ('Button.padding', {'sticky': 'nswe', 'children': [
            ('Button.label', {'sticky': 'nswe'})
        ]})
    ]})])

    style.configure("Nav.TButton", background=NAV_BAR_COLOR, foreground=BG_COLOR, font=("Segoe UI", 10, "bold"), borderwidth=0, relief="flat", padding=(10, 8))
    style.map("Nav.TButton", background=[('active', NAV_BUTTON_ACTIVE_COLOR), ('hover', NAV_BUTTON_ACTIVE_COLOR)])
    style.configure("ActiveNav.TButton", background=NAV_BUTTON_ACTIVE_COLOR, foreground=TEXT_COLOR, font=("Segoe UI", 10, "bold"), relief="flat", padding=(10, 8))

    style.configure("Accent.TButton", background=NAV_BAR_COLOR, foreground=BG_COLOR, font=("Segoe UI", 10, "bold"), padding=(10,8))
    style.map("Accent.TButton", background=[('active', NAV_BUTTON_ACTIVE_COLOR), ('hover', NAV_BUTTON_ACTIVE_COLOR)])
    style.configure("Outline.TButton", background=BG_COLOR, foreground=TEXT_COLOR, relief="solid", borderwidth=1, bordercolor=FRAME_COLOR, font=("Segoe UI", 10, "bold"), padding=(10,8))
    style.map("Outline.TButton", background=[('active', FRAME_COLOR), ('hover', FRAME_COLOR)])
    style.map('TCombobox', fieldbackground=[('readonly', FRAME_COLOR)], foreground=[('readonly', TEXT_COLOR)], selectbackground=[('readonly', FRAME_COLOR)], selectforeground=[('readonly', ACCENT_COLOR)])

    style.map('Treeview', background=[('selected', NAV_BUTTON_ACTIVE_COLOR)])

    style.configure("Treeview", rowheight=28, font=("Segoe UI", 10), background=FRAME_COLOR, fieldbackground=FRAME_COLOR, foreground=TEXT_COLOR)
    style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background=TABLE_HEADER_BG, foreground=TEXT_COLOR, padding=8)
    style.map("Treeview.Heading", background=[('!active', ACCENT_COLOR)])

    style.configure("TLabelframe", background=BG_COLOR, bordercolor=TABLE_HEADER_BG)
    style.configure("TLabelframe.Label", background=BG_COLOR, foreground=ACCENT_COLOR, font=("Segoe UI", 11, "bold"))
    style.configure("App.Vertical.TScrollbar", troughcolor=BG_COLOR, background=FRAME_COLOR, arrowcolor=ACCENT_COLOR)

    app = PDFInserterApp(root, CIDADES_VALIDAS)
    rotina_de_inicializacao(app)
    root.mainloop()
