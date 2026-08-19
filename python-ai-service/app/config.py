from __future__ import annotations

import os
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = SERVICE_DIR / ".env"


def load_env_file() -> None:
    """Load a local .env without overriding explicitly supplied environment variables."""
    if ENV_PATH.exists():
        for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    aliases = {
        "API_KEY": "OPENAI_API_KEY",
        "AI_MODEL": "OPENAI_MODEL",
        "AI_BASE_URL": "OPENAI_BASE_URL",
    }
    for source, target in aliases.items():
        if os.getenv(source) and not os.getenv(target):
            os.environ[target] = os.getenv(source, "")


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
