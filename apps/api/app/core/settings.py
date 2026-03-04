from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_repo_root(start: Path) -> Path:
    cur = start
    for _ in range(20):
        if (cur / "compose.yml").exists() or (cur / "docker-compose.yml").exists() or (cur / ".git").exists():
            return cur
        cur = cur.parent
    return start


HERE = Path(__file__).resolve()
REPO_ROOT = find_repo_root(HERE)

ENV_FILES = [
    str(REPO_ROOT / ".env"),
    str(REPO_ROOT / ".env.local"),
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    project_name: str = Field(default="securitypassport", validation_alias="PROJECT_NAME")

    postgres_db: str = Field(validation_alias="POSTGRES_DB")
    postgres_user: str = Field(validation_alias="POSTGRES_USER")
    postgres_password: str = Field(validation_alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(default="127.0.0.1", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=55432, validation_alias="POSTGRES_PORT")

    redis_url: str = Field(default="redis://127.0.0.1:56379/0", validation_alias="REDIS_URL")

    jwt_secret_key: str = Field(default="dev-change-me", validation_alias="JWT_SECRET_KEY")
    jwt_issuer: str = Field(default="securitypassport", validation_alias="JWT_ISSUER")
    jwt_access_token_minutes: int = Field(default=60, validation_alias="JWT_ACCESS_TOKEN_MINUTES")

    s3_endpoint: str = Field(validation_alias="S3_ENDPOINT")
    s3_access_key: str = Field(validation_alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(validation_alias="S3_SECRET_KEY")
    s3_bucket: str = Field(validation_alias="S3_BUCKET")
    s3_region: str = Field(default="us-east-1", validation_alias="S3_REGION")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()

if os.getenv("DEBUG_SETTINGS") == "1":
    print("=== SETTINGS DEBUG ===")
    print("cwd:", Path.cwd())
    print("REPO_ROOT:", REPO_ROOT)
    print("ENV_FILES:", ENV_FILES)
    print("os.getenv('REDIS_URL'):", os.getenv("REDIS_URL"))
    print("settings.redis_url:", settings.redis_url)
    print("======================")