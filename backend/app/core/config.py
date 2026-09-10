from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration runtime du socle local 4GIx."""

    model_config = SettingsConfigDict(
        env_prefix="FOURGIX_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "4GIx"
    env: str = "local"
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    database_url: str = "postgresql://4gix_user:4gix_password@4gix-postgis:5432/4gix_db"
    postgis_host: str = "4gix-postgis"
    postgis_port: int = 5432
    postgis_user: str = "4gix_user"
    postgis_password: str = "4gix_password"
    postgis_db: str = "4gix_db"
    workspace_dir: str = "/workspace"
    fme_executable: str = ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                import json

                return json.loads(text)
            return [item.strip() for item in text.split(",") if item.strip()]
        return value

    @property
    def sqlalchemy_url(self) -> str:
        return self.database_url


settings = Settings()
