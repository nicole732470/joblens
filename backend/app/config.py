from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, read from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://jobintel:jobintel@localhost:5432/jobintel"
    cors_origins: list[str] = ["*"]


settings = Settings()
