"""Data models for mysqlm."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from . import constants


@dataclass
class InstanceConfig:
    """Representation of a managed MySQL instance."""

    name: str
    port: int
    socket: str
    datadir: str
    config_path: str
    log_dir: str
    error_log: str
    slow_log: str
    pid_file: str
    runtime_dir: str
    backup_dir: str
    mysql_version: Optional[str]
    created_at: str
    last_modified: str
    systemd_unit: str
    root_password_path: str
    root_password_set: bool = False

    @property
    def config_dir(self) -> str:
        return str(Path(self.config_path).parent)

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "port": self.port,
            "socket": self.socket,
            "datadir": self.datadir,
            "config_path": self.config_path,
            "log_dir": self.log_dir,
            "error_log": self.error_log,
            "slow_log": self.slow_log,
            "pid_file": self.pid_file,
            "runtime_dir": self.runtime_dir,
            "backup_dir": self.backup_dir,
            "mysql_version": self.mysql_version,
            "created_at": self.created_at,
            "last_modified": self.last_modified,
            "systemd_unit": self.systemd_unit,
            "root_password_path": self.root_password_path,
            "root_password_set": self.root_password_set,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "InstanceConfig":
        return cls(
            name=str(data["name"]),
            port=int(data["port"]),
            socket=str(data["socket"]),
            datadir=str(data["datadir"]),
            config_path=str(data["config_path"]),
            log_dir=str(data["log_dir"]),
            error_log=str(data["error_log"]),
            slow_log=str(data["slow_log"]),
            pid_file=str(data["pid_file"]),
            runtime_dir=str(data["runtime_dir"]),
            backup_dir=str(data.get("backup_dir", constants.DEFAULT_BACKUP_ROOT)),
            mysql_version=data.get("mysql_version"),
            created_at=str(data.get("created_at", datetime.utcnow().isoformat())),
            last_modified=str(data.get("last_modified", datetime.utcnow().isoformat())),
            systemd_unit=str(data["systemd_unit"]),
            root_password_path=str(data.get("root_password_path", "")),
            root_password_set=bool(data.get("root_password_set", False)),
        )
