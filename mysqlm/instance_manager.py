"""MySQL instance lifecycle management."""
from __future__ import annotations

import grp
import os
import pwd
import secrets
import shutil
import socket
import stat
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from . import constants
from .logging_utils import get_logger
from .models import InstanceConfig
from .registry import InstanceRegistry
from .system import run_command, wait_for_socket
from .systemd import SystemdManager
from .utils import ensure_directory

LOGGER = get_logger(__name__)


class InstanceManager:
    """Create and manage MySQL server instances."""

    def __init__(self, registry: InstanceRegistry, systemd: Optional[SystemdManager] = None) -> None:
        self.registry = registry
        self.systemd = systemd or SystemdManager()

    # ----------------------- helpers -----------------------
    def _generate_paths(self, name: str) -> Dict[str, Path]:
        return {
            "datadir": constants.DEFAULT_DATA_ROOT / name,
            "conf_dir": constants.DEFAULT_CONFIG_ROOT / name,
            "config_path": constants.DEFAULT_CONFIG_ROOT / name / "my.cnf",
            "log_dir": Path(constants.DEFAULT_ERROR_LOG_TEMPLATE.format(name=name)).parent,
            "runtime_dir": Path(constants.DEFAULT_SOCKET_TEMPLATE.format(name=name)).parent,
            "socket": Path(constants.DEFAULT_SOCKET_TEMPLATE.format(name=name)),
            "error_log": Path(constants.DEFAULT_ERROR_LOG_TEMPLATE.format(name=name)),
            "slow_log": Path(constants.DEFAULT_SLOW_LOG_TEMPLATE.format(name=name)),
            "pid_file": Path(constants.DEFAULT_PID_TEMPLATE.format(name=name)),
            "backup_dir": constants.DEFAULT_BACKUP_ROOT / name,
        }

    def _ensure_paths(self, paths: Dict[str, Path]) -> None:
        for key in ("datadir", "conf_dir", "log_dir", "runtime_dir", "backup_dir"):
            ensure_directory(paths[key])
        for file_key in ("error_log", "slow_log", "pid_file", "socket"):
            ensure_directory(paths[file_key].parent)
            if file_key in ("error_log", "slow_log") and not paths[file_key].exists():
                paths[file_key].touch()
                os.chmod(paths[file_key], 0o640)

    def _set_permissions(self, paths: Dict[str, Path]) -> None:
        try:
            mysql_user = pwd.getpwnam("mysql")
            mysql_group = grp.getgrnam("mysql")
            uid = mysql_user.pw_uid
            gid = mysql_group.gr_gid
        except KeyError:
            LOGGER.warning("MySQL user or group not found. Directories will remain owned by current user.")
            uid = gid = None
        for directory in (
            paths["datadir"],
            paths["log_dir"],
            paths["runtime_dir"],
            paths["backup_dir"],
            paths["conf_dir"],
        ):
            if uid is not None:
                shutil.chown(directory, user=uid, group=gid)
            os.chmod(directory, 0o750)

    def suggest_port(self) -> int:
        ports = {instance.port for instance in self.registry.list_instances()}
        candidate = 3306
        while candidate in ports:
            candidate += 1
        return candidate

    def _ensure_port_available(self, port: int) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(f"Port {port} is already in use")

    def _render_config(self, port: int, paths: Dict[str, Path]) -> str:
        return f"""
[mysqld]
user=mysql
datadir={paths['datadir']}
socket={paths['socket']}
log-error={paths['error_log']}
slow_query_log=ON
slow_query_log_file={paths['slow_log']}
pid-file={paths['pid_file']}
port={port}

# Default tuning (adjust via mysqlm set-parameter)
innodb_buffer_pool_size=1G
max_connections=200
sql_mode=STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION

[client]
port={port}
socket={paths['socket']}
""".strip()

    def _write_config(self, config: str, path: Path) -> None:
        ensure_directory(path.parent)
        path.write_text(config)
        os.chmod(path, 0o640)

    def _initialize_datadir(self, paths: Dict[str, Path]) -> None:
        datadir = paths["datadir"]
        if any(datadir.iterdir()):
            LOGGER.info("Datadir %s already initialized", datadir)
            return
        cmd = [
            "mysqld",
            "--initialize",
            f"--datadir={datadir}",
            "--user=mysql",
            f"--log-error={paths['error_log']}",
        ]
        run_command(cmd, sudo=True)

    def _extract_temporary_password(self, error_log: Path) -> Optional[str]:
        if not error_log.exists():
            LOGGER.warning("Error log %s not found; cannot read temporary password", error_log)
            return None
        lines = error_log.read_text().splitlines()
        for line in reversed(lines):
            if "temporary password" in line.lower():
                return line.split()[-1]
        LOGGER.warning("Temporary password not located in %s", error_log)
        return None

    def _generate_root_password(self) -> str:
        return secrets.token_urlsafe(24)

    def _store_root_password(self, password: str, config_dir: Path) -> Path:
        ensure_directory(config_dir)
        path = config_dir / "root-password.txt"
        path.write_text(password + "\n")
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        return path

    def _bootstrap_root_password(
        self,
        instance: InstanceConfig,
        temp_password: Optional[str],
        new_password: str,
    ) -> bool:
        if not temp_password:
            LOGGER.warning("Skipping root password bootstrap; temporary password unavailable")
            return False
        LOGGER.info("Starting mysqld temporarily to set persistent root password")
        cmd = ["mysqld", f"--defaults-file={instance.config_path}", "--daemonize"]
        run_command(cmd, sudo=True)
        try:
            wait_for_socket(Path(instance.socket), timeout=90)
            sql = (
                "ALTER USER 'root'@'localhost' IDENTIFIED BY '{pwd}'; FLUSH PRIVILEGES;"
            ).format(pwd=new_password)
            run_command(
                [
                    "mysql",
                    f"--socket={instance.socket}",
                    "-uroot",
                    f"-p{temp_password}",
                    "--connect-expired-password",
                    "-e",
                    sql,
                ],
                sudo=True,
                mask_secrets=[temp_password, new_password],
            )
            LOGGER.info("Root password updated")
            return True
        finally:
            run_command(
                [
                    "mysqladmin",
                    f"--socket={instance.socket}",
                    "-uroot",
                    f"-p{new_password}",
                    "shutdown",
                ],
                sudo=True,
                mask_secrets=[new_password],
                check=False,
            )
            try:
                wait_for_socket(Path(instance.socket), timeout=30, expect_exists=False)
            except TimeoutError:
                LOGGER.warning("mysqld did not shut down cleanly; please check logs")

    def _mysqld_path(self) -> str:
        path = shutil.which("mysqld")
        if not path:
            raise FileNotFoundError("mysqld binary not found in PATH")
        return path

    def render_systemd_unit(self, instance: InstanceConfig) -> str:
        mysqld_path = self._mysqld_path()
        return f"""
[Unit]
Description=MySQL Server instance {instance.name} managed by mysqlm
After=network.target

[Service]
Type=simple
User=mysql
Group=mysql
ExecStart={mysqld_path} --defaults-file={instance.config_path}
ExecStop=/bin/kill -TERM $MAINPID
TimeoutSec=600
Restart=on-failure
LimitNOFILE=65535
PIDFile={instance.pid_file}

[Install]
WantedBy=multi-user.target
""".strip()

    # ----------------------- public API -----------------------
    def create_instance(
        self,
        name: str,
        port: Optional[int],
        mysql_version: Optional[str],
    ) -> InstanceConfig:
        if self.registry.exists(name):
            raise ValueError(f"Instance '{name}' already exists")
        if port is None:
            port = self.suggest_port()
        self._ensure_port_available(port)
        paths = self._generate_paths(name)
        self._ensure_paths(paths)
        self._set_permissions(paths)
        config_text = self._render_config(port, paths)
        self._write_config(config_text, paths["config_path"])
        self._initialize_datadir(paths)
        temp_password = self._extract_temporary_password(paths["error_log"])
        new_password = self._generate_root_password()
        password_path = self._store_root_password(new_password, paths["conf_dir"])

        now = datetime.utcnow().isoformat()
        instance = InstanceConfig(
            name=name,
            port=port,
            socket=str(paths["socket"]),
            datadir=str(paths["datadir"]),
            config_path=str(paths["config_path"]),
            log_dir=str(paths["log_dir"]),
            error_log=str(paths["error_log"]),
            slow_log=str(paths["slow_log"]),
            pid_file=str(paths["pid_file"]),
            runtime_dir=str(paths["runtime_dir"]),
            backup_dir=str(paths["backup_dir"]),
            mysql_version=mysql_version,
            created_at=now,
            last_modified=now,
            systemd_unit=constants.DEFAULT_SYSTEMD_UNIT_TEMPLATE.format(name=name),
            root_password_path=str(password_path),
            root_password_set=False,
        )

        if self._bootstrap_root_password(instance, temp_password, new_password):
            instance.root_password_set = True
        else:
            LOGGER.warning(
                "Root password stored at %s but may not be applied. Run mysql_secure_installation after first start.",
                password_path,
            )
        self.registry.save(instance)
        return instance

    def remove_instance(self, name: str, keep_data: bool = False) -> None:
        instance = self.registry.load(name)
        self.systemd.stop(instance.systemd_unit)
        self.systemd.disable(instance.systemd_unit)
        unit_path = self.systemd.unit_path(instance.systemd_unit)
        if unit_path.exists():
            unit_path.unlink()
            self.systemd.daemon_reload()
        if not keep_data:
            for path_str in (instance.datadir, instance.log_dir):
                path = Path(path_str)
                if path.exists():
                    shutil.rmtree(path)
        runtime_path = Path(instance.runtime_dir)
        if runtime_path.exists():
            shutil.rmtree(runtime_path)
        conf_dir = Path(instance.config_path).parent
        if conf_dir.exists():
            shutil.rmtree(conf_dir)
        backup_dir = Path(instance.backup_dir)
        if backup_dir.exists() and not keep_data:
            shutil.rmtree(backup_dir)
        self.registry.delete(name)

    def start_instance(self, name: str) -> None:
        instance = self.registry.load(name)
        unit_path = self.systemd.unit_path(instance.systemd_unit)
        if not unit_path.exists():
            unit_content = self.render_systemd_unit(instance)
            self.systemd.write_unit(instance.systemd_unit, unit_content)
        self.systemd.start(instance.systemd_unit)

    def stop_instance(self, name: str) -> None:
        instance = self.registry.load(name)
        self.systemd.stop(instance.systemd_unit)

    def restart_instance(self, name: str) -> None:
        instance = self.registry.load(name)
        self.systemd.restart(instance.systemd_unit)

    def status_instance(self, name: str) -> str:
        instance = self.registry.load(name)
        return self.systemd.status(instance.systemd_unit)
