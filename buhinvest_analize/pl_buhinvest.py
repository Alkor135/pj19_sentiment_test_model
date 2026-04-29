"""
Построение PNG-графиков доходности из файла Buhinvest в RUR.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import yaml


SAVE_PATH = Path(__file__).resolve().parent
SETTINGS_FILE = SAVE_PATH / "settings.yaml"


def load_file_path() -> Path:
    with SETTINGS_FILE.open(encoding="utf-8") as f:
        settings = yaml.safe_load(f) or {}
    return Path(settings["buhinvest_excel_path"])


def build_png_reports(file_path: Path, output_dir: Path = SAVE_PATH) -> tuple[Path, Path]:
    df = pd.read_excel(
        file_path,
        sheet_name="Data",
        usecols=["Дата", "Profit/Loss к предыдущему", "Общ. прибыль Руб."],
    )

    df["Дата"] = pd.to_datetime(df["Дата"])
    df["Profit/Loss к предыдущему"] = pd.to_numeric(df["Profit/Loss к предыдущему"], errors="coerce")
    df["Общ. прибыль Руб."] = pd.to_numeric(df["Общ. прибыль Руб."], errors="coerce")
    df["Profit/Loss к предыдущему"] = df["Profit/Loss к предыдущему"].fillna(0)
    df["Общ. прибыль Руб."] = df["Общ. прибыль Руб."].fillna(0)
    df = df.dropna(subset=["Дата"]).sort_values("Дата")

    monthly = df.copy()
    monthly["Месяц"] = monthly["Дата"].dt.to_period("M")
    pl_by_month = monthly.groupby("Месяц", as_index=False)["Profit/Loss к предыдущему"].sum()
    pl_by_month["Месяц_dt"] = pl_by_month["Месяц"].dt.to_timestamp()
    pl_by_month = pl_by_month.rename(columns={"Profit/Loss к предыдущему": "Profit/Loss"})

    month_output = output_dir / "pl_by_month.png"
    colors = ["red" if x < 0 else "skyblue" for x in pl_by_month["Profit/Loss"]]
    plt.figure(figsize=(10, 5))
    ax = plt.gca()
    ax.bar(pl_by_month["Месяц_dt"], pl_by_month["Profit/Loss"], width=20, color=colors, edgecolor="black")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.xticks(rotation=45, ha="right")
    plt.title("Сумма Profit/Loss по месяцам")
    plt.xlabel("Месяц")
    plt.ylabel("Profit/Loss (RUB)")
    for x, y in zip(pl_by_month["Месяц_dt"], pl_by_month["Profit/Loss"]):
        va = "top" if y < 0 else "bottom"
        ax.text(x, y, f"{y:,.0f}", ha="center", va=va, fontsize=9)
    plt.tight_layout()
    plt.savefig(month_output, dpi=200, bbox_inches="tight")
    plt.close()

    cumulative_output = output_dir / "cumulative_profit.png"
    cumulative = df.drop_duplicates(subset=["Дата"]).sort_values("Дата")
    plt.figure(figsize=(12, 6))
    plt.plot(cumulative["Дата"], cumulative["Общ. прибыль Руб."], marker="o", linestyle="-", color="green")
    plt.title("Общая прибыль (накопительно) по дням")
    plt.xlabel("Дата")
    plt.ylabel("Общ. прибыль Руб.")
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(cumulative_output, dpi=200, bbox_inches="tight")
    plt.close()

    return month_output, cumulative_output


def main() -> None:
    parser = argparse.ArgumentParser(description="Построить PNG-графики из Excel-файла Buhinvest.")
    parser.add_argument("--file", type=Path, default=load_file_path(), help="Путь к Excel-файлу Buhinvest.")
    args = parser.parse_args()

    month_output, cumulative_output = build_png_reports(args.file)
    print("Графики сохранены:")
    print(f"- {month_output}")
    print(f"- {cumulative_output}")


if __name__ == "__main__":
    main()
