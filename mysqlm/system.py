"""System utilities for executing commands and interacting with the OS."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Iterable, Optional, Sequence

from .logging_utils import get_logger

LOGGER = get_logger(__name__)


class CommandError(RuntimeError):
    """Raised when a system command fails."""

    def __init__(self, command: Sequence[str], returncode: int, stdout: str, stderr: str):
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(self.__str__())

    def __str__(self) -> str:  # pragma: no cover - formatting method
        return (
            f"Command '{' '.join(self.command)}' failed with exit code {self.returncode}."
            f" Stdout: {self.stdout.strip()} Stderr: {self.stderr.strip()}"
        )


def _mask(text: str, mask_secrets: Optional[Iterable[str]]) -> str:
    if not mask_secrets:
        return text
    masked = text
    for secret in mask_secrets:
        if secret:
            masked = masked.replace(secret, "******")
    return masked


def run_command(
    command: Sequence[str],
    *,
    sudo: bool = False,
    check: bool = True,
    capture_output: bool = True,
    env: Optional[dict] = None,
    cwd: Optional[Path] = None,
    timeout: Optional[int] = None,
    mask_secrets: Optional[Iterable[str]] = None,
    stdout_path: Optional[Path] = None,
    stderr_path: Optional[Path] = None,
    stdin_path: Optional[Path] = None,
) -> subprocess.CompletedProcess:
    """Execute a system command, raising :class:`CommandError` when it fails."""

    cmd = list(command)
    if sudo and os.geteuid() != 0:
        cmd = ["sudo"] + cmd
    display_cmd = _mask(" ".join(cmd), mask_secrets)
    LOGGER.debug("Executing command: %s", display_cmd)

    stdout_handle = None
    stderr_handle = None
    stdin_handle = None
    stdout = subprocess.PIPE if capture_output and not stdout_path else None
    stderr = subprocess.PIPE if capture_output and not stderr_path else None
    stdin = None
    if stdout_path:
        stdout_handle = open(stdout_path, "wb")
        stdout = stdout_handle
    if stderr_path:
        stderr_handle = open(stderr_path, "wb")
        stderr = stderr_handle
    if stdin_path:
        stdin_handle = open(stdin_path, "rb")
        stdin = stdin_handle

    try:
        result = subprocess.run(
            cmd,
            check=False,
            stdout=stdout,
            stderr=stderr,
            stdin=stdin,
            text=not stdout_path,
            env=env,
            cwd=str(cwd) if cwd else None,
            timeout=timeout,
        )
    finally:
        if stdout_handle:
            stdout_handle.close()
        if stderr_handle:
            stderr_handle.close()
        if stdin_handle:
            stdin_handle.close()

    if check and result.returncode != 0:
        stdout_text = result.stdout if capture_output and not stdout_path else ""
        stderr_text = result.stderr if capture_output and not stderr_path else ""
        raise CommandError(cmd, result.returncode, stdout_text or "", stderr_text or "")

    LOGGER.debug(
        "Command finished rc=%s stdout=%s stderr=%s",
        result.returncode,
        _mask(result.stdout.strip(), mask_secrets) if getattr(result, "stdout", None) else "",
        _mask(result.stderr.strip(), mask_secrets) if getattr(result, "stderr", None) else "",
    )
    return result


def wait_for_socket(path: Path, timeout: int = 60, expect_exists: bool = True) -> None:
    """Wait for a UNIX socket file to appear or disappear."""

    LOGGER.debug("Waiting for socket %s (expect_exists=%s)", path, expect_exists)
    deadline = time.time() + timeout
    while time.time() < deadline:
        exists = path.exists()
        if exists and expect_exists:
            return
        if not exists and not expect_exists:
            return
        time.sleep(1)
    state = "appear" if expect_exists else "disappear"
    raise TimeoutError(f"Socket {path} did not {state} within {timeout} seconds")


def is_root() -> bool:
    return os.geteuid() == 0


def ensure_root() -> None:
    if not is_root():
        raise PermissionError("This action requires root privileges. Please re-run with sudo.")
