"""Tests for mysqlm.registry fallbacks."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mysqlm import constants
from mysqlm.registry import ConfigStore, InstanceRegistry


class RegistryFallbackTests(TestCase):
    def test_config_store_falls_back_when_system_path_unwritable(self) -> None:
        """ConfigStore should fall back to a user-writable config file."""

        with TemporaryDirectory() as tmpdir:
            xdg_config_home = Path(tmpdir) / "config"
            fallback_path = xdg_config_home / "mysqlm" / "config.yaml"
            original_mkdir = Path.mkdir

            def fake_mkdir(path_obj: Path, *args, **kwargs):  # type: ignore[override]
                if path_obj == constants.GLOBAL_CONFIG_PATHS[0].parent:
                    raise PermissionError("cannot create system config directory")
                return original_mkdir(path_obj, *args, **kwargs)

            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(xdg_config_home)}, clear=False):
                with patch.object(constants, "GLOBAL_CONFIG_PATHS", [Path("/etc/mysqlm/config.yaml")]):
                    with patch("pathlib.Path.mkdir", autospec=True) as mocked_mkdir:
                        mocked_mkdir.side_effect = fake_mkdir
                        store = ConfigStore()

            self.assertEqual(fallback_path, store.path)
            self.assertTrue(store.path.exists(), "Fallback config file should be created")

    def test_instance_registry_falls_back_when_system_dir_unwritable(self) -> None:
        """InstanceRegistry should fall back to a user-writable directory."""

        with TemporaryDirectory() as tmpdir:
            xdg_state_home = Path(tmpdir) / "state"
            fallback_dir = xdg_state_home / "mysqlm" / "instances"
            original_mkdir = Path.mkdir

            def fake_mkdir(path_obj: Path, *args, **kwargs):  # type: ignore[override]
                if path_obj == constants.INSTANCE_REGISTRY_DIR:
                    raise PermissionError("cannot create system registry directory")
                return original_mkdir(path_obj, *args, **kwargs)

            with patch.dict(os.environ, {"XDG_STATE_HOME": str(xdg_state_home)}, clear=False):
                with patch.object(constants, "INSTANCE_REGISTRY_DIR", Path("/etc/mysqlm/instances")):
                    with patch("pathlib.Path.mkdir", autospec=True) as mocked_mkdir:
                        mocked_mkdir.side_effect = fake_mkdir
                        registry = InstanceRegistry()

            self.assertEqual(fallback_dir, registry.directory)
            self.assertTrue(registry.directory.exists(), "Fallback registry directory should be created")

