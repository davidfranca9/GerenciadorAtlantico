from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/atlantico"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    cors_allowed_origins: str = "http://localhost:5173"

    gmail_sender_email: str = ""
    gmail_app_password_send: str = ""
    gmail_app_password_imap: str = ""
    gmail_factory_sender: str = ""

    bsoft_api_base_url: str = "https://atlanticofertlog.bsoft.app/services/index.php"
    bsoft_api_user: str = ""
    bsoft_api_password: str = ""
    bsoft_timeout_segundos: int = 30
    # RNTRC da frota propria. O RNTRC e dado de quem transporta: o motorista
    # autonomo tem o dele (vem da tela/do OCR do documento) e o proprietario
    # PJ tem o da empresa dele. Este aqui e so a rede de seguranca do caminhao
    # da casa, quando o motorista e empregado e nao tem RNTRC proprio. Fica em
    # variavel de ambiente (BSOFT_RNTRC_PADRAO) porque e cadastro da empresa:
    # nao entra no codigo e nunca e exposto no frontend. Vazio = sem rede, a
    # tela passa a exigir o RNTRC preenchido.
    bsoft_rntrc_padrao: str = ""

    # Ids do tenant, descobertos pela API e pela tela do Bsoft. Ficam aqui
    # (e nao no codigo) pra poder corrigir por variavel de ambiente, sem
    # deploy, se algum cadastro mudar do lado deles.
    bsoft_agencia_id: int = 2                 # ATLANTICO FERTLOG
    bsoft_talao_cte_id: int = 3               # talao tipo Conhecimento
    bsoft_talao_mdfe_id: int = 7              # talao tipo Manifesto de carga
    bsoft_talao_contrato_frete_id: int = 5    # talao RECIBO DE FRETE
    bsoft_regra_frete_id: int = 35            # regra "Calculo FERTIMAXI"
    bsoft_numero_apolice: str = "202511"      # apolice CHUBB SEGUROS BRASIL S.A.
    # Apolice RCTR-C da CHUBB (numero 202511, vigencia 27/05/2026 a
    # 31/05/2027), lida na tela de Apolices de Seguro: na listagem do Bsoft o
    # id do registro vem no checkbox da linha (name="id" value="3").
    bsoft_apolice_id: str = "3"
    # CHUBB SEGUROS BRASIL S.A., lido no cadastro da apolice 3 (o campo da
    # tela se chama dados_seguradora_id, mesmo nome do campo da API).
    bsoft_seguradora_id: str = "2096"
    bsoft_natureza_carga_id: int = 4          # FERTILIZANTES
    # Natureza da operacao (na API o campo e cfops_id). A escolha entre as
    # duas segue a regra do CFOP: 5xxx dentro do estado, 6xxx fora dele.
    bsoft_cfops_id_estadual: int = 1          # CFOP 5352
    bsoft_cfops_id_interestadual: int = 3     # CFOP 6352
    # Ainda desconhecido: o cadastro paramCriaCteViaNFe esta vazio no tenant
    # e precisa ser criado no Bsoft (pergunta 1.6 do suporte). Sem ele, o
    # POST /conhecimentos/viaNFe nao tem como funcionar.
    bsoft_parametro_criacao_cte: str = ""
    # Trava geral: com False, nenhuma operacao que cria ou altera documento
    # fiscal no Bsoft e executada (so leitura). Ligada por autorizacao
    # explicita do responsavel, que cancela o CT-e no Bsoft se sair errado.
    # Pra desligar sem deploy: BSOFT_EMISSAO_HABILITADA=false.
    bsoft_emissao_habilitada: bool = True
    # Quando a nota chega ja casada com o agendamento e com tarifa da
    # cotacao, o sistema monta o CT-e e cria o RASCUNHO no Bsoft sozinho.
    # Nunca o definitivo. Pra desligar sem deploy: RASCUNHO_AUTOMATICO=false.
    rascunho_automatico: bool = True
    # E-mails de inclusao e substituicao de motorista. Testados em 16/09/2026
    # com e-mail de verdade pra davidfranca9@gmail.com e aprovados: vao pra
    # fabrica. Pra voltar ao modo teste sem deploy: EMAILS_MOTORISTA_EM_TESTE=true.
    emails_motorista_em_teste: bool = False
    # Destino dos e-mails de teste - os de inclusao/substituicao enquanto em
    # teste, e qualquer e-mail de fabrica chamado com teste=True.
    email_teste_fabrica: str = "davidfranca9@gmail.com"

    # Certificado A1 da empresa, usado pra baixar XML de NF-e direto da
    # SEFAZ. O arquivo fica FORA do repositorio e o caminho vem por
    # variavel de ambiente; a senha idem.
    certificado_pfx_path: str = ""
    certificado_senha: str = ""
    certificado_cnpj: str = "08187322000101"
    sefaz_timeout_segundos: int = 60

    gemini_api_key: str = ""

    # --- Extrato de conta corrente do Itau (API do devportal) -------------
    # Credencial de BANCO: nada disso entra no codigo, nada e exposto no
    # frontend e nada aparece em log (nem o token, nem o secret, nem o
    # conteudo do certificado). Sem as variaveis preenchidas a rota responde
    # "Configure as credenciais do Itau" em vez de tentar a chamada.
    itau_client_id: str = ""
    itau_client_secret: str = ""        # o devportal mostra o secret UMA vez
    # Certificado dinamico (mTLS): o .crt que o Itau assinou a partir do CSR
    # e a .key gerada com ele. Os arquivos ficam FORA do repositorio.
    itau_cert_path: str = ""
    itau_cert_key_path: str = ""
    # No servidor nao ha onde largar arquivo: da pra colar o conteudo do .crt
    # e do .key aqui (o texto inteiro, com as linhas BEGIN/END). O sistema
    # escreve os dois em disco, so pra ele mesmo, na primeira chamada.
    itau_cert_pem: str = ""
    itau_cert_key_pem: str = ""
    # A conta na URL do extrato e agencia(4) + "00" + conta(5) + DAC(1) - o
    # exemplo da documentacao e 816100994788. Guardamos em pedacos pra nao
    # errar a montagem na mao.
    itau_agencia: str = ""             # 4 digitos
    itau_conta: str = ""               # 5 digitos (aceita 6 com o DAC junto)
    itau_conta_dac: str = ""           # 1 digito
    # URLs de PRODUCAO. Homologacao (pra testar antes de valer dinheiro):
    #   ITAU_TOKEN_URL=https://sts.rdhi.com.br/api/oauth/token
    #   ITAU_EXTRATO_BASE_URL=https://account-statement.api.hom.itau.com/account-statement/v1
    itau_token_url: str = "https://sts.itau.com.br/api/oauth/token"
    itau_extrato_base_url: str = "https://account-statement.api.itau.com/account-statement/v1"
    itau_timeout_segundos: int = 60
    # A documentacao mostra page_size 8000 e 100. 100 e o tamanho seguro: com
    # pagina grande um mes inteiro vem numa resposta so, mas o banco nao
    # garante isso em lugar nenhum - o servico pagina de qualquer jeito.
    itau_page_size: int = 100

    whatsapp_verify_token: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_supplier_padrao: str = "AFL"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


settings = Settings()
