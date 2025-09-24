"""Utility helpers for mysqlm."""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import questionary
from rich.console import Console
from rich.table import Table

console = Console()


def detect_package_manager() -> str:
    """Return the preferred package manager (dnf or yum)."""

    for candidate in ("dnf", "yum"):
        if shutil.which(candidate):
            return candidate
    raise RuntimeError("Neither yum nor dnf is available on this system")


def confirm(question: str, default: bool = True, assume_yes: bool = False) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        return default
    return bool(questionary.confirm(question, default=default).ask())


def choose(question: str, choices: Iterable[str]) -> Optional[str]:
    if not sys.stdin.isatty():
        return next(iter(choices), None)
    return questionary.select(question, choices=list(choices)).ask()


def info_table(title: str, rows: Iterable[tuple[str, str]]) -> None:
    table = Table(title=title, show_header=False)
    table.add_column("Property", style="bold")
    table.add_column("Value")
    for key, value in rows:
        table.add_row(key, value)
    console.print(table)


def timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S")


def human_readable_size(num_bytes: int) -> str:
    step_to_greater_unit = 1024.0
    num = float(num_bytes)
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if num < step_to_greater_unit:
            return f"{num:3.1f} {unit}"
        num /= step_to_greater_unit
    return f"{num:.1f} PiB"


def ensure_directory(path: Path, mode: int = 0o750) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(mode)
