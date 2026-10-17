"""Explicit, locally scoped configuration. No external company credentials required."""
from dataclasses import dataclass
from pathlib import Path
import os


def truthy(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path(os.getenv("DATABASE_PATH", "./data/company.sqlite3"))
    artifacts_dir: Path = Path(os.getenv("ARTIFACTS_DIR", "./data/artifacts"))
    host: str = os.getenv("APP_HOST", "127.0.0.1")
    port: int = int(os.getenv("APP_PORT", "8000"))
    approval_threshold_cents: int = int(os.getenv("APPROVAL_THRESHOLD_CENTS", "100000"))
    browser_executable: str = os.getenv("BROWSER_EXECUTABLE", "")
    execution_mode: str = os.getenv("EXECUTION_MODE", "browser")
    headless: bool = truthy(os.getenv("HEADLESS", "true"))
    model_backend: str = os.getenv("MODEL_BACKEND", "gemma")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    ollama_timeout: float = float(os.getenv("OLLAMA_TIMEOUT", "45"))

    def __post_init__(self):
        if self.model_backend not in {"gemma", "rules"}:
            raise ValueError("MODEL_BACKEND must be gemma or rules; the old local checkpoint was removed")
        if not (1 <= self.ollama_timeout <= 300):
            raise ValueError("OLLAMA_TIMEOUT must be between 1 and 300 seconds")
        from app.agent.gemma import validate_ollama_url
        validate_ollama_url(self.ollama_url)
