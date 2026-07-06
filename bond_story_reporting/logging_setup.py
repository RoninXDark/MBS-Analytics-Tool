from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .runtime_paths import resolve_default_logs_dir
from .utils import ensure_dir


def configure_logging(
    app_name: str = "bond_story_reporting",
    logs_dir: str | Path | None = None,
    level: int = logging.INFO,
) -> Path:
    log_root = ensure_dir(logs_dir or resolve_default_logs_dir())
    log_path = Path(log_root) / f"{app_name}.log"

    logger = logging.getLogger()
    logger.setLevel(level)

    has_file_handler = any(
        isinstance(h, RotatingFileHandler) and Path(getattr(h, "baseFilename", "")) == log_path
        for h in logger.handlers
    )
    if not has_file_handler:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    has_console_handler = any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
    if not has_console_handler:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(console_handler)

    return log_path
