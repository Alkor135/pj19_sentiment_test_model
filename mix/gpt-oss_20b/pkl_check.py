"""
Проверка содержимого локального `sentiment_scores.pkl`.

Скрипт читает `sentiment_scores.pkl` из той же папки, где лежит сам,
выводит полный список колонок DataFrame, затем первые 5 и последние 5 строк
по колонкам из константы `COLUMNS`.

Примеры запуска:
    .venv/Scripts/python.exe rts/gpt-oss_20b/pkl_check.py
    cd rts/gpt-oss_20b
    ../../.venv/Scripts/python.exe pkl_check.py
"""

from pathlib import Path
import sys

import pandas as pd


PKL_PATH = Path(__file__).resolve().parent / "sentiment_scores.pkl"

COLUMNS = [
    "source_date",
    "date",
    "ticker",
    "model",
    "content_hash",
    "sentiment",
    "body",
    "next_body",
    "next_open_to_open",
    "prompt_tokens",
    "raw_response",
]


def load_sentiment_frame(pkl_path: Path) -> pd.DataFrame:
    """Загружает PKL-файл и возвращает его содержимое как DataFrame."""
    data = pd.read_pickle(pkl_path)
    if isinstance(data, pd.DataFrame):
        return data
    return pd.DataFrame(data)


def select_existing_columns(df: pd.DataFrame, columns: list[str]) -> list[str]:
    """Возвращает только те заданные колонки, которые есть в DataFrame."""
    return [column for column in columns if column in df.columns]


def print_column_list(df: pd.DataFrame) -> None:
    """Печатает полный список колонок DataFrame по одной колонке на строку."""
    print("Колонки df:")
    for column in df.columns:
        print(f"  - {column}")


def print_rows(df: pd.DataFrame, columns: list[str]) -> None:
    """Печатает первые и последние 5 строк по выбранным колонкам."""
    selected_columns = select_existing_columns(df, columns)
    missing_columns = [column for column in columns if column not in df.columns]

    if missing_columns:
        print()
        print("Колонки из COLUMNS, которых нет в df:")
        for column in missing_columns:
            print(f"  - {column}")

    if not selected_columns:
        print()
        print("Нет ни одной колонки из COLUMNS для вывода строк.")
        return

    with pd.option_context(
        "display.width",
        1000,
        "display.max_columns",
        None,
        "display.max_colwidth",
        80,
        "display.max_rows",
        20,
        "display.float_format",
        "{:,.2f}".format,
    ):
        preview_df = df.loc[:, selected_columns]
        print()
        print("Первые 5 строк по COLUMNS:")
        print(preview_df.head(5).to_string(index=False))
        print()
        print("Последние 5 строк по COLUMNS:")
        print(preview_df.tail(5).to_string(index=False))


def print_report(pkl_path: Path, df: pd.DataFrame, columns: list[str]) -> None:
    """Печатает сводку по PKL-файлу и выбранные строки DataFrame."""
    print(f"Файл: {pkl_path}")
    print(f"Shape: {df.shape}")
    print_column_list(df)
    print_rows(df, columns)


def main() -> int:
    """Запускает проверку локального `sentiment_scores.pkl`."""
    if not PKL_PATH.exists():
        print(f"Файл не найден: {PKL_PATH}")
        return 1

    df = load_sentiment_frame(PKL_PATH)
    print_report(PKL_PATH, df, COLUMNS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
