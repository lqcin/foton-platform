from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("FOTON_DATA_DIR", BASE_DIR / "data")).resolve()
STORAGE_DIR = DATA_DIR / "storage"
VIDEO_DIR = STORAGE_DIR / "videos"
REPORT_DIR = STORAGE_DIR / "reports"
CAD_DIR = STORAGE_DIR / "cad"
DB_PATH = DATA_DIR / "foton.db"

for directory in (DATA_DIR, STORAGE_DIR, VIDEO_DIR, REPORT_DIR, CAD_DIR):
    directory.mkdir(parents=True, exist_ok=True)

def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

SEED_DEMO = env_bool("FOTON_SEED_DEMO", False)
SESSION_HOURS = int(os.getenv("FOTON_SESSION_HOURS", "12"))
RESET_TOKEN_MINUTES = int(os.getenv("FOTON_RESET_TOKEN_MINUTES", "30"))

def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} ortam degiskeni gerekli")
    return value
