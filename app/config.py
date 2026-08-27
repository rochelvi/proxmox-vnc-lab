from functools import lru_cache

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TemplateSpec(BaseModel):
    vmid: int
    label: str


def _parse_templates(value: str | None) -> list[TemplateSpec]:
    if value is None or not value.strip():
        return []
    templates: list[TemplateSpec] = []
    seen: set[int] = set()
    for entry in value.split(","):
        item = entry.strip()
        if not item or ":" not in item:
            raise ValueError(
                f"Invalid TEMPLATES entry {entry!r}; expected comma-separated vmid:label entries"
            )
        vmid_text, label = item.split(":", 1)
        try:
            vmid = int(vmid_text.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid TEMPLATES VMID {vmid_text!r}; VMID must be an integer") from exc
        label = label.strip()
        if vmid <= 0 or not label:
            raise ValueError(f"Invalid TEMPLATES entry {entry!r}; VMID must be positive and label non-empty")
        if vmid in seen:
            raise ValueError(f"Duplicate VMID {vmid} in TEMPLATES")
        seen.add(vmid)
        templates.append(TemplateSpec(vmid=vmid, label=label))
    return templates


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
    templates: str | None = None
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

    @field_validator("templates")
    @classmethod
    def validate_templates(cls, value: str | None) -> str | None:
        _parse_templates(value)
        return value

    def templates_list(self) -> list[TemplateSpec]:
        templates = _parse_templates(self.templates)
        if templates:
            return templates
        return [TemplateSpec(vmid=self.template_vmid, label=f"template-{self.template_vmid}")]

    def template_by_vmid(self, vmid: int) -> TemplateSpec | None:
        return next((template for template in self.templates_list() if template.vmid == vmid), None)


@lru_cache
def get_settings() -> Settings:
    return Settings()
