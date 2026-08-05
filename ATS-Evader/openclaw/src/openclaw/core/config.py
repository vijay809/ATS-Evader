"""Configuration models owned by the runtime."""

from pathlib import Path

from pydantic import BaseModel, Field


class RuntimeSettings(BaseModel):
    """Settings that are safe to pass to the core runtime."""

    data_dir: Path = Field(default_factory=lambda: Path.home() / ".openclaw")
    database_name: str = "openclaw.sqlite"
    log_level: str = "INFO"

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.database_name
