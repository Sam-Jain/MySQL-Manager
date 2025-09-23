"""Backup and restore helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .logging_utils import get_logger
from .models import InstanceConfig
from .system import run_command
from .utils import ensure_directory, timestamp

LOGGER = get_logger(__name__)


def _read_root_password(instance: InstanceConfig) -> str:
    path = Path(instance.root_password_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Root password file {path} not found. Cannot perform backup/restore."
        )
    return path.read_text().strip()


def perform_backup(instance: InstanceConfig, destination_dir: Optional[Path] = None) -> Path:
    password = _read_root_password(instance)
    stamp = timestamp()
    target_dir = destination_dir or Path(instance.backup_dir) / stamp
    ensure_directory(target_dir, mode=0o750)
    outfile = target_dir / f"{instance.name}-{stamp}.sql"
    LOGGER.info("Writing backup to %s", outfile)
    run_command(
        [
            "mysqldump",
            "--single-transaction",
            "--routines",
            "--events",
            "--triggers",
            f"--socket={instance.socket}",
            "-uroot",
            f"-p{password}",
            "--all-databases",
        ],
        sudo=True,
        mask_secrets=[password],
        stdout_path=outfile,
    )
    LOGGER.info("Backup completed: %s", outfile)
    return outfile


def restore_backup(instance: InstanceConfig, backup_file: Path) -> None:
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file {backup_file} does not exist")
    password = _read_root_password(instance)
    LOGGER.info("Restoring backup from %s", backup_file)
    run_command(
        [
            "mysql",
            f"--socket={instance.socket}",
            "-uroot",
            f"-p{password}",
        ],
        sudo=True,
        mask_secrets=[password],
        stdin_path=backup_file,
    )
    LOGGER.info("Restore completed")
