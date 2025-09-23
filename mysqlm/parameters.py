"""Configuration parameter management."""
from __future__ import annotations

import configparser
import re
from pathlib import Path
from typing import Dict, Tuple

from rich.table import Table

from .logging_utils import get_logger
from .models import InstanceConfig
from .system import run_command
from .utils import console

LOGGER = get_logger(__name__)

NUMERIC_PARAMS = {
    "max_connections",
    "innodb_buffer_pool_instances",
    "innodb_io_capacity",
    "thread_cache_size",
}

SIZE_PARAMS = {
    "innodb_buffer_pool_size",
    "innodb_log_file_size",
    "tmp_table_size",
    "innodb_log_buffer_size",
}

BOOLEAN_PARAMS = {
    "slow_query_log",
    "skip_name_resolve",
    "log_bin",
}

SIZE_PATTERN = re.compile(r"^\d+[KMGTP]?$", re.IGNORECASE)


def _read_config(instance: InstanceConfig) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.optionxform = str  # preserve case
    parser.read(instance.config_path)
    if "mysqld" not in parser:
        parser["mysqld"] = {}
    return parser


def validate_parameter(name: str, value: str) -> None:
    if name in NUMERIC_PARAMS and not value.isdigit():
        raise ValueError(f"Parameter {name} expects a numeric value")
    if name in SIZE_PARAMS and not (value.isdigit() or SIZE_PATTERN.match(value)):
        raise ValueError(
            f"Parameter {name} expects size format such as 512M or 4G"
        )
    if name in BOOLEAN_PARAMS:
        normalized = value.lower()
        if normalized not in {"on", "off", "true", "false", "1", "0"}:
            raise ValueError(f"Parameter {name} expects a boolean value (ON/OFF)")


def set_parameter(instance: InstanceConfig, parameter: str, value: str) -> None:
    parser = _read_config(instance)
    validate_parameter(parameter, value)
    parser["mysqld"][parameter] = value
    with open(instance.config_path, "w") as fh:
        parser.write(fh)
    LOGGER.info("Parameter %s updated in %s", parameter, instance.config_path)


def show_parameters(instance: InstanceConfig, live: bool = False) -> Tuple[Dict[str, str], Dict[str, str]]:
    parser = _read_config(instance)
    configured = dict(parser["mysqld"]) if parser.has_section("mysqld") else {}
    live_values: Dict[str, str] = {}
    if live and configured:
        if not Path(instance.root_password_path).exists():
            LOGGER.warning("Root password file %s not found; skipping live values", instance.root_password_path)
        else:
            password = Path(instance.root_password_path).read_text().strip()
            if password:
                params = "','".join(configured.keys())
                query = f"SHOW VARIABLES WHERE Variable_name IN ('{params}')"
                result = run_command(
                    [
                        "mysql",
                        f"--socket={instance.socket}",
                        "-uroot",
                        f"-p{password}",
                        "--batch",
                        "--skip-column-names",
                        "-e",
                        query,
                    ],
                    sudo=True,
                    mask_secrets=[password],
                    check=False,
                )
                for line in result.stdout.splitlines():
                    if "\t" in line:
                        key, val = line.split("\t", 1)
                        live_values[key] = val
    return configured, live_values


def display_parameters(instance: InstanceConfig, configured: Dict[str, str], live: Dict[str, str]) -> None:
    table = Table(title=f"Parameters for {instance.name}")
    table.add_column("Parameter", style="bold")
    table.add_column("Configured Value")
    table.add_column("Live Value", style="cyan")
    for key, value in sorted(configured.items()):
        table.add_row(key, value, live.get(key, ""))
    console.print(table)
