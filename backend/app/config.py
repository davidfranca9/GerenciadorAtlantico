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
