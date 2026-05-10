from pathlib import Path
import sqlite3
from datetime import datetime as real_datetime

import beget.sync_files as sync_files


class FixedDateTime(real_datetime):
    @classmethod
    def now(cls):
        return cls(2026, 5, 10, 12, 0, 0)


def test_sync_log_is_written_next_to_script(monkeypatch, tmp_path):
    script_dir = tmp_path / "beget"
    script_dir.mkdir()
    monkeypatch.setattr(sync_files, "__file__", str(script_dir / "sync_files.py"))
    monkeypatch.setattr(sync_files, "remote_host", "root@example.test")
    monkeypatch.setattr(
        sync_files,
        "sync_configs",
        [
            {
                "name": "all_providers",
                "db_dir": str(tmp_path / "db"),
                "log_dir": str(tmp_path / "remote_logs"),
                "db_remote": "/remote/db/",
                "log_remote": "/remote/log/",
                "log_pattern": "*.log",
            }
        ],
    )

    seen_log_files = []

    def fake_run_rsync(command, log_file: Path, section):
        seen_log_files.append(log_file)

    monkeypatch.setattr(sync_files, "run_rsync", fake_run_rsync)
    monkeypatch.setattr(sync_files, "write_rss_db_check", lambda log_file: True)

    sync_files.sync_files()

    expected_log_file = script_dir / "log" / "sync.log"
    assert seen_log_files == [expected_log_file, expected_log_file]
    assert "Sync started\n" in expected_log_file.read_text(encoding="utf-8")


def test_sync_files_writes_rss_db_check_to_console_and_log(
    monkeypatch,
    tmp_path,
    capsys,
):
    script_dir = tmp_path / "beget"
    script_dir.mkdir()
    db_dir = tmp_path / "db"
    remote_log_dir = tmp_path / "remote_logs"
    db_dir.mkdir()

    db_path = db_dir / "rss_news_2026_05.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE news (provider TEXT, date TEXT)")
    conn.executemany(
        "INSERT INTO news (provider, date) VALUES (?, ?)",
        [
            ("interfax", "2026-05-10 09:00:00"),
            ("tass", "2026-05-10 10:00:00"),
            ("tass", "2026-05-09 11:00:00"),
        ],
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(sync_files, "__file__", str(script_dir / "sync_files.py"))
    monkeypatch.setattr(sync_files, "datetime", FixedDateTime)
    monkeypatch.setattr(sync_files, "remote_host", "root@example.test")
    monkeypatch.setattr(
        sync_files,
        "sync_configs",
        [
            {
                "name": "all_providers",
                "db_dir": str(db_dir),
                "log_dir": str(remote_log_dir),
                "db_remote": "/remote/db/",
                "log_remote": "/remote/log/",
                "log_pattern": "*.log",
                "db_file_pattern": "rss_news_{year}_{month:02d}.db",
                "provider_column": "provider",
                "date_column": "date",
            }
        ],
    )
    monkeypatch.setattr(sync_files, "run_rsync", lambda command, log_file, section: None)

    sync_files.sync_files()

    out = capsys.readouterr().out
    log_text = (script_dir / "log" / "sync.log").read_text(encoding="utf-8")

    expected_lines = [
        "=== RSS DB check: 2026-05-09 ===",
        "ВСЕГО за 2026-05-09: 1",
        "=== RSS DB check: 2026-05-10 ===",
        "ВСЕГО за 2026-05-10: 2",
    ]

    for line in expected_lines:
        assert line in out
        assert line in log_text

    assert "\033[" not in log_text
    assert out.index("=== RSS DB check: 2026-05-09 ===") < out.index(
        "=== RSS DB check: 2026-05-10 ==="
    )
