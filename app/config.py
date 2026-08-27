from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    pve_host: str = "localhost"
    pve_port: int = 8006
    pve_token_id: str | None = None
    pve_token_secret: str | None = None
    pve_user: str | None = None
    pve_password: str | None = None
    pve_verify_ssl: bool = False
    pve_node: str = "pve"
    template_vmid: int = 9000
    clone_vmid_min: int = 100
    clone_vmid_max: int = 999
    clone_full: bool = False
    clone_storage: str | None = None
    clone_pool: str | None = None
    clone_name_prefix: str = "intern"
    max_vms_per_user: int = 1
    database_url: str = "sqlite:///./data/app.db"
    jwt_secret: str = "change-this-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    auth_provider: str = "local"
    log_level: str = "INFO"
    task_timeout_seconds: int = 300
    task_poll_interval: float = 2.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
