import sqlite3
from datetime import datetime as real_datetime

import beget.check_rss_db as check_rss_db


class FixedDateTime(real_datetime):
    @classmethod
    def now(cls):
        return cls(2026, 5, 10, 12, 0, 0)


def test_main_prints_today_and_previous_day(monkeypatch, tmp_path, capsys):
    db_path = tmp_path / "rss_news_2026_05.db"
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

    monkeypatch.setattr(check_rss_db, "datetime", FixedDateTime)
    monkeypatch.setattr(
        check_rss_db,
        "load_config",
        lambda: {
            "sources": [
                {
                    "name": "all_providers",
                    "db_dir": str(tmp_path),
                    "db_file_pattern": "rss_news_{year}_{month:02d}.db",
                    "provider_column": "provider",
                    "date_column": "date",
                }
            ]
        },
    )

    exit_code = check_rss_db.main()
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "=== RSS DB check: 2026-05-10 ===" in out
    assert "=== RSS DB check: 2026-05-09 ===" in out
    assert out.index("=== RSS DB check: 2026-05-09 ===") < out.index(
        "=== RSS DB check: 2026-05-10 ==="
    )
    assert "ВСЕГО за 2026-05-10: 2" in out
    assert "ВСЕГО за 2026-05-09: 1" in out
