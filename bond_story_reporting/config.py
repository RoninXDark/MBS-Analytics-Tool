from __future__ import annotations

from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"


def load_yaml(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_default_config() -> dict:
    return load_yaml(CONFIG_DIR / "default_config.yaml")


def get_report_templates() -> dict:
    return load_yaml(CONFIG_DIR / "report_templates.yaml")
