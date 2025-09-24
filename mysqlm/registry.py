"""Instance registry and global configuration storage."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import yaml

from . import constants
from .logging_utils import get_logger
from .models import InstanceConfig

LOGGER = get_logger(__name__)


class ConfigStore:
    """Manage the global mysqlm configuration file."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or self._select_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save({})

    def _select_path(self) -> Path:
        for path in constants.GLOBAL_CONFIG_PATHS:
            parent = path.parent
            if os.access(parent, os.W_OK) or not parent.exists():
                return path
        fallback = Path.home() / ".config" / "mysqlm" / "config.yaml"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        return yaml.safe_load(self.path.read_text()) or {}

    def save(self, data: dict) -> None:
        self.path.write_text(yaml.safe_dump(data, sort_keys=False))
        os.chmod(self.path, 0o640)


class InstanceRegistry:
    """YAML-based registry for MySQL instances."""

    def __init__(self, directory: Optional[Path] = None) -> None:
        self.directory = directory or constants.INSTANCE_REGISTRY_DIR
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.directory / f"{name}.yaml"

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def load(self, name: str) -> InstanceConfig:
        path = self._path(name)
        if not path.exists():
            raise FileNotFoundError(f"Instance '{name}' is not registered")
        data = yaml.safe_load(path.read_text()) or {}
        return InstanceConfig.from_dict(data)

    def save(self, instance: InstanceConfig) -> None:
        path = self._path(instance.name)
        instance.last_modified = datetime.utcnow().isoformat()
        data = instance.to_dict()
        path.write_text(yaml.safe_dump(data, sort_keys=False))
        os.chmod(path, 0o640)

    def delete(self, name: str) -> None:
        path = self._path(name)
        if path.exists():
            path.unlink()

    def list_instances(self) -> Iterable[InstanceConfig]:
        for path in sorted(self.directory.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text()) or {}
                yield InstanceConfig.from_dict(data)
            except Exception as exc:  # pragma: no cover
                LOGGER.error("Failed to parse %s: %s", path, exc)
