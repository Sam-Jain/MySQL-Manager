"""Project-wide constants."""
from __future__ import annotations

from pathlib import Path


GLOBAL_CONFIG_PATHS = [
    Path("/etc/mysqlm/config.yaml"),
    Path("/usr/local/etc/mysqlm/config.yaml"),
]

INSTANCE_REGISTRY_DIR = Path("/etc/mysqlm/instances")

DEFAULT_DATA_ROOT = Path("/var/lib/mysql-instances")
DEFAULT_CONFIG_ROOT = Path("/etc/mysql-instances")
DEFAULT_LOG_ROOT = Path("/var/log/mysql")
DEFAULT_RUNTIME_ROOT = Path("/var/run")
DEFAULT_BACKUP_ROOT = Path("/var/backups/mysql")
DEFAULT_LOG_DIR = Path("/var/log/mysqlm")

DEFAULT_SOCKET_TEMPLATE = "/var/run/mysql-{name}/mysqld.sock"
DEFAULT_ERROR_LOG_TEMPLATE = "/var/log/mysql-{name}/mysqld.log"
DEFAULT_SLOW_LOG_TEMPLATE = "/var/log/mysql-{name}/mysql-slow.log"
DEFAULT_PID_TEMPLATE = "/var/run/mysql-{name}/mysqld.pid"
DEFAULT_SYSTEMD_UNIT_TEMPLATE = "mysqld-{name}.service"

SUPPORTED_MINORS = {"5.7", "8.0"}

MYSQL_RELEASE_RPMS = {
    "8.0": "https://repo.mysql.com/mysql80-community-release-el7-5.noarch.rpm",
    "5.7": "https://repo.mysql.com/mysql57-community-release-el7-11.noarch.rpm",
}

MYSQL_PACKAGE = "mysql-community-server"
MYSQL_CLIENT_PACKAGE = "mysql-community-client"
