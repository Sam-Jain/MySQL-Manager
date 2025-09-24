"""Upgrade workflows for MySQL instances."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from .backups import perform_backup
from .logging_utils import get_logger
from .models import InstanceConfig
from .mysql_repository import MySQLRepositoryManager
from .registry import InstanceRegistry
from .system import run_command, wait_for_socket
from .utils import human_readable_size

LOGGER = get_logger(__name__)


class UpgradeManager:
    """Handle in-place upgrades of MySQL instances."""

    def __init__(self, registry: InstanceRegistry) -> None:
        self.registry = registry
        self.repo = MySQLRepositoryManager()

    def _check_disk_space(self, path: Path) -> None:
        usage = shutil.disk_usage(path)
        LOGGER.info(
            "Disk space for %s: total=%s used=%s free=%s",
            path,
            human_readable_size(usage.total),
            human_readable_size(usage.used),
            human_readable_size(usage.free),
        )
        if usage.free < 5 * 1024 * 1024 * 1024:  # 5 GiB
            LOGGER.warning("Free space below 5 GiB. Ensure there is enough space for upgrade")

    def upgrade_instance(
        self,
        instance_name: str,
        target_minor: str,
        *,
        take_backup: bool = True,
        assume_yes: bool = False,
    ) -> InstanceConfig:
        instance = self.registry.load(instance_name)
        self._check_disk_space(Path(instance.datadir))
        if take_backup:
            perform_backup(instance)
        # stop service
        from .instance_manager import InstanceManager  # avoid circular import

        manager = InstanceManager(self.registry)
        manager.stop_instance(instance_name)

        version = self.repo.install_version(target_minor)
        LOGGER.info("Packages upgraded to %s", version.version)

        manager.start_instance(instance_name)
        wait_for_socket(Path(instance.socket), timeout=120)

        password = Path(instance.root_password_path).read_text().strip() if instance.root_password_path else ""
        if not password:
            LOGGER.warning("Root password unavailable; skipping mysql_upgrade. Run manually.")
        else:
            run_command(
                [
                    "mysql_upgrade",
                    f"--socket={instance.socket}",
                    "-uroot",
                    f"-p{password}",
                ],
                sudo=True,
                mask_secrets=[password],
            )
            LOGGER.info("mysql_upgrade completed")

        manager.restart_instance(instance_name)
        instance.mysql_version = version.version
        self.registry.save(instance)
        return instance
