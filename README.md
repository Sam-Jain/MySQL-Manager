# mysqlm – Oracle MySQL Manager for Amazon Linux 2

`mysqlm` is an interactive, production-ready Python CLI for managing Oracle MySQL Community Server on Amazon Linux 2. It streamlines installing specific minor releases, provisioning isolated instances, tuning configuration, performing backups, and executing upgrades – all while enforcing safe defaults and idempotent operations.

## Key Capabilities

- Discover and install the latest patch for a requested major.minor (5.7 or 8.0) via the official Oracle Yum repository, with fallbacks and conflict detection.
- Manage multiple MySQL instances on a single EC2 host with dedicated configuration, data, runtime, and logging directories.
- Generate secure root passwords, bootstrap new datadirs, and optionally bring up instances through dedicated systemd units (`mysqld-<name>.service`).
- Interactively adjust configuration parameters with validation and optional live-value inspection.
- Run logical backups/restores, pre-upgrade health checks, and in-place upgrades with optional safety backups.
- Provide rich logging to both console and rotating log files, plus detailed prompts and confirmations for destructive actions.

## Prerequisites

1. **Operating system**: Amazon Linux 2 with systemd.
2. **Python**: Version 3.9+ available (use the Amazon Linux `python3` package or newer from EPEL).
3. **System access**: sudo/root privileges – the CLI will abort actions that require elevated permissions.
4. **Packages/tools**:
   - `sudo yum install -y yum-utils` (provides `yum-config-manager` for repository management).
   - Oracle MySQL Community Server RPMs accessible via the internet or previously cached locally.
   - Ensure no MariaDB packages are installed (`rpm -qa | grep -i mariadb`); the CLI aborts when conflicts are detected.
5. **Python dependencies**: Installed automatically via `pip`, but outbound internet access is required.

## Installation

```bash
# Clone the repository
sudo yum install -y git python3-pip
git clone <repository-url>
cd MySQL-Manager

# (Recommended) create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the CLI
pip install -e .

# The `mysqlm` command is now available (activate the venv or add to PATH)
mysqlm --help
```

> **Tip:** when running the CLI with sudo, activate the virtual environment inside the sudo session (`sudo -E`) or install globally for system use.

## Directory Layout & State Files

| Path | Purpose |
|------|---------|
| `/etc/mysqlm/config.yaml` | Global mysqlm settings (created on first run; currently reserved for future global defaults). |
| `/etc/mysqlm/instances/<name>.yaml` | Registry entries describing each managed instance. |
| `/var/lib/mysql-instances/<name>` | Dedicated datadir for instance `<name>`. |
| `/etc/mysql-instances/<name>/my.cnf` | Instance-specific configuration file. |
| `/etc/mysql-instances/<name>/root-password.txt` | Secure root password generated during initialization (`chmod 600`). |
| `/var/log/mysql-<name>/` | Error and slow query logs for the instance. |
| `/var/run/mysql-<name>/` | Socket and PID files. |
| `/var/backups/mysql/<name>/` | Logical backup archive root. |
| `/var/log/mysqlm/mysqlm.log` | Rotating mysqlm operational log (5×5 MB). |

### Instance Registry Schema

Each `/etc/mysqlm/instances/<name>.yaml` file stores:

| Field | Description |
|-------|-------------|
| `name` | Instance identifier (e.g., `prod01`). |
| `port` | TCP listener port. |
| `socket` | UNIX socket path. |
| `datadir` | Data directory. |
| `config_path` | `my.cnf` location. |
| `log_dir` | Directory containing logs (`error_log`, `slow_log`). |
| `error_log` / `slow_log` | Specific log file paths. |
| `pid_file` | PID file path used by systemd. |
| `runtime_dir` | Directory that houses sockets/PID files. |
| `backup_dir` | Root backup directory for the instance. |
| `mysql_version` | Installed MySQL version (latest detected patch). |
| `created_at` / `last_modified` | UTC ISO timestamps for lifecycle tracking. |
| `systemd_unit` | The dedicated unit name (`mysqld-<name>.service`). |
| `root_password_path` | File storing the generated root password. |
| `root_password_set` | Whether mysqlm successfully applied the password post-initialization. |

## Usage Overview

Run `mysqlm --help` for the top-level help and `mysqlm <command> --help` for per-command options.

```bash
# Discover available Oracle MySQL builds
sudo mysqlm list-available

# Install the latest 8.0.x patch (prompts for confirmation)
sudo mysqlm install --version 8.0

# Provision an instance named prod01 on port 3306
sudo mysqlm init-instance --name prod01 --port 3306

# View registered instances
mysqlm list-instances

# Start/stop via systemd wrappers
sudo mysqlm start prod01
sudo mysqlm status prod01
sudo mysqlm stop prod01

# Tune configuration safely
sudo mysqlm set-parameter prod01 innodb_buffer_pool_size 2G
sudo mysqlm show-parameters prod01 --live

# Back up and restore
sudo mysqlm backup prod01 --output /var/backups/mysql/prod01
sudo mysqlm restore prod01 /var/backups/mysql/prod01/prod01-20240101-full.sql

# Upgrade to the latest 8.0.x patch (backup by default)
sudo mysqlm upgrade prod01 --to 8.0

# Remove an instance (keep data directory if desired)
sudo mysqlm remove-instance prod01 --keep-data
```

All destructive actions prompt for confirmation unless `--no-*` flags are specified. The CLI masks secrets in logs and never prints generated passwords.

## Logging & Verbosity

- Console output defaults to `INFO` level. Add `--verbose` to any command for debug-level tracing.
- Structured logs are written to `/var/log/mysqlm/mysqlm.log` with rotation (5 files × 5 MB).
- MySQL server logs remain in the per-instance directories under `/var/log/mysql-<name>/`.

## Upgrades & Backups

- `mysqlm upgrade` runs optional logical backups (`mysqldump --single-transaction`) before patching packages and executing `mysql_upgrade`.
- Backups are stored under `/var/backups/mysql/<instance>/<timestamp>/<instance>-<timestamp>.sql` by default; pass `--output` to override.
- `restore` streams SQL files directly into `mysql` using the stored root password; ensure target instance is stopped or prepared appropriately.

## Configuration Management

- `set-parameter` edits the `[mysqld]` block in the instance `my.cnf`, validating numeric/boolean/size values.
- `show-parameters` reads configured values and can optionally query live MySQL variables (requires the instance to be running and the stored root password to be valid).
- After changing tunables the CLI offers to restart the instance (unless `--no-restart` is provided).

## Security & Safety Notes

- Directories are created with restrictive permissions (typically `750` for directories, `640` for config/log files, `600` for password files). Ownership is shifted to the `mysql:mysql` account when present.
- Root/sudo is required for package installation, datadir initialization, and systemd manipulations. Non-privileged invocations are rejected with actionable guidance.
- mysqlm detects conflicting MariaDB packages and aborts before installation, reducing risk of accidental replacement.
- SELinux/AppArmor denials are logged but not automatically remediated; consult `/var/log/audit/audit.log` if mysqld fails to start.

## Troubleshooting

- **Repository issues**: If `yum-config-manager` is missing, install `yum-utils`. Verify `/etc/yum.repos.d/mysql-community.repo` exists.
- **Initialization failures**: Review `/var/log/mysql-<name>/mysqld.log` and `/var/log/mysqlm/mysqlm.log` for detailed errors. Ensure `/var/lib/mysql-instances/<name>` is empty before retrying.
- **Systemd startup problems**: `sudo systemctl status mysqld-<name>` and `journalctl -u mysqld-<name>` provide extended diagnostics.
- **Root password mismatch**: If mysqlm could not apply the generated password, use `mysql_secure_installation` or manually `ALTER USER` using the temporary password noted in the error log.
- **Port collisions**: The CLI checks for active listeners on the selected port. Use `sudo lsof -i :PORT` to inspect conflicts.

## Extensibility

The project is organized into modular components (`mysql_repository`, `instance_manager`, `parameters`, `backups`, `upgrade`, etc.) to ease future enhancements such as monitoring hooks, TLS provisioning, or replication management. System interactions are centralized in `mysqlm/system.py`, simplifying auditing and testing.

---

Feel free to open issues or submit pull requests for additional features and improvements.
