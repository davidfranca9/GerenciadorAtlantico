from ..shared import *

def _get_timestamp():
    """Retorna a data e hora atual formatada para logs."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

def _report_error(title, message, error_handler=None):
    if callable(error_handler):
        error_handler(title, message)
        return
    messagebox.showerror(title, message)


def cadastrar_veiculo_bsoft(dados_veiculo, error_handler=None):
    """
    [VERSÃO FINAL] Envia os dados de um novo veículo para a Bsoft.
    """
    endpoint_url = "https://atlanticofertlog.bsoft.app/services/index.php/transporte/v1/veiculos"
    auth = (BSOFT_API_USER, BSOFT_API_PASSWORD)
    
    temp_payload = {
        "placa": dados_veiculo.get("placa"), "renavam": dados_veiculo.get("renavam"),
        "rntrc": dados_veiculo.get("rntrc"), "tara": dados_veiculo.get("tara"),
        "capacidadeCarga": dados_veiculo.get("capacidadeCarga"), "capM3": dados_veiculo.get("capM3"),
        "modeloVeiculo": dados_veiculo.get("modeloVeiculo"), "quantidadeEixos": dados_veiculo.get("quantidadeEixos"),
        "marcaVeiculo": dados_veiculo.get("marcaVeiculo"), "categoriaVeiculo": dados_veiculo.get("categoriaVeiculo"),
        "grupoVeiculo": dados_veiculo.get("grupoVeiculo"), "tipoRodado": dados_veiculo.get("tipoRodado"),
        "tipoCarroceria": dados_veiculo.get("tipoCarroceria"), "tipoEquipamento": dados_veiculo.get("tipoEquipamento"),
        "motoristaEhProprietario": "S" if dados_veiculo.get("motoristaEhProprietario") else "N",
        "estado": dados_veiculo.get("estado"),
        "cidade": dados_veiculo.get("cidade"),
        "proprietarioId": dados_veiculo.get("proprietario_id"),
        # --- NOVOS CAMPOS ADICIONADOS AQUI ---
        "motoristaId": dados_veiculo.get("motoristaId"),
        "arrendatarioId": dados_veiculo.get("arrendatarioId")
        # -------------------------------------
    }

    if not dados_veiculo.get("motoristaEhProprietario"):
        temp_payload["motorista"] = dados_veiculo.get("motorista_documento")

    payload = {k: v for k, v in temp_payload.items() if v is not None and v != ''}

    try:
        print(f"{_get_timestamp()} [VEÍCULO] Enviando dados para a Bsoft: {payload}")
        response = requests.post(endpoint_url, json=payload, auth=auth, timeout=30)
        
        if response.status_code in [200, 201]:
            print(f"{_get_timestamp()} [VEÍCULO] SUCESSO: Resposta do cadastro: {response.json()}")
            return response.json()
        else:
            print(f"{_get_timestamp()} [VEÍCULO] ERRO: Status: {response.status_code}, Resposta: {response.text}")
            _report_error("Erro na API Bsoft (Veículo)", f"Falha ao cadastrar veículo.\n\nCódigo: {response.status_code}\nResposta: {response.text}", error_handler)
            return None
    except requests.exceptions.RequestException as e:
        print(f"{_get_timestamp()} [VEÍCULO] ERRO DE CONEXÃO: {e}")
        _report_error("Erro de Conexão (Veículo)", f"Não foi possível conectar à API da Bsoft TMS.\n\nErro: {e}", error_handler)
        return None

def cadastrar_endereco_bsoft(cod_pessoa, dados_endereco, error_handler=None):
    """
    [VERSÃO FINAL E CORRIGIDA] Envia um endereço para uma pessoa específica,
    incluindo o ID tanto na URL quanto no payload, conforme a API da Bsoft.
    """
    print(f"\n{_get_timestamp()} [ENDEREÇO] Entrando em 'cadastrar_endereco_bsoft' (Versão Híbrida)...")
    if not cod_pessoa or not dados_endereco.get('logradouro'):
        print(f"{_get_timestamp()} [ENDEREÇO] Pulei o cadastro (ID da pessoa ou logradouro ausente).")
        return None

    # 1. URL CORRIGIDA: Usa f-string para incluir o ID da pessoa na URL
    endpoint_url = f"https://atlanticofertlog.bsoft.app/services/index.php/pessoas/v1/pessoas/{cod_pessoa}/enderecos"
    auth = (BSOFT_API_USER, BSOFT_API_PASSWORD)
    
    # 2. PAYLOAD HÍBRIDO: Também inclui o 'codPessoa' dentro do payload
    payload = dados_endereco.copy()
    payload['codPessoa'] = str(cod_pessoa) # <-- LINHA RE-ADICIONADA
    
    payload_limpo = {k: v for k, v in payload.items() if v is not None and v != ''}
    
    try:
        print(f"{_get_timestamp()} [ENDEREÇO] Enviando para URL: {endpoint_url}")
        print(f"{_get_timestamp()} [ENDEREÇO] Payload final para ID {cod_pessoa}:")
        print(json.dumps(payload_limpo, indent=2, ensure_ascii=False))
        
        # O método continua sendo POST
        resp = requests.post(endpoint_url, json=payload_limpo, auth=auth, timeout=20)
        
        if resp.status_code in [200, 201]:
            print(f"{_get_timestamp()} [ENDEREÇO] SUCESSO: Resposta da API: {resp.status_code}")
            return resp.json()
        else:
            print(f"{_get_timestamp()} [ENDEREÇO] ERRO: Status: {resp.status_code}, Resposta: {resp.text}")
            _report_error("Erro na API Bsoft (Endereço)", f"Falha ao cadastrar endereço.\nCódigo: {resp.status_code}\nResposta: {resp.text}", error_handler)
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"{_get_timestamp()} [ENDEREÇO] ERRO DE CONEXÃO: {e}")
        _report_error("Erro de Conexão (Endereço)", f"Não foi possível conectar à API: {e}", error_handler)
        return None

def cadastrar_pessoa_fisica_bsoft(dados_motorista, error_handler=None):
    print(f"\n{_get_timestamp()} [PESSOA FÍSICA] Entrando em 'cadastrar_pessoa_fisica_bsoft' (versão simples)...")
    endpoint_url = "https://atlanticofertlog.bsoft.app/services/index.php/pessoas/v1/pessoas/fisicas"
    auth = (BSOFT_API_USER, BSOFT_API_PASSWORD)
    partes_nome = dados_motorista.get("nome", "").split(" ", 1)
    
    payload = {
        "dependentesIRRF": 0, "cpf": dados_motorista.get("cpf"), "nome": partes_nome[0],
        "sobrenome": partes_nome[1] if len(partes_nome) > 1 else "", "dtNascimento": dados_motorista.get("dtNascimento"),
        "tipoTransportadora": "T", "RNTRC": dados_motorista.get("rntrc"), "celular": dados_motorista.get("fone"),
        "grupos": ["motoristas", "proprietariosVeiculos"] if dados_motorista.get("is_owner") else ["motoristas"],
        "cnh": {k: v for k, v in dados_motorista.get("cnh", {}).items() if v}
    }

    try:
        print(f"{_get_timestamp()} [PESSOA FÍSICA] Payload final de CRIAÇÃO:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        resp = requests.post(endpoint_url, json=payload, auth=auth, timeout=20)
        if resp.status_code in (200, 201):
            print(f"{_get_timestamp()} [PESSOA FÍSICA] SUCESSO (CREATE): Resposta da API: {resp.status_code}")
            return resp.json()
        else:
            print(f"{_get_timestamp()} [PESSOA FÍSICA] ERRO (CREATE): Status: {resp.status_code}, Resposta: {resp.text}")
            _report_error("Erro API Bsoft (Cadastro PF)", f"Falha ao CADASTRAR motorista.\nCódigo: {resp.status_code}\n{resp.text}", error_handler)
            return None
    except requests.exceptions.RequestException as e:
        print(f"{_get_timestamp()} [PESSOA FÍSICA] ERRO DE CONEXÃO (CREATE): {e}")
        _report_error("Erro de Conexão (Cadastro PF)", f"Não foi possível conectar à API: {e}", error_handler)
        return None

def atualizar_pessoa_fisica_bsoft(cpf, dados_motorista, error_handler=None):
    print(f"\n{_get_timestamp()} [PESSOA FÍSICA] Entrando em 'atualizar_pessoa_fisica_bsoft'...")
    endpoint_url = f"https://atlanticofertlog.bsoft.app/services/index.php/pessoas/v1/pessoas/fisicas/{cpf}"
    auth = (BSOFT_API_USER, BSOFT_API_PASSWORD)
    partes_nome = dados_motorista.get("nome", "").split(" ", 1)
    
    payload = {
        "dependentesIRRF": 0, "cpf": cpf, "nome": partes_nome[0],
        "sobrenome": partes_nome[1] if len(partes_nome) > 1 else "", "dtNascimento": dados_motorista.get("dtNascimento"),
        "tipoTransportadora": "T", "RNTRC": dados_motorista.get("rntrc"), "celular": dados_motorista.get("fone"),
        "grupos": ["motoristas", "proprietariosVeiculos"] if dados_motorista.get("is_owner") else ["motoristas"],
        "cnh": {k: v for k, v in dados_motorista.get("cnh", {}).items() if v}
    }
    
    try:
        print(f"{_get_timestamp()} [PESSOA FÍSICA] Payload final de ATUALIZAÇÃO:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        resp = requests.put(endpoint_url, json=payload, auth=auth, timeout=20)
        if resp.status_code == 200:
            print(f"{_get_timestamp()} [PESSOA FÍSICA] SUCESSO (UPDATE): Resposta da API: {resp.status_code}")
            return resp.json()
        else:
            print(f"{_get_timestamp()} [PESSOA FÍSICA] ERRO (UPDATE): Status: {resp.status_code}, Resposta: {resp.text}")
            _report_error("Erro API Bsoft (Update PF)", f"Falha ao ATUALIZAR motorista.\nCódigo: {resp.status_code}\n{resp.text}", error_handler)
            return None
    except requests.exceptions.RequestException as e:
        print(f"{_get_timestamp()} [PESSOA FÍSICA] ERRO DE CONEXÃO (UPDATE): {e}")
        _report_error("Erro de Conexão (Update PF)", f"Não foi possível conectar à API: {e}", error_handler)
        return None

def cadastrar_pessoa_juridica_bsoft(dados_empresa, error_handler=None):
    print("\n>>> Entrando em 'cadastrar_pessoa_juridica_bsoft'...")
    endpoint_url = "https://atlanticofertlog.bsoft.app/services/index.php/pessoas/v1/pessoas/juridicas"
    auth = (BSOFT_API_USER, BSOFT_API_PASSWORD)
    payload = { "cnpj": dados_empresa.get("cnpj"), "razaoSocial": dados_empresa.get("razao_social"), "nomeFantasia": dados_empresa.get("razao_social"), "tipoTransportadora": dados_empresa.get("tipoTransportadora"), "RNTRC": dados_empresa.get("rntrc"), "inscricaoEstadual": dados_empresa.get("inscricao_estadual"), "grupos": ["proprietariosVeiculos"] }
    payload_limpo = {k: v for k, v in payload.items() if v is not None and v != ''}
    try:
        print("[DEBUG PJ CREATE] Payload final:")
        print(json.dumps(payload_limpo, indent=2, ensure_ascii=False))
        resp = requests.post(endpoint_url, json=payload_limpo, auth=auth, timeout=20)
        if resp.status_code in [200, 201]:
            print("[SUCESSO PJ CREATE] Resposta da API:", resp.status_code)
            return resp.json()
        else:
            print(f"[ERRO PJ CREATE] Status: {resp.status_code}, Resposta: {resp.text}")
            _report_error("Erro API Bsoft (Cadastro PJ)", f"Falha ao cadastrar proprietário (PJ).\nCódigo: {resp.status_code}\n{resp.text}", error_handler)
            return None
    except requests.exceptions.RequestException as e:
        print(f"[ERRO PJ CREATE] Falha de conexão: {e}")
        _report_error("Erro de Conexão (Cadastro PJ)", f"Não foi possível conectar à API: {e}", error_handler)
        return None


def atualizar_pessoa_juridica_bsoft(cnpj, dados_empresa, error_handler=None):
    print("\n>>> Entrando em 'atualizar_pessoa_juridica_bsoft'...")
    endpoint_url = f"https://atlanticofertlog.bsoft.app/services/index.php/pessoas/v1/pessoas/juridicas/{cnpj}"
    auth = (BSOFT_API_USER, BSOFT_API_PASSWORD)
    payload = { "cnpj": cnpj, "razaoSocial": dados_empresa.get("razao_social"), "nomeFantasia": dados_empresa.get("razao_social"), "tipoTransportadora": dados_empresa.get("tipoTransportadora"), "RNTRC": dados_empresa.get("rntrc"), "inscricaoEstadual": dados_empresa.get("inscricao_estadual"), "grupos": ["proprietariosVeiculos"] }
    payload_limpo = {k: v for k, v in payload.items() if v is not None and v != ''}
    try:
        print("[DEBUG PJ UPDATE] Payload final:")
        print(json.dumps(payload_limpo, indent=2, ensure_ascii=False))
        resp = requests.put(endpoint_url, json=payload_limpo, auth=auth, timeout=20)
        if resp.status_code == 200:
            print("[SUCESSO PJ UPDATE] Resposta da API:", resp.status_code)
            return resp.json()
        else:
            print(f"[ERRO PJ UPDATE] Status: {resp.status_code}, Resposta: {resp.text}")
            _report_error("Erro API Bsoft (Update PJ)", f"Falha ao ATUALIZAR proprietário (PJ).\nCódigo: {resp.status_code}\n{resp.text}", error_handler)
            return None
    except requests.exceptions.RequestException as e:
        print(f"[ERRO PJ UPDATE] Falha de conexão: {e}")
        _report_error("Erro de Conexão (Update PJ)", f"Não foi possível conectar à API: {e}", error_handler)
        return None
