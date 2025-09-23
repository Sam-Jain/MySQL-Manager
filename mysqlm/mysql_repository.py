"""MySQL repository and package management."""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from typing import List

from . import constants
from .logging_utils import get_logger
from .system import run_command
from .utils import detect_package_manager

LOGGER = get_logger(__name__)


@dataclass
class PackageVersion:
    version: str
    release: str

    @property
    def full_version(self) -> str:
        return f"{self.version}-{self.release}" if self.release else self.version


class MySQLRepositoryManager:
    """Manage the official Oracle MySQL yum repository."""

    def __init__(self) -> None:
        self.pkg_mgr = detect_package_manager()

    def _package_cmd(self, *args: str) -> List[str]:
        return [self.pkg_mgr, *args]

    def check_mariadb_conflict(self) -> None:
        result = run_command(["rpm", "-qa"], capture_output=True, check=False)
        conflicts = [line for line in result.stdout.splitlines() if line.lower().startswith("mariadb")]
        if conflicts:
            raise RuntimeError(
                "MariaDB packages detected ({}). Please remove them before installing MySQL.".format(
                    ", ".join(conflicts)
                )
            )

    def release_installed(self) -> bool:
        result = run_command(["rpm", "-qa"], capture_output=True, check=False)
        return any("mysql" in line and "community-release" in line for line in result.stdout.splitlines())

    def install_release_package(self, minor: str) -> None:
        url = constants.MYSQL_RELEASE_RPMS.get(minor)
        if not url:
            raise ValueError(f"Unsupported minor version {minor}")
        run_command(["rpm", "-Uvh", url], sudo=True)

    def enable_minor_repo(self, minor: str) -> None:
        numeric = minor.replace(".", "")
        repo = f"mysql{numeric}-community"
        config_manager = shutil.which("yum-config-manager")
        if not config_manager:
            LOGGER.warning("yum-config-manager not found. Ensure the desired MySQL repo is enabled manually.")
            return
        disable_pattern = "mysql*-community"
        run_command([config_manager, "--disable", disable_pattern], sudo=True, check=False)
        run_command([config_manager, "--enable", repo], sudo=True)

    def list_available_versions(self) -> List[PackageVersion]:
        cmd = self._package_cmd("list", "--showduplicates", constants.MYSQL_PACKAGE)
        result = run_command(cmd, capture_output=True)
        versions: List[PackageVersion] = []
        for line in result.stdout.splitlines():
            if constants.MYSQL_PACKAGE in line and "@" not in line:
                parts = line.split()
                if len(parts) >= 2:
                    version_release = parts[1]
                    if "-" in version_release:
                        version, release = version_release.split("-", 1)
                    else:
                        version, release = version_release, ""
                    versions.append(PackageVersion(version=version, release=release))
        if not versions:
            LOGGER.warning("No MySQL versions discovered in repository output")
        return versions

    def resolve_latest_patch(self, minor: str) -> PackageVersion:
        available = self.list_available_versions()
        candidates = [ver for ver in available if ver.version.startswith(minor)]
        if not candidates:
            raise ValueError(f"No versions found for minor {minor}")
        candidates.sort(key=lambda v: [int(x) for x in re.findall(r"\d+", v.version)], reverse=True)
        return candidates[0]

    def install_version(self, minor: str) -> PackageVersion:
        self.check_mariadb_conflict()
        if not self.release_installed():
            self.install_release_package(minor)
        self.enable_minor_repo(minor)
        version = self.resolve_latest_patch(minor)
        pkg_name = f"{constants.MYSQL_PACKAGE}-{version.version}"
        run_command(self._package_cmd("install", "-y", pkg_name), sudo=True)
        run_command(self._package_cmd("install", "-y", constants.MYSQL_CLIENT_PACKAGE), sudo=True)
        return version

    def upgrade_packages(self) -> None:
        run_command(self._package_cmd("update", "-y", constants.MYSQL_PACKAGE), sudo=True)
        run_command(self._package_cmd("update", "-y", constants.MYSQL_CLIENT_PACKAGE), sudo=True)
