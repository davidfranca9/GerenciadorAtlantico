from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/atlantico"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    cors_allowed_origins: str = "http://localhost:5173"

    azure_vision_endpoint: str = ""
    azure_vision_key: str = ""

    gmail_sender_email: str = ""
    gmail_app_password_send: str = ""
    gmail_app_password_imap: str = ""
    gmail_factory_sender: str = ""

    bsoft_api_base_url: str = ""
    bsoft_api_user: str = ""
    bsoft_api_password: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


settings = Settings()
