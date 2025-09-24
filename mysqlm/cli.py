"""Command line interface for mysqlm."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from . import constants
from .backups import perform_backup, restore_backup
from .instance_manager import InstanceManager
from .logging_utils import configure_logging, get_logger
from .models import InstanceConfig
from .mysql_repository import MySQLRepositoryManager
from .parameters import display_parameters, set_parameter, show_parameters
from .registry import ConfigStore, InstanceRegistry
from .system import ensure_root, run_command
from .upgrade import UpgradeManager
from .utils import choose, confirm, console, info_table

app = typer.Typer(help="Manage Oracle MySQL Community Server on Amazon Linux 2")
LOGGER = get_logger(__name__)


class AppState:
    def __init__(self) -> None:
        self.console = console
        self.config_store = ConfigStore()
        self.registry = InstanceRegistry()
        self.instance_manager = InstanceManager(self.registry)
        self.repo_manager = MySQLRepositoryManager()
        self.upgrade_manager = UpgradeManager(self.registry)


def _validate_minor(version: str) -> str:
    pattern = re.compile(r"^\d+\.\d+$")
    if not pattern.match(version):
        raise typer.BadParameter("Version must be in <major>.<minor> format, e.g. 8.0")
    return version


@app.callback()
def main(ctx: typer.Context, verbose: bool = typer.Option(False, "--verbose", help="Enable debug logging")) -> None:
    configure_logging(verbose)
    ctx.obj = AppState()


@app.command("list-available")
def list_available(ctx: typer.Context) -> None:
    state: AppState = ctx.obj
    versions = state.repo_manager.list_available_versions()
    table = Table(title="Available MySQL Versions")
    table.add_column("Version")
    table.add_column("Release")
    for version in versions:
        table.add_row(version.version, version.release)
    state.console.print(table)


@app.command()
def install(ctx: typer.Context, version: str = typer.Option(..., "--version", callback=_validate_minor, help="MySQL major.minor version to install")) -> None:
    ensure_root()
    state: AppState = ctx.obj
    if version not in constants.SUPPORTED_MINORS:
        if not confirm(
            f"Version {version} is not officially listed. Continue attempting installation?",
            default=False,
        ):
            raise typer.Abort()
    if not confirm(f"Proceed to install MySQL {version}?", default=True):
        typer.echo("Aborted")
        raise typer.Abort()
    resolved = state.repo_manager.install_version(version)
    state.console.print(f"Installed MySQL {resolved.version} ({resolved.release})")


def _load_instance(ctx: typer.Context, name: str) -> InstanceConfig:
    state: AppState = ctx.obj
    try:
        return state.registry.load(name)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc))


def _detect_installed_version() -> Optional[str]:
    try:
        result = run_command(["mysqld", "--version"])
        match = re.search(r"(\d+\.\d+\.\d+)", result.stdout)
        if match:
            return match.group(1)
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Failed to detect installed MySQL version: %s", exc)
    return None


@app.command("init-instance")
def init_instance(
    ctx: typer.Context,
    name: Optional[str] = typer.Option(None, "--name", help="Instance name"),
    port: Optional[int] = typer.Option(None, "--port", help="Listen port"),
    mysql_minor: Optional[str] = typer.Option(None, "--mysql-version", help="MySQL major.minor version"),
) -> None:
    ensure_root()
    state: AppState = ctx.obj
    if not name:
        name = typer.prompt("Instance name", type=str)
    if state.registry.exists(name):
        raise typer.BadParameter(f"Instance '{name}' already exists")
    if port is None:
        port = state.instance_manager.suggest_port()
        if not confirm(f"Use port {port}?", default=True):
            port = typer.prompt("Port", type=int)
    if mysql_minor is None:
        mysql_minor = choose("Select MySQL minor", constants.SUPPORTED_MINORS) or "8.0"
    else:
        _validate_minor(mysql_minor)

    detected_version = _detect_installed_version()
    if detected_version:
        LOGGER.info("Detected MySQL binary version %s", detected_version)

    instance = state.instance_manager.create_instance(name, port, detected_version or mysql_minor)
    state.console.print(f"Instance {name} created")
    info_table(
        f"Instance {name}",
        [
            ("Name", instance.name),
            ("Port", str(instance.port)),
            ("Socket", instance.socket),
            ("Datadir", instance.datadir),
            ("Config", instance.config_path),
            ("Logs", instance.log_dir),
            ("Root password", instance.root_password_path),
            ("Systemd unit", instance.systemd_unit),
        ],
    )
    if confirm("Enable and start the systemd service now?", default=True):
        state.instance_manager.start_instance(name)
        state.console.print("Instance started via systemd")


@app.command()
def list_instances(ctx: typer.Context) -> None:
    state: AppState = ctx.obj
    table = Table(title="Registered MySQL Instances")
    table.add_column("Name", style="bold")
    table.add_column("Port")
    table.add_column("Socket")
    table.add_column("Datadir")
    table.add_column("Version")
    table.add_column("Systemd Unit")
    for instance in state.registry.list_instances():
        table.add_row(
            instance.name,
            str(instance.port),
            instance.socket,
            instance.datadir,
            instance.mysql_version or "?",
            instance.systemd_unit,
        )
    state.console.print(table)


@app.command()
def start(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    ensure_root()
    state: AppState = ctx.obj
    state.instance_manager.start_instance(name)
    state.console.print(f"Instance {name} started")


@app.command()
def stop(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    ensure_root()
    state: AppState = ctx.obj
    state.instance_manager.stop_instance(name)
    state.console.print(f"Instance {name} stopped")


@app.command()
def restart(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    ensure_root()
    state: AppState = ctx.obj
    state.instance_manager.restart_instance(name)
    state.console.print(f"Instance {name} restarted")


@app.command()
def status(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    ensure_root()
    state: AppState = ctx.obj
    output = state.instance_manager.status_instance(name)
    state.console.print(output)


@app.command("remove-instance")
def remove_instance(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    keep_data: bool = typer.Option(False, "--keep-data", help="Preserve data directory"),
) -> None:
    ensure_root()
    if not confirm(f"Really remove instance {name}?", default=False):
        raise typer.Abort()
    state: AppState = ctx.obj
    state.instance_manager.remove_instance(name, keep_data=keep_data)
    state.console.print(f"Instance {name} removed")


@app.command("set-parameter")
def set_parameter_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    parameter: str = typer.Argument(...),
    value: str = typer.Argument(...),
    no_restart: bool = typer.Option(False, "--no-restart", help="Do not restart automatically"),
) -> None:
    ensure_root()
    state: AppState = ctx.obj
    instance = _load_instance(ctx, name)
    set_parameter(instance, parameter, value)
    state.registry.save(instance)
    if not no_restart and confirm("Restart instance to apply changes?", default=True):
        state.instance_manager.restart_instance(name)
        state.console.print("Instance restarted")


@app.command("show-parameters")
def show_parameters_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    live: bool = typer.Option(False, "--live", help="Query live values via mysql"),
) -> None:
    instance = _load_instance(ctx, name)
    configured, live_values = show_parameters(instance, live=live)
    display_parameters(instance, configured, live_values)


@app.command()
def backup(ctx: typer.Context, name: str = typer.Argument(...), output: Optional[Path] = typer.Option(None, "--output", help="Backup destination directory")) -> None:
    ensure_root()
    instance = _load_instance(ctx, name)
    path = perform_backup(instance, output)
    typer.echo(f"Backup written to {path}")


@app.command()
def restore(ctx: typer.Context, name: str = typer.Argument(...), backup_file: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    ensure_root()
    instance = _load_instance(ctx, name)
    if not confirm(f"Restore {backup_file} into instance {name}?", default=False):
        raise typer.Abort()
    restore_backup(instance, backup_file)
    typer.echo("Restore completed")


@app.command()
def upgrade(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    to: str = typer.Option(..., "--to", callback=_validate_minor, help="Target MySQL minor version"),
    no_backup: bool = typer.Option(False, "--no-backup", help="Skip automatic backup"),
) -> None:
    ensure_root()
    state: AppState = ctx.obj
    if not confirm(f"Upgrade instance {name} to MySQL {to}?", default=False):
        raise typer.Abort()
    upgraded = state.upgrade_manager.upgrade_instance(name, to, take_backup=not no_backup)
    state.console.print(f"Instance {name} now running MySQL {upgraded.mysql_version}")


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
