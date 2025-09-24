"""Tests for mysqlm.logging_utils."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable
from unittest import TestCase
from unittest.mock import patch

from logging.handlers import RotatingFileHandler

from mysqlm import constants, logging_utils


def _reset_logging_state() -> None:
    """Reset global logging state for tests."""

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        handler.close()
        root_logger.removeHandler(handler)
    logging_utils._LOGGER_INITIALIZED = False


class ConfigureLoggingTests(TestCase):
    def setUp(self) -> None:  # noqa: D401 - standard unittest hook
        _reset_logging_state()
        self.addCleanup(_reset_logging_state)

    def _get_file_handlers(self, logger: logging.Logger) -> Iterable[RotatingFileHandler]:
        return [
            handler
            for handler in logger.handlers
            if isinstance(handler, RotatingFileHandler)
        ]

    def test_configure_logging_falls_back_when_default_unwritable(self) -> None:
        """configure_logging should use a user-writable fallback on PermissionError."""

        with TemporaryDirectory() as tmpdir:
            fallback_dir = Path(tmpdir) / "mysqlm"
            original_mkdir = Path.mkdir

            def fake_mkdir(path_obj: Path, *args, **kwargs):
                if path_obj == constants.DEFAULT_LOG_DIR:
                    raise PermissionError("cannot create default log dir")
                return original_mkdir(path_obj, *args, **kwargs)

            with patch.dict(os.environ, {"XDG_STATE_HOME": tmpdir}, clear=False):
                with patch("pathlib.Path.mkdir", autospec=True) as mocked_mkdir:
                    mocked_mkdir.side_effect = fake_mkdir
                    logger = logging_utils.configure_logging()

            self.assertTrue(fallback_dir.exists(), "Fallback log directory should be created")
            file_handlers = list(self._get_file_handlers(logger))
            self.assertEqual(1, len(file_handlers))
            expected_path = fallback_dir / "mysqlm.log"
            self.assertEqual(str(expected_path), file_handlers[0].baseFilename)

    def test_configure_logging_honors_explicit_log_path(self) -> None:
        """Providing log_path should bypass fallback logic."""

        with TemporaryDirectory() as tmpdir:
            explicit_path = Path(tmpdir) / "custom.log"
            logger = logging_utils.configure_logging(log_path=explicit_path)

        file_handlers = list(self._get_file_handlers(logger))
        self.assertEqual(1, len(file_handlers))
        self.assertEqual(str(explicit_path), file_handlers[0].baseFilename)
