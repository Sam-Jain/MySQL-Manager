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
        selected_path = path or self._select_path()
        self.path = self._ensure_path(selected_path, explicit=path is not None)
        if not self.path.exists():
            self.save({})

    def _select_path(self) -> Path:
        for path in constants.GLOBAL_CONFIG_PATHS:
            parent = path.parent
            if parent.exists():
                if os.access(parent, os.W_OK):
                    return path
            else:
                ancestor = parent.parent
                if ancestor != parent and ancestor.exists() and os.access(ancestor, os.W_OK):
                    return path
        return self._user_config_path()

    def _ensure_path(self, candidate: Path, *, explicit: bool) -> Path:
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return candidate
        except PermissionError:
            if explicit:
                raise
            fallback = self._user_config_path()
            fallback.parent.mkdir(parents=True, exist_ok=True)
            return fallback

    def _user_config_path(self) -> Path:
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config_home:
            base = Path(xdg_config_home)
        else:
            base = Path.home() / ".config"
        return base / "mysqlm" / "config.yaml"

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
        selected_directory = directory or constants.INSTANCE_REGISTRY_DIR
        self.directory = self._ensure_directory(selected_directory, explicit=directory is not None)

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

    def _ensure_directory(self, directory: Path, *, explicit: bool) -> Path:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            return directory
        except PermissionError:
            if explicit:
                raise
            fallback = self._user_registry_dir()
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback

    def _user_registry_dir(self) -> Path:
        xdg_state_home = os.environ.get("XDG_STATE_HOME")
        if xdg_state_home:
            base = Path(xdg_state_home)
        else:
            base = Path.home() / ".local" / "state"
        return base / "mysqlm" / "instances"
