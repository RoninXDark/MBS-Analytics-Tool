from __future__ import annotations

from pathlib import Path
import json
from datetime import datetime


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def slugify(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def write_json(path: str | Path, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
