import importlib
import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path


def _create_minute_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE Futures (
            TRADEDATE TEXT PRIMARY KEY UNIQUE NOT NULL,
            SECID TEXT NOT NULL,
            OPEN REAL NOT NULL,
            LOW REAL NOT NULL,
            HIGH REAL NOT NULL,
            CLOSE REAL NOT NULL,
            VOLUME INTEGER NOT NULL,
            LSTTRADE DATE NOT NULL
        )
        """
    )


def test_quik_fill_seeds_today_when_iss_has_no_today_rows(caplog) -> None:
    download = importlib.import_module("mix.shared.download_minutes_to_db")
    connection = sqlite3.connect(":memory:")
    _create_minute_table(connection)
    connection.execute(
        """
        INSERT INTO Futures
        (TRADEDATE, SECID, OPEN, LOW, HIGH, CLOSE, VOLUME, LSTTRADE)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("2026-04-30 20:59:00", "MXM6", 100, 99, 101, 100, 10, "2026-06-18"),
    )

    csv_path = Path("tests/fixtures/quik_minutes_fixture.txt")
    now = datetime.fromtimestamp(csv_path.stat().st_mtime)

    with caplog.at_level(logging.INFO, logger=download.logger.name):
        download.fill_today_tail_from_quik(
            csv_path,
            connection,
            connection.cursor(),
            date(2026, 5, 1),
            now=now,
        )

    rows = connection.execute(
        "SELECT TRADEDATE, SECID, CLOSE, LSTTRADE FROM Futures "
        "WHERE DATE(TRADEDATE) = '2026-05-01' ORDER BY TRADEDATE"
    ).fetchall()

    assert rows == [
        ("2026-05-01 20:58:00", "MXM6", 110.0, "2026-06-18"),
        ("2026-05-01 20:59:00", "MXM6", 111.0, "2026-06-18"),
    ]
    assert "БД нет сегодняшних" not in caplog.text


def test_quik_fill_accepts_nearest_available_bar_before_cutoff() -> None:
    download = importlib.import_module("mix.shared.download_minutes_to_db")
    connection = sqlite3.connect(":memory:")
    _create_minute_table(connection)
    connection.execute(
        """
        INSERT INTO Futures
        (TRADEDATE, SECID, OPEN, LOW, HIGH, CLOSE, VOLUME, LSTTRADE)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("2026-05-01 20:59:00", "MXM6", 100, 99, 101, 100, 10, "2026-06-18"),
    )

    csv_path = Path("tests/fixtures/quik_minutes_fixture.txt")
    now = datetime.fromtimestamp(csv_path.stat().st_mtime)

    download.fill_today_tail_from_quik(
        csv_path,
        connection,
        connection.cursor(),
        date(2026, 5, 2),
        now=now,
    )

    rows = connection.execute(
        "SELECT TRADEDATE, SECID, CLOSE, LSTTRADE FROM Futures "
        "WHERE DATE(TRADEDATE) = '2026-05-02' ORDER BY TRADEDATE"
    ).fetchall()

    assert rows == [("2026-05-02 20:30:00", "MXM6", 120.0, "2026-06-18")]


def test_quik_lua_keeps_full_session_tail_buffer() -> None:
    script = Path("trade/quik_export_minutes.lua").read_text(encoding="utf-8")

    assert "local TAIL_BARS = 1800" in script


def test_final_missing_today_log_runs_after_fallback_attempt(caplog) -> None:
    download = importlib.import_module("mix.shared.download_minutes_to_db")
    connection = sqlite3.connect(":memory:")
    _create_minute_table(connection)

    with caplog.at_level(logging.WARNING, logger=download.logger.name):
        download.log_if_no_today_bars(connection.cursor(), date(2026, 5, 3))

    assert "БД нет сегодняшних баров, пропускаем" in caplog.text
