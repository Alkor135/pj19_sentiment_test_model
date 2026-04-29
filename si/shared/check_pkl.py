"""
Просмотр содержимого sentiment_scores.pkl в консоли.
Загружает DataFrame, выводит shape, колонки, диапазон дат и сам df.
"""

import pickle
import sys
from pathlib import Path

import pandas as pd
import yaml

# --- Загрузка настроек из {ticker}/settings.yaml (common + sentiment) ---
TICKER_DIR = Path(__file__).resolve().parents[1]
_raw = yaml.safe_load((TICKER_DIR / "settings.yaml").read_text(encoding="utf-8"))
settings = {**(_raw.get("common") or {}), **(_raw.get("sentiment") or {})}
_ticker = settings.get("ticker", "")
_ticker_lc = settings.get("ticker_lc", _ticker.lower())
for _k, _v in list(settings.items()):
    if isinstance(_v, str):
        settings[_k] = _v.replace("{ticker}", _ticker).replace("{ticker_lc}", _ticker_lc)

pkl_path = Path(settings["sentiment_output_pkl"])

if not pkl_path.exists():
    print(f"Файл не найден: {pkl_path}")
    sys.exit(1)

with open(pkl_path, "rb") as f:
    df = pickle.load(f)

if not isinstance(df, pd.DataFrame):
    df = pd.DataFrame(df)

print(f"Файл: {pkl_path}")
print(f"Shape: {df.shape}")
print(f"Колонки: {list(df.columns)}")
if "source_date" in df.columns:
    print(f"Период: {df['source_date'].min()} .. {df['source_date'].max()}")

with pd.option_context(
    "display.width", 1000,
    "display.max_columns", 20,
    "display.max_colwidth", 60,
    "display.max_rows", 500,
    "display.float_format", "{:,.2f}".format,
):
    print()
    # print(df)
    print(df[['date', 'ticker', 'model', 'prompt_tokens', 'raw_response', 'sentiment', 'body', 'next_body']])
