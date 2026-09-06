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
    bsoft_natureza_carga_id: int = 4          # FERTILIZANTES
    # Natureza da operacao (na API o campo e cfops_id). A escolha entre as
    # duas segue a regra do CFOP: 5xxx dentro do estado, 6xxx fora dele.
    bsoft_cfops_id_estadual: int = 1          # CFOP 5352
    bsoft_cfops_id_interestadual: int = 3     # CFOP 6352
    # Ainda desconhecido: o cadastro paramCriaCteViaNFe esta vazio no tenant
    # e precisa ser criado no Bsoft (pergunta 1.6 do suporte). Sem ele, o
    # POST /conhecimentos/viaNFe nao tem como funcionar.
    bsoft_parametro_criacao_cte: str = ""
    # Trava geral: enquanto False, nenhuma operacao que cria/altera documento
    # fiscal no Bsoft e executada (so leitura). Serve pra manter o codigo em
    # producao sem risco ate o suporte confirmar o comportamento da API.
    bsoft_emissao_habilitada: bool = False

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
