"""Systemd unit management for mysqlm."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .logging_utils import get_logger
from .system import run_command

LOGGER = get_logger(__name__)


class SystemdManager:
    """Helper for managing systemd service units."""

    def __init__(self, unit_dir: Path = Path("/etc/systemd/system")) -> None:
        self.unit_dir = unit_dir

    def unit_path(self, unit_name: str) -> Path:
        return self.unit_dir / unit_name

    def write_unit(self, unit_name: str, content: str, reload: bool = True) -> Path:
        path = self.unit_path(unit_name)
        path.write_text(content)
        path.chmod(0o644)
        if reload:
            self.daemon_reload()
        return path

    def daemon_reload(self) -> None:
        run_command(["systemctl", "daemon-reload"], sudo=True)

    def enable(self, unit_name: str) -> None:
        run_command(["systemctl", "enable", unit_name], sudo=True)

    def disable(self, unit_name: str) -> None:
        run_command(["systemctl", "disable", unit_name], sudo=True, check=False)

    def start(self, unit_name: str) -> None:
        run_command(["systemctl", "start", unit_name], sudo=True)

    def stop(self, unit_name: str) -> None:
        run_command(["systemctl", "stop", unit_name], sudo=True, check=False)

    def restart(self, unit_name: str) -> None:
        run_command(["systemctl", "restart", unit_name], sudo=True)

    def status(self, unit_name: str) -> str:
        result = run_command(
            ["systemctl", "status", unit_name, "--no-pager"],
            sudo=True,
            capture_output=True,
            check=False,
        )
        return result.stdout
