"""Logging helpers for mysqlm."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from rich.logging import RichHandler

from . import constants

_LOGGER_INITIALIZED = False


def configure_logging(verbose: bool = False, log_path: Optional[Path] = None) -> logging.Logger:
    """Configure root logger with console and rotating file handlers."""

    global _LOGGER_INITIALIZED
    logger = logging.getLogger()
    if _LOGGER_INITIALIZED:
        if verbose:
            for handler in logger.handlers:
                if isinstance(handler, RichHandler):
                    handler.setLevel(logging.DEBUG)
        return logger

    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    console_handler = RichHandler(rich_tracebacks=True, show_time=False, show_path=False)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(console_handler)

    log_path = log_path or (constants.DEFAULT_LOG_DIR / "mysqlm.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(log_path, maxBytes=5_000_000, backupCount=5)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(file_handler)

    _LOGGER_INITIALIZED = True
    logger.debug("Logging initialized. Log file: %s", log_path)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return module logger after ensuring logging is configured."""

    if not _LOGGER_INITIALIZED:
        configure_logging()
    return logging.getLogger(name)
