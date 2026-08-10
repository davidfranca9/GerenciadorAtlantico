"""Elementos compartilhados da aplica??o Atl?ntico Fertlog."""

import json
import os
import sys
import ctypes
if getattr(sys, 'frozen', False):
    # Oculta a saída do console ao rodar como executável
    NULL_FILE = open(os.devnull, 'w', encoding='utf-8')
    sys.stdout = NULL_FILE
    sys.stderr = NULL_FILE
import time
import re
import subprocess
import pandas as pd
import pdfplumber
from tkcalendar import Calendar, DateEntry
from openpyxl import load_workbook, Workbook
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, Toplevel, Label, Radiobutton, Button, StringVar, Frame
from datetime import datetime, timedelta
from PIL import Image, ImageTk
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import unicodedata
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.core.credentials import AzureKeyCredential
import fitz # PyMuPDF
from docx2pdf import convert
import traceback
import locale
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import mimetypes
import gspread
from imap_tools import MailBox, A
import email
from email.header import decode_header
import threading
import time
import queue # <--- ADICIONADO para comunicação thread-safe com a UI
import requests
import collections
import uuid
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.platypus import Image as ReportLabImage # <<< NOVO NOME AQUI
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont 
from reportlab.lib.enums import TA_RIGHT
from io import BytesIO

def configurar_dpi_windows():
    """
    Evita borrado em telas com escala do Windows (125%, 150%, etc.)
    tornando o processo DPI-aware antes de criar o Tk().
    """
    if os.name != "nt":
        return

    try:
        # PER_MONITOR_AWARE_V2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass

    try:
        # Fallback para Windows antigos
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def ajustar_escala_tk(root_widget):
    """Sincroniza a escala interna do Tk com o DPI real do monitor."""
    try:
        dpi = root_widget.winfo_fpixels("1i")
        if dpi > 0:
            root_widget.tk.call("tk", "scaling", dpi / 72.0)
    except Exception:
        pass


# ==============================================================================
# Paleta de Cores e Constantes de Estilo
# ==============================================================================
BG_COLOR = "#1C2536"  # Azul escuro principal
FRAME_COLOR = "#2A3B52" # Azul um pouco mais claro para frames internos
ACCENT_COLOR = "#20C4B4" # Ciano/Verde para botões e destaques
TEXT_COLOR = "#FFFFFF" # Branco
GRAY_TEXT_COLOR = "#A0AEC0" # Cinza claro para texto secundário
TABLE_HEADER_BG = "#3E516C"
DANGER_COLOR = "#E53E3E"
SUCCESS_COLOR = "#48BB78"
WARNING_COLOR = "#F6AD55"
INFO_COLOR = "#4299E1"



# Adicione a fonte Arial para suportar acentos no ReportLab (mantida)
try:
    pdfmetrics.registerFont(TTFont('Arial', 'arial.ttf'))
    pdfmetrics.registerFont(TTFont('Arial-Bold', 'arialbd.ttf'))
except Exception as e:
    pass

BSOFT_CATEGORY_ID_TO_RODADO_ID_MAP = {
    # Categoria ID -> Rodado ID
    7: '00',  # 3/4 -> NÃO APLICÁVEL
    8: '05',  # AUTOMÓVEIS -> UTILITARIO
    11: '01', # BITRUCK -> TRUCK
    3: '00',  # CARRETA -> NÃO APLICÁVEL
    1: '03',  # CAVALO -> CAVALO MECANICO
    9: '03',  # CAVALO 4 EIXOS -> CAVALO MECANICO
    10: '03', # CAVALO TRUCADO 3 EIXOS -> CAVALO MECANICO
    2: '00',  # SEMI-REBOQUE 1 -> NÃO APLICÁVEL
    12: '00', # SEMI-REBOQUE 2 -> NÃO APLICÁVEL
    13: '00', # DOLLY -> NÃO APLICÁVEL
    4: '01',  # TRUCK -> TRUCK
    6: '02',  # TOCO -> TOCO
    5: '04'   # VAN -> VAN
}

def get_key_from_value(d, val):
    """Busca um valor em um dicionário e retorna a chave correspondente."""
    return next((k for k, v in d.items() if v == val), None)



def resource_path(relative_path):
    """ Retorna o caminho absoluto para o recurso, funciona para dev e para PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ---------------- CONSTANTES GLOBAIS ----------------
AZURE_ENDPOINT = "https://meu-projeto-ocr.cognitiveservices.azure.com/"
AZURE_KEY = os.environ.get("AZURE_KEY", "")
EMAIL_REMETENTE = "atlanticofertlog.comercial@gmail.com"
SENHA_APP_EMAIL = os.environ.get("SENHA_APP_EMAIL", "")
EXCEL_FILE = (resource_path("dados/Autorizacao de Carregamento (2).xlsx"))
SHEET_NAME = "Ordem de Carregamento"
TEMPLATE_OC = (resource_path("dados/O.C_AFL.docx"))
TEMPLATE_OC_HERINGER = (resource_path("dados/O.C_HERINGER.docx")) # <-- ADICIONE ESTA LINHA
TEMPLATE_CF = (resource_path("dados/CARTA FRETE atlantico (1).docx"))
EXPECTED_HEADERS = [
    "Cliente", "Data de Carregamento", "Placa cavalo mecânico", "Nome do condutor",
    "Número do pedido", "Produto", "Embalagem", "Quantidade", "Cidade/UF"
]
PLANILHA_CIDADES = resource_path("dados/CIDADES E UF.xlsx")
ABA_CIDADES = "Planilha1"
EMAIL_IMAP_SERVER = "imap.gmail.com"
SENHA_APP_EMAIL_LEITURA = os.environ.get("SENHA_APP_EMAIL_LEITURA", "")
EMAIL_FABRICA = "elisangela.santos@fertimaxi.com.br" # E-mail de quem envia a confirmação
LOGO_APP_PATH = resource_path("dados/logo.png")
LOGO_RELATORIO_PATH = resource_path("dados/file.jpg")
# --- CONSTANTES PARA A API BSOFT ---
# !!! SUBSTITUA 'seudominio' PELO SEU DOMÍNIO REAL DA BSOFT !!!
BSOFT_API_BASE_URL = "https://atlanticofertlog.bsoft.app/services/index.php/pessoas/v1/pessoas/fisicas" 
# !!! SUBSTITUA COM SEU USUÁRIO E SENHA FORNECIDOS PELA BSOFT !!!
BSOFT_API_USER = "API"
BSOFT_API_PASSWORD = os.environ.get("BSOFT_API_PASSWORD", "")
ADMIN_MAC_ADDRESS = os.environ.get("ADMIN_MAC_ADDRESS", "")
ADMIN_OVERRIDE_PASSWORD = os.environ.get("ADMIN_OVERRIDE_PASSWORD", "")


BSOFT_MARCA_ID_LOOKUP = {
    ('SCANIA', 'CAVALO'): 1, ('VOLVO', 'CAVALO'): 2, ('IVECO', 'CAVALO'): 3, ('VOLKSWAGEN', 'CAVALO'): 4,
    ('GUERRA', 'CARRETA'): 5, ('GUERRA', 'SEMI-REBOQUE 1'): 7, ('FORD', 'CAVALO'): 8, ('MERCEDES BENZ', 'CAVALO'): 9,
    ('SCHIFFER', 'SEMI-REBOQUE 1'): 11, ('RANDON', 'SEMI-REBOQUE 1'): 12, ('FACCHINI', 'SEMI-REBOQUE 1'): 13,
    ('NOMA', 'SEMI-REBOQUE 1'): 14, ('REB KRONE', 'SEMI-REBOQUE 1'): 15, ('FIAT', 'CAVALO'): 17,
    ('FACCHINI', 'CARRETA'): 18, ('NOMA', 'CARRETA'): 19, ('RANDON', 'CARRETA'): 20, ('LIBRELATO', 'CARRETA'): 21,
    ('SCHIFFER', 'CARRETA'): 22, ('SERRATO', 'CARRETA'): 24, ('KRONE', 'CARRETA'): 26, ('NAVISTAR', 'CAVALO'): 27,
    ('MARCOFRIO', 'CARRETA'): 28, ('CHARGER', 'CARRETA'): 29, ('ANTONINI', 'CARRETA'): 30,
    ('ANTONINI', 'SEMI-REBOQUE 1'): 31, ('RODOLINEA', 'CARRETA'): 32, ('RODOLINEA', 'SEMI-REBOQUE 1'): 33,
    ('ROSSETTI', 'CARRETA'): 34, ('LIBRELATO', 'SEMI-REBOQUE 1'): 35, ('RECRUSUL', 'CARRETA'): 36,
    ('FNV', 'CARRETA'): 37, ('IDEROL', 'CARRETA'): 38, ('SAN MARINO', 'CARRETA'): 39,
    ('PASTRE', 'SEMI-REBOQUE 1'): 40, ('PIKO', 'CARRETA'): 41, ('GOTTI', 'CARRETA'): 42, ('VOLVO', 'TRUCK'): 43,
    ('MERCEDES BENZ', 'TRUCK'): 44, ('VW', 'TRUCK'): 45, ('FORD', 'TRUCK'): 46, ('SCANIA', 'TRUCK'): 47,
    ('FIAT', 'TRUCK'): 48, ('HYUNDAI', 'TOCO'): 49, ('KIA', 'TOCO'): 50, ('FIAT', 'AUTOMÓVEIS'): 51,
    ('SCANIA', 'CAVALO 4 EIXOS'): 52, ('SCANIA', 'CAVALO TRUCADO 3 EIXOS'): 53, ('SCANIA', 'BITRUCK'): 54,
    ('MAN', 'CAVALO'): 55, ('SR', 'SEMI-REBOQUE 1'): 56, ('GUERRA', 'SEMI-REBOQUE 2'): 57, ('IVECO', 'TRUCK'): 58,
    ('IRMAOS CLARA', 'SEMI-REBOQUE 1'): 59, ('ROSSETTI', 'SEMI-REBOQUE 1'): 60,
    ('IDEROL', 'SEMI-REBOQUE 1'): 61, ('SAO PEDRO', 'SEMI-REBOQUE 1'): 62, ('ALFASTEEL', 'SEMI-REBOQUE 1'): 63,
    ('VOLVO', 'CAVALO TRUCADO 3 EIXOS'): 64, ('RANDONSP', 'SEMI-REBOQUE 1'): 65,
    ('LIBRELATO', 'SEMI-REBOQUE 2'): 66, ('TRIELHT', 'SEMI-REBOQUE 1'): 67, ('DAF', 'TRUCK'): 68,
    ('TECTRAN', 'SEMI-REBOQUE 1'): 69, ('DAF', 'CAVALO'): 70, ('ESTRADA', 'SEMI-REBOQUE 1'): 71,
    ('VW', 'CAVALO'): 72, ('NEW-G', 'SEMI-REBOQUE 1'): 73, ('NEW-G', 'SEMI-REBOQUE 2'): 74,
    ('NOMA', 'SEMI-REBOQUE 2'): 75, ('RANDON', 'SEMI-REBOQUE 2'): 76, ('FACCHINI', 'SEMI-REBOQUE 2'): 77,
    ('RODOFORTSA', 'SEMI-REBOQUE 1'): 78, ('UNICARR', 'SEMI-REBOQUE 1'): 79
}

# CORRIGIDO: Usando a lista original de 1 a 13
BSOFT_CATEGORIAS_VEICULO = {
    'CAVALO': 1, 'SEMI-REBOQUE 1': 2, 'CARRETA': 3, 'TRUCK': 4, 'VAN': 5, 'TOCO': 6,
    '3/4': 7, 'AUTOMÓVEIS': 8, 'CAVALO 4 EIXOS': 9, 'CAVALO TRUCADO 3 EIXOS': 10,
    'BITRUCK': 11, 'SEMI-REBOQUE 2': 12, 'DOLLY': 13
}

BSOFT_TIPOS_EQUIPAMENTO = {
    "TOCO": 1, "3/4": 2, "CARRETA SIMPLES": 3, "CAVALO": 4, "TRUCK": 5, "AUTOMÓVEIS": 7, "CAVALO 4 EIXOS": 8,
    "CAVALO TRUCADO 3 EIXOS": 9, "BITRUCK": 10, "CARRETA 3 EIXOS": 11, "CARRETA VANDERLEIA 3 EIXOS ESPAÇADOS": 12,
    "CARRETA 4º EIXOS": 13, "SEMI-REBOQUE 1": 14, "SEMI-REBOQUE 2": 15, "DOLLY": 16
}

# --- ADICIONE ESTE DICIONÁRIO QUE FALTAVA ---
BSOFT_GRUPOS_VEICULO = {
    "FROTA PROPRIA": 1,
    "FROTA DE TERCEIROS": 2
}
# Tabela de tradução CORRIGIDA para usar apenas os IDs de 1 a 13
# Tabela de tradução para mapear Categoria para o Equipamento correto
BSOFT_CATEGORY_TO_EQUIPMENT_MAP = {
    1: 4,   # CAVALO -> CAVALO
    2: 14,  # SEMI-REBOQUE 1 -> SEMI-REBOQUE 1
    3: 11,  # CARRETA -> CARRETA 3 EIXOS (mapeamento lógico)
    4: 5,   # TRUCK -> TRUCK
    6: 1,   # TOCO -> TOCO
    7: 2,   # 3/4 -> 3/4
    8: 7,   # AUTOMÓVEIS -> AUTOMÓVEIS
    9: 8,   # CAVALO 4 EIXOS -> CAVALO 4 EIXOS
    10: 9,  # CAVALO TRUCADO 3 EIXOS -> CAVALO TRUCADO 3 EIXOS
    11: 10, # BITRUCK -> BITRUCK
    12: 15, # SEMI-REBOQUE 2 -> SEMI-REBOQUE 2
    13: 16  # DOLLY -> DOLLY
}

BSOFT_TIPOS_RODADO_NOMES = {
    '00': 'NÃO APLICÁVEL', '01': 'TRUCK', '02': 'TOCO', '03': 'CAVALO MECANICO',
    '04': 'VAN', '05': 'UTILITARIO', '06': 'OUTROS'
}

BSOFT_TIPOS_CARROCERIA_NOMES = {
    '00': 'NÃO APLICAVEL', '01': 'ABERTA', '02': 'FECHADA/BAÚ', '03': 'GRANELEIRA',
    '04': 'PORTA CONTAINER', '05': 'SIDER'
}



BSOFT_CATEGORY_TO_SIMPLE_BRANDS_MAP = {
    'CAVALO': ['SCANIA', 'VOLVO', 'IVECO', 'VOLKSWAGEN', 'FORD', 'MERCEDES BENZ', 'FIAT', 'NAVISTAR', 'MAN', 'DAF', 'VW'],
    'SEMI-REBOQUE 1': ['GUERRA', 'SCHIFFER', 'RANDON', 'FACCHINI', 'NOMA', 'REB KRONE', 'ANTONINI', 'RODOLINEA', 'LIBRELATO', 'PASTRE', 'SR', 'IRMAOS CLARA', 'ROSSETTI', 'IDEROL', 'SAO PEDRO', 'ALFASTEEL', 'RANDONSP', 'TRIELHT', 'TECTRAN', 'ESTRADA', 'NEW-G', 'RODOFORTSA', 'UNICARR'],
    'CARRETA': ['GUERRA', 'FACCHINI', 'NOMA', 'RANDON', 'LIBRELATO', 'SCHIFFER', 'SERRATO', 'KRONE', 'MARCOFRIO', 'CHARGER', 'ANTONINI', 'RODOLINEA', 'ROSSETTI', 'RECRUSUL', 'FNV', 'IDEROL', 'SAN MARINO', 'PIKO', 'GOTTI'],
    'TRUCK': ['VOLVO', 'MERCEDES BENZ', 'VW', 'FORD', 'SCANIA', 'FIAT', 'IVECO', 'DAF'],
    'TOCO': ['HYUNDAI', 'KIA'],
    'AUTOMÓVEIS': ['FIAT'],
    'CAVALO 4 EIXOS': ['SCANIA'],
    'CAVALO TRUCADO 3 EIXOS': ['SCANIA', 'VOLVO'],
    'BITRUCK': ['SCANIA'],
    'SEMI-REBOQUE 2': ['GUERRA', 'LIBRELATO', 'NEW-G', 'NOMA', 'RANDON', 'FACCHINI']
}


BSOFT_SIMPLE_BRANDS_LIST = sorted(list(set(marca for marca, categoria in BSOFT_MARCA_ID_LOOKUP.keys())), key=len, reverse=True)
# ------------------------------------------------------------------------------









