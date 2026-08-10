from ..shared import *

def rotina_de_inicializacao(app):
    aba_agendamentos = app._conectar_google_sheets("Agendamentos")
    if aba_agendamentos:
        app.limpar_agendamentos_antigos(aba_agendamentos)
        app._compactar_planilha(aba_agendamentos)
    aba_pedidos_grandes = app._conectar_google_sheets("Pedidos Grandes")
    if aba_pedidos_grandes:
        app._compactar_planilha(aba_pedidos_grandes)
