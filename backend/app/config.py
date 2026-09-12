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

    # Certificado A1 da empresa, usado pra baixar XML de NF-e direto da
    # SEFAZ. O arquivo fica FORA do repositorio e o caminho vem por
    # variavel de ambiente; a senha idem.
    certificado_pfx_path: str = ""
    certificado_senha: str = ""
    certificado_cnpj: str = "08187322000101"
    sefaz_timeout_segundos: int = 60

    gemini_api_key: str = ""

    whatsapp_verify_token: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_supplier_padrao: str = "AFL"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


settings = Settings()
