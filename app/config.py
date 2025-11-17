"""Application configuration constants with environment overrides."""

from __future__ import annotations

import os
from typing import Optional


def _get_env(key: str, default: Optional[str] = None) -> str:
    """Return ``key`` from the environment or fall back to ``default``."""

    value = os.getenv(key)
    if value is None:
        if default is None:
            raise RuntimeError(f"Missing required environment variable: {key}")
        return default
    return value


DB_URL: str = _get_env("DATABASE_URL", "sqlite:///./exam.db")
PASS_PERCENT: float = float(os.getenv("PASS_PERCENT", "60"))
PAGE_SIZE: int = int(os.getenv("PAGE_SIZE", "10"))
SECRET_KEY: str = _get_env("SECRET_KEY", "exam-workshop-secret")
