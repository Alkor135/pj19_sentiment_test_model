from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill


SUMMARY_COLUMNS = (
    "status",
    "ticker",
    "model_dir",
    "sentiment_model",
    "source_date",
    "trades",
    "pnl",
    "skip_reason",
    "error",
)
TRADE_COLUMNS = (
    "ticker",
    "model_dir",
    "sentiment_model",
    "source_date",
    "pnl",
    "direction",
    "action",
    "sentiment",
)
GROUP_KEYS = ["ticker", "model_dir", "sentiment_model"]


def normalize_summary(summary: pd.DataFrame) -> pd.DataFrame:
    result = summary.copy()
    for column in SUMMARY_COLUMNS:
        if column not in result.columns:
            result[column] = ""

    result["status"] = result["status"].fillna("").astype(str)
    result["ticker"] = result["ticker"].fillna("").astype(str).str.upper()
    result["model_dir"] = result["model_dir"].fillna("").astype(str)
    result["sentiment_model"] = result["sentiment_model"].fillna("").astype(str)
    result["source_date"] = pd.to_datetime(result["source_date"], errors="coerce").dt.date
    result["trades"] = pd.to_numeric(result["trades"], errors="coerce").fillna(0).astype(int)
    result["pnl"] = pd.to_numeric(result["pnl"], errors="coerce").fillna(0.0).astype(float)
    result["skip_reason"] = result["skip_reason"].fillna("").astype(str)
    result["error"] = result["error"].fillna("").astype(str)
    return result


def normalize_trades(trades: pd.DataFrame) -> pd.DataFrame:
    result = trades.copy()
    for column in TRADE_COLUMNS:
        if column not in result.columns:
            result[column] = ""

    result["ticker"] = result["ticker"].fillna("").astype(str).str.upper()
    result["model_dir"] = result["model_dir"].fillna("").astype(str)
    result["sentiment_model"] = result["sentiment_model"].fillna("").astype(str)
    result["source_date"] = pd.to_datetime(result["source_date"], errors="coerce").dt.date
    result["pnl"] = pd.to_numeric(result["pnl"], errors="coerce").fillna(0.0).astype(float)
    result["sentiment"] = pd.to_numeric(result["sentiment"], errors="coerce")
    result["direction"] = result["direction"].fillna("").astype(str)
    result["action"] = result["action"].fillna("").astype(str)
    return result.dropna(subset=["source_date"])


def _empty_leaderboard() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "ticker",
            "rank",
            "model_dir",
            "sentiment_model",
            "days",
            "trades",
            "total_pnl",
            "winrate",
            "profit_factor",
            "max_drawdown",
            "recovery_factor",
            "avg_trade",
            "best_day",
            "worst_day",
            "score",
            "skipped_days",
            "error_days",
        ]
    )


def _metric_row(key: tuple[Any, ...], summary: pd.DataFrame, trades: pd.DataFrame) -> dict[str, Any]:
    ticker, model_dir, sentiment_model = key
    model_summary = summary[
        (summary["ticker"] == ticker)
        & (summary["model_dir"] == model_dir)
        & (summary["sentiment_model"] == sentiment_model)
    ]
    model_trades = trades[
        (trades["ticker"] == ticker)
        & (trades["model_dir"] == model_dir)
        & (trades["sentiment_model"] == sentiment_model)
    ].sort_values("source_date")

    daily_pnl = model_trades.groupby("source_date")["pnl"].sum().sort_index()
    trades_count = int(len(model_trades))
    total_pnl = float(model_trades["pnl"].sum()) if trades_count else 0.0
    gross_profit = float(model_trades.loc[model_trades["pnl"] > 0, "pnl"].sum()) if trades_count else 0.0
    gross_loss = abs(float(model_trades.loc[model_trades["pnl"] < 0, "pnl"].sum())) if trades_count else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss else float("inf")
    winrate = float((model_trades["pnl"] > 0).mean() * 100) if trades_count else 0.0
    avg_trade = total_pnl / trades_count if trades_count else 0.0
    best_day = float(daily_pnl.max()) if not daily_pnl.empty else 0.0
    worst_day = float(daily_pnl.min()) if not daily_pnl.empty else 0.0
    max_drawdown = 0.0
    if not daily_pnl.empty:
        cum = daily_pnl.cumsum()
        max_drawdown = float((cum - cum.cummax()).min())
    recovery_factor = total_pnl / abs(max_drawdown) if max_drawdown else float("inf")
    score = total_pnl + max_drawdown * 0.5

    summary_days = int(model_summary["source_date"].nunique()) if not model_summary.empty else 0
    trade_days = int(daily_pnl.index.nunique()) if not daily_pnl.empty else 0
    return {
        "ticker": ticker,
        "rank": 0,
        "model_dir": model_dir,
        "sentiment_model": sentiment_model,
        "days": max(summary_days, trade_days),
        "trades": trades_count,
        "total_pnl": total_pnl,
        "winrate": winrate,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "recovery_factor": recovery_factor,
        "avg_trade": avg_trade,
        "best_day": best_day,
        "worst_day": worst_day,
        "score": score,
        "skipped_days": int((model_summary["status"] == "skipped").sum()) if not model_summary.empty else 0,
        "error_days": int((model_summary["status"] == "error").sum()) if not model_summary.empty else 0,
    }


def build_leaderboard(summary: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    summary = normalize_summary(summary)
    trades = normalize_trades(trades)
    ok_summary = summary[summary["status"] == "ok"]

    keys: set[tuple[Any, ...]] = set()
    if not ok_summary.empty:
        keys.update(tuple(row) for row in ok_summary[GROUP_KEYS].drop_duplicates().to_numpy())
    if not trades.empty:
        keys.update(tuple(row) for row in trades[GROUP_KEYS].drop_duplicates().to_numpy())
    if not keys:
        return _empty_leaderboard()

    result = pd.DataFrame([_metric_row(key, summary, trades) for key in sorted(keys)])
    result = result.sort_values(["ticker", "score", "total_pnl"], ascending=[True, False, False])
    result["rank"] = result.groupby("ticker").cumcount() + 1
    return result[_empty_leaderboard().columns].reset_index(drop=True)


def build_ticker_summary(leaderboard: pd.DataFrame) -> pd.DataFrame:
    if leaderboard.empty:
        return pd.DataFrame(
            columns=[
                "ticker",
                "models",
                "best_model",
                "best_score",
                "total_pnl",
                "avg_model_pnl",
                "trades",
                "best_winrate",
                "worst_drawdown",
            ]
        )

    rows: list[dict[str, Any]] = []
    for ticker, group in leaderboard.sort_values(["ticker", "rank"]).groupby("ticker", sort=True):
        best = group.iloc[0]
        rows.append(
            {
                "ticker": ticker,
                "models": int(group["model_dir"].nunique()),
                "best_model": best["model_dir"],
                "best_score": float(best["score"]),
                "total_pnl": float(group["total_pnl"].sum()),
                "avg_model_pnl": float(group["total_pnl"].mean()),
                "trades": int(group["trades"].sum()),
                "best_winrate": float(group["winrate"].max()),
                "worst_drawdown": float(group["max_drawdown"].min()),
            }
        )
    return pd.DataFrame(rows)


def _empty_errors() -> pd.DataFrame:
    return pd.DataFrame(columns=["ticker", "model_dir", "sentiment_model", "status", "error"])


def _resolve_ticker_dir(results_dir: Path, ticker: str) -> Path:
    direct = results_dir / ticker
    if direct.exists():
        return direct

    ticker_lc = ticker.lower()
    if results_dir.exists():
        for child in results_dir.iterdir():
            if child.is_dir() and child.name.lower() == ticker_lc:
                return child
    return direct


def load_all_trades(results_dir: Path, summary: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary = normalize_summary(summary)
    ok_summary = summary[summary["status"] == "ok"]
    frames: list[pd.DataFrame] = []
    errors: list[dict[str, str]] = []

    for item in ok_summary[GROUP_KEYS].drop_duplicates().to_dict("records"):
        ticker = str(item["ticker"])
        model_dir = str(item["model_dir"])
        sentiment_model = str(item["sentiment_model"])
        trades_path = _resolve_ticker_dir(results_dir, ticker) / model_dir / "trades.csv"

        if not trades_path.exists():
            errors.append(
                {
                    "ticker": ticker,
                    "model_dir": model_dir,
                    "sentiment_model": sentiment_model,
                    "status": "error",
                    "error": f"Не найден файл trades.csv: {trades_path}",
                }
            )
            continue

        try:
            frame = pd.read_csv(trades_path, encoding="utf-8-sig")
        except Exception as exc:
            errors.append(
                {
                    "ticker": ticker,
                    "model_dir": model_dir,
                    "sentiment_model": sentiment_model,
                    "status": "error",
                    "error": f"Не удалось прочитать trades.csv: {exc}",
                }
            )
            continue

        frame["ticker"] = ticker
        frame["model_dir"] = model_dir
        frame["sentiment_model"] = sentiment_model
        frames.append(frame)

    trades = normalize_trades(pd.concat(frames, ignore_index=True)) if frames else normalize_trades(pd.DataFrame())
    error_frame = pd.DataFrame(errors) if errors else _empty_errors()
    return trades, error_frame


def _build_period_matrix(trades: pd.DataFrame, period_column: str) -> pd.DataFrame:
    trades = normalize_trades(trades)
    if trades.empty:
        return pd.DataFrame()

    result = trades.copy()
    result["series"] = result["ticker"] + " / " + result["model_dir"]
    if period_column == "month":
        result["period"] = pd.to_datetime(result["source_date"]).dt.to_period("M").astype(str)
    else:
        result["period"] = pd.to_datetime(result["source_date"]).dt.strftime("%Y-%m-%d")

    matrix = result.pivot_table(
        index="series",
        columns="period",
        values="pnl",
        aggfunc="sum",
        fill_value=0.0,
    )
    return matrix.sort_index().sort_index(axis=1)


def build_monthly_matrix(trades: pd.DataFrame) -> pd.DataFrame:
    return _build_period_matrix(trades, "month")


def build_daily_matrix(trades: pd.DataFrame) -> pd.DataFrame:
    return _build_period_matrix(trades, "day")


def build_dashboard(
    summary: pd.DataFrame,
    trades: pd.DataFrame,
    leaderboard: pd.DataFrame,
    ticker_summary: pd.DataFrame,
    errors: pd.DataFrame,
) -> pd.DataFrame:
    summary = normalize_summary(summary)
    trades = normalize_trades(trades)
    total_pnl = float(trades["pnl"].sum()) if not trades.empty else 0.0
    best = leaderboard.iloc[0] if not leaderboard.empty else None
    return pd.DataFrame(
        [
            {"Показатель": "Тикеров", "Значение": int(ticker_summary["ticker"].nunique()) if not ticker_summary.empty else 0},
            {"Показатель": "Моделей", "Значение": int(leaderboard["model_dir"].nunique()) if not leaderboard.empty else 0},
            {"Показатель": "Дней в summary", "Значение": int(summary["source_date"].nunique()) if not summary.empty else 0},
            {"Показатель": "Сделок", "Значение": int(len(trades))},
            {"Показатель": "Total P/L", "Значение": total_pnl},
            {"Показатель": "Лучшая модель", "Значение": "" if best is None else f"{best['ticker']} / {best['model_dir']}"},
            {"Показатель": "Ошибок", "Значение": int(len(errors))},
        ]
    )


def _excel_safe(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.copy()


def _sheet_name(value: str, used: set[str]) -> str:
    base = "".join(ch for ch in value if ch not in r"[]:*?/\\")[:31] or "Sheet"
    name = base
    suffix = 2
    while name in used:
        tail = f"_{suffix}"
        name = f"{base[:31 - len(tail)]}{tail}"
        suffix += 1
    used.add(name)
    return name


def write_excel_report(
    *,
    summary: pd.DataFrame,
    trades: pd.DataFrame,
    leaderboard: pd.DataFrame,
    ticker_summary: pd.DataFrame,
    monthly_matrix: pd.DataFrame,
    daily_matrix: pd.DataFrame,
    errors: pd.DataFrame,
    output_xlsx: Path,
) -> None:
    output_xlsx.parent.mkdir(parents=True, exist_ok=True)
    summary = normalize_summary(summary)
    trades = normalize_trades(trades)
    errors = errors.copy() if not errors.empty else _empty_errors()
    dashboard = build_dashboard(summary, trades, leaderboard, ticker_summary, errors)
    used_sheets = {
        "Dashboard",
        "Leaderboard",
        "Ticker_Summary",
        "Monthly_Matrix",
        "Daily_Matrix",
        "Raw_Summary",
        "Raw_Trades",
        "Errors",
    }

    with pd.ExcelWriter(output_xlsx, engine="openpyxl") as writer:
        _excel_safe(dashboard).to_excel(writer, sheet_name="Dashboard", index=False, inf_rep="inf")
        _excel_safe(leaderboard).to_excel(writer, sheet_name="Leaderboard", index=False, inf_rep="inf")
        _excel_safe(ticker_summary).to_excel(writer, sheet_name="Ticker_Summary", index=False, inf_rep="inf")
        _excel_safe(monthly_matrix).to_excel(writer, sheet_name="Monthly_Matrix", inf_rep="inf")
        _excel_safe(daily_matrix).to_excel(writer, sheet_name="Daily_Matrix", inf_rep="inf")

        tickers = sorted(
            set(leaderboard["ticker"].dropna())
            | set(ticker_summary["ticker"].dropna())
            | set(trades["ticker"].dropna())
        )
        for ticker in tickers:
            ticker_trades = trades[trades["ticker"] == ticker]
            ticker_leaderboard = leaderboard[leaderboard["ticker"] == ticker]
            sheet = _sheet_name(str(ticker), used_sheets)
            if not ticker_trades.empty:
                frame = ticker_trades
            else:
                frame = ticker_leaderboard
            _excel_safe(frame).to_excel(writer, sheet_name=sheet, index=False, inf_rep="inf")

        _excel_safe(summary).to_excel(writer, sheet_name="Raw_Summary", index=False, inf_rep="inf")
        _excel_safe(trades).to_excel(writer, sheet_name="Raw_Trades", index=False, inf_rep="inf")
        _excel_safe(errors).to_excel(writer, sheet_name="Errors", index=False, inf_rep="inf")

    _style_workbook(output_xlsx)


def _style_workbook(path: Path) -> None:
    workbook = load_workbook(path)
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    positive_fill = PatternFill("solid", fgColor="E2F0D9")
    negative_fill = PatternFill("solid", fgColor="FCE4D6")

    for worksheet in workbook.worksheets:
        worksheet.freeze_panes = "A2"
        worksheet.sheet_view.showGridLines = False
        if worksheet.max_row > 1 and worksheet.max_column > 0:
            worksheet.auto_filter.ref = worksheet.dimensions

        headers: dict[int, str] = {}
        for cell in worksheet[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")
            headers[cell.column] = str(cell.value or "").lower()

        for column_cells in worksheet.columns:
            width = min(max(len(str(cell.value or "")) for cell in column_cells) + 2, 44)
            worksheet.column_dimensions[column_cells[0].column_letter].width = max(width, 10)

        for row in worksheet.iter_rows(min_row=2):
            for cell in row:
                header = headers.get(cell.column, "")
                if isinstance(cell.value, (int, float)):
                    if any(token in header for token in ("pnl", "p/l", "score", "drawdown", "profit", "avg", "best", "worst")):
                        cell.number_format = "#,##0.00"
                    if any(token in header for token in ("winrate", "rate")):
                        cell.number_format = "0.00"
                    if any(token in header for token in ("pnl", "p/l", "score")):
                        if cell.value > 0:
                            cell.fill = positive_fill
                        elif cell.value < 0:
                            cell.fill = negative_fill

    workbook.save(path)
