"""
Надёжная синхронизация SQLite + Google Drive + rsync + WSL
Без code 23 и без Permission denied.

Особенности:
- SQLite-safe параметры rsync
- Google Drive safe (--inplace)
- Цветной вывод
- Лог файл
- stderr логируется
"""

import subprocess
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import sys
import yaml

# Цвета консоли
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def get_timestamp():
    """Возвращает текущее время в формате для консольных сообщений и логов."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


with open(Path(__file__).parent / "settings.yaml", encoding="utf-8") as _f:
    _cfg = yaml.safe_load(_f)

sync_configs = _cfg["sources"]
remote_host = _cfg["remote_host"]


def ensure_dir(directory: Path):
    """Создаёт директорию назначения вместе с родительскими папками при необходимости."""
    directory.mkdir(parents=True, exist_ok=True)


def win_to_wsl(path: Path):
    """Преобразует Windows-путь в формат WSL для передачи в rsync."""

    return "/mnt/c" + str(path)[2:].replace("\\", "/")


def run_command(command, log_file: Path, name: str):
    """Запускает внешнюю команду, печатает её в консоль и пишет stdout/stderr в лог."""

    print(f"[{get_timestamp()}] {name}")
    print("Команда:", " ".join(command))

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    with open(log_file, "a", encoding="utf-8") as f:

        f.write(f"\n[{get_timestamp()}] --- {name} ---\n")

        if result.stdout:
            f.write(result.stdout)

        if result.stderr:
            f.write("\nSTDERR:\n")
            f.write(result.stderr)

    return result.returncode


def run_rsync(command, log_file: Path, section):
    """Выполняет rsync-команду и завершает скрипт при критической ошибке."""

    code = run_command(command, log_file, section)

    if code == 0:

        print(GREEN + f"[{get_timestamp()}] OK: {section}" + RESET)

    elif code == 23:

        print(YELLOW +
              f"[{get_timestamp()}] Warning (code 23): {section}" +
              RESET)

    else:

        print(RED +
              f"[{get_timestamp()}] ERROR {code}: {section}" +
              RESET)

        sys.exit(code)


def print_and_log(message: str, log_file: Path):
    """Печатает строку в консоль и добавляет её в служебный лог синхронизации."""
    print(message)
    log_message = (
        message.replace(GREEN, "")
        .replace(RED, "")
        .replace(YELLOW, "")
        .replace(RESET, "")
    )
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(log_message + "\n")


def count_by_provider(db_path: Path, config: dict, day: str):
    """Возвращает количество новостей по провайдерам за указанную дату YYYY-MM-DD."""
    date_col = config["date_column"]
    prov_col = config.get("provider_column")

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    if prov_col:
        rows = cur.execute(
            f"SELECT {prov_col}, COUNT(*) FROM news "
            f"WHERE {date_col} LIKE ? GROUP BY {prov_col} ORDER BY {prov_col}",
            (f"{day}%",),
        ).fetchall()
    else:
        (total,) = cur.execute(
            f"SELECT COUNT(*) FROM news WHERE {date_col} LIKE ?",
            (f"{day}%",),
        ).fetchone()
        rows = [(config["provider_fixed"], total)]

    conn.close()
    return rows


def write_rss_db_day_check(report_day: datetime, log_file: Path):
    """Пишет в консоль и лог отдельный блок проверки RSS-БД за одну дату."""
    day = report_day.strftime("%Y-%m-%d")
    grand_total = 0
    any_missing = False

    print_and_log("", log_file)
    print_and_log(f"=== RSS DB check: {day} ===", log_file)
    print_and_log("", log_file)

    for config in sync_configs:
        db_dir = Path(config["db_dir"])
        db_name = config["db_file_pattern"].format(
            year=report_day.year,
            month=report_day.month,
        )
        db_path = db_dir / db_name

        print_and_log(f"[{config['name']}] {db_path.name}", log_file)

        if not db_path.exists():
            print_and_log(RED + f"  файл не найден: {db_path}" + RESET, log_file)
            any_missing = True
            continue

        rows = count_by_provider(db_path, config, day)
        src_total = sum(n for _, n in rows)
        grand_total += src_total

        if not rows or src_total == 0:
            print_and_log(YELLOW + f"  новостей за {day} нет" + RESET, log_file)
            continue

        for provider, count in rows:
            print_and_log(f"  {provider:<12}: {count:>5}", log_file)
        print_and_log(f"  {'ИТОГО':<12}: {src_total:>5}", log_file)
        print_and_log("", log_file)

    color = GREEN if grand_total > 0 and not any_missing else YELLOW
    print_and_log(color + f"ВСЕГО за {day}: {grand_total}" + RESET, log_file)

    return grand_total > 0 and not any_missing


def write_rss_db_check(log_file: Path):
    """Пишет проверку RSS-БД за предыдущий и текущий день в консоль и лог."""
    now = datetime.now()
    report_days = [now - timedelta(days=1), now]

    all_days_ok = True
    for report_day in report_days:
        if not write_rss_db_day_check(report_day, log_file):
            all_days_ok = False

    return all_days_ok


def sync_files():
    """Синхронизирует базы и лог-файлы для всех источников из settings.yaml."""
    local_log_dir = Path(__file__).resolve().parent / "log"
    ensure_dir(local_log_dir)

    log_file = local_log_dir / "sync.log"

    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"[{get_timestamp()}] Sync started\n")

    for config in sync_configs:

        print("\n" + "=" * 60)

        db_dir = Path(config["db_dir"])
        log_dir = Path(config["log_dir"])

        ensure_dir(db_dir)
        ensure_dir(log_dir)

        # ---------- DB FILES ----------

        print(f"\n[{get_timestamp()}] Sync DB ({config['name']})")

        rsync_db_cmd = [

            "wsl",
            "rsync",

            "-avz",
            "--progress",

            # SQLite + Google Drive safe
            "--inplace",
            "--partial",
            "--size-only",

            "--no-perms",
            "--no-owner",
            "--no-group",

            "--include=*/",
            "--include=**/*.db",
            "--exclude=*",

            f"{remote_host}:{config['db_remote']}",

            win_to_wsl(db_dir) + "/"
        ]

        run_rsync(rsync_db_cmd, log_file,
                  f"Sync DB: {config['name']}")

        # ---------- LOG FILES ----------

        print(f"\n[{get_timestamp()}] Sync LOG ({config['name']})")

        rsync_log_cmd = [

            "wsl",
            "rsync",

            "-avz",
            "--progress",

            "--inplace",
            "--partial",

            "--no-perms",
            "--no-owner",
            "--no-group",

            f"--include={config['log_pattern']}",
            "--exclude=*",

            f"{remote_host}:{config['log_remote']}",

            win_to_wsl(log_dir) + "/"
        ]

        run_rsync(rsync_log_cmd,
                  log_file,
                  f"Sync LOG: {config['name']}")

    write_rss_db_check(log_file)

    print("\n" + GREEN + "SYNC COMPLETE" + RESET)


if __name__ == "__main__":
    sync_files()
