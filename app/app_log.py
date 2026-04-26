"""Basic file logging for HauntOS."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "hauntos.log"


def setup_logging() -> None:
    """Configure a small rotating app log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    for handler in root_logger.handlers:
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == LOG_FILE:
            return

    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=256_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger.addHandler(handler)


def recent_lines(limit: int = 80, errors_only: bool = False) -> list[str]:
    """Return recent log lines, optionally filtering for warnings and errors."""
    if not LOG_FILE.exists():
        return []

    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    if errors_only:
        lines = [
            line
            for line in lines
            if " ERROR " in line or " WARNING " in line or " CRITICAL " in line
        ]

    return lines[-limit:]
