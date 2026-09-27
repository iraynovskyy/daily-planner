from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root, so paths don't depend on the directory the app is started from.
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    database_url: str = "sqlite:///data/planner.db"
    # Defaults for a fresh database; None → seed.local.toml if present, else seed.example.toml.
    seed_file: Path | None = None

    # Signs the session cookie: anyone who knows it can forge a login, so keep it out of git.
    # None → a random key per process (fine locally; everyone is logged out on restart).
    secret_key: str | None = None
    # Send the session cookie over HTTPS only. Must be true in production.
    session_https_only: bool = False
    session_max_age_days: int = 30

    @field_validator("database_url")
    @classmethod
    def _anchor_sqlite_path(cls, url: str) -> str:
        # Relative SQLite paths ("sqlite:///data/x.db") resolve against BASE_DIR, not the CWD.
        prefix = "sqlite:///"
        path = url.removeprefix(prefix)
        if not url.startswith(prefix) or path == ":memory:" or Path(path).is_absolute():
            return url
        return f"{prefix}{BASE_DIR / path}"

    @property
    def seed_path(self) -> Path:
        if self.seed_file is not None:
            return self.seed_file if self.seed_file.is_absolute() else BASE_DIR / self.seed_file
        local = BASE_DIR / "seed.local.toml"
        return local if local.exists() else BASE_DIR / "seed.example.toml"


settings = Settings()
