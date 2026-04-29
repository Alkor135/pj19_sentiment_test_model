from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import quantstats_lumi as qs


REQUIRED_COLUMNS = [
    "Дата",
    "Вводы",
    "Всего на счетах",
    "Общ. прибыль Руб.",
    "Общ. прибыль %",
    "Profit/Loss к предыдущему",
    "Доходность змейкой %",
    "% годовых",
    "XIRR %",
    "За месяц",
]


def load_buhinvest_data(file_path: Path | str) -> pd.DataFrame:
    df = pd.read_excel(file_path, sheet_name="Data", usecols=REQUIRED_COLUMNS)
    df["Дата"] = pd.to_datetime(df["Дата"], errors="coerce")
    df = df.dropna(subset=["Дата"]).sort_values("Дата").reset_index(drop=True)

    numeric_columns = [
        "Вводы",
        "Всего на счетах",
        "Общ. прибыль Руб.",
        "Общ. прибыль %",
        "Profit/Loss к предыдущему",
        "Доходность змейкой %",
        "% годовых",
        "XIRR %",
        "За месяц",
    ]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Вводы"] = df["Вводы"].fillna(0.0)
    df["Profit/Loss к предыдущему"] = df["Profit/Loss к предыдущему"].fillna(0.0)
    return df


def compute_real_capital_returns(df: pd.DataFrame) -> pd.Series:
    pnl = df["Profit/Loss к предыдущему"].astype(float)
    previous_total_equity = df["Всего на счетах"].astype(float).shift(1)
    current_cash_flow = df["Вводы"].fillna(0.0).astype(float)
    capital_base = previous_total_equity.add(current_cash_flow, fill_value=0.0)

    returns = pd.Series(0.0, index=pd.to_datetime(df["Дата"]), dtype=float)
    valid_mask = capital_base.abs() > 1e-12
    returns.loc[valid_mask.values] = pnl.loc[valid_mask].values / capital_base.loc[valid_mask].values
    returns.index.name = None
    return returns


def _max_consecutive(series: pd.Series, condition: int) -> int:
    streaks = (series != condition).cumsum()
    filtered = series[series == condition]
    if filtered.empty:
        return 0
    return int(filtered.groupby(streaks[series == condition]).size().max())


def _build_plotly_figures(df: pd.DataFrame) -> tuple[go.Figure, go.Figure, go.Figure]:
    pl = df["Profit/Loss к предыдущему"]

    day_colors = ["#d32f2f" if v < 0 else "#2e7d32" for v in pl]

    monthly = (
        df.assign(Месяц=df["Дата"].dt.to_period("M"))
        .groupby("Месяц", as_index=False)["Profit/Loss к предыдущему"]
        .sum()
        .rename(columns={"Profit/Loss к предыдущему": "PL"})
    )
    monthly["dt"] = monthly["Месяц"].dt.to_timestamp()
    month_colors = ["#d32f2f" if v < 0 else "#1565c0" for v in monthly["PL"]]

    weekly = (
        df.assign(Неделя=df["Дата"].dt.to_period("W"))
        .groupby("Неделя", as_index=False)["Profit/Loss к предыдущему"]
        .sum()
        .rename(columns={"Profit/Loss к предыдущему": "PL"})
    )
    weekly["dt"] = weekly["Неделя"].apply(lambda p: p.start_time)
    week_colors = ["#d32f2f" if v < 0 else "#00838f" for v in weekly["PL"]]

    cum = df["Общ. прибыль Руб."].fillna(0.0)
    running_max = cum.cummax()
    drawdown = cum - running_max

    for w in (7, 14, 30):
        df[f"MA{w}"] = pl.rolling(w, min_periods=1).mean()

    total_profit = float(df["Общ. прибыль Руб."].iloc[-1])
    total_days = len(df)
    win_days = int((pl > 0).sum())
    loss_days = int((pl < 0).sum())
    zero_days = int((pl == 0).sum())
    trade_days = win_days + loss_days
    win_rate = win_days / max(trade_days, 1) * 100
    max_dd = float(drawdown.min())
    best_day = float(pl.max())
    worst_day = float(pl.min())
    avg_day = float(pl.mean())
    median_day = float(pl.median())
    std_day = float(pl.std())

    gross_profit = float(pl[pl > 0].sum())
    gross_loss = float(abs(pl[pl < 0].sum()))
    avg_win = float(pl[pl > 0].mean()) if win_days else 0.0
    avg_loss = float(abs(pl[pl < 0].mean())) if loss_days else 0.0

    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf")
    recovery_factor = total_profit / abs(max_dd) if max_dd != 0 else float("inf")
    expectancy = (win_rate / 100) * avg_win - (1 - win_rate / 100) * avg_loss
    sharpe = (avg_day / std_day) * np.sqrt(252) if std_day > 0 else 0.0

    downside = pl[pl < 0]
    downside_std = float(downside.std()) if len(downside) > 1 else 0.0
    sortino = (avg_day / downside_std) * np.sqrt(252) if downside_std > 0 else 0.0

    date_range_days = (df["Дата"].max() - df["Дата"].min()).days or 1
    annual_profit = total_profit * 365 / date_range_days
    calmar = annual_profit / abs(max_dd) if max_dd != 0 else float("inf")

    signs = pl.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    max_consec_wins = _max_consecutive(signs, 1)
    max_consec_losses = _max_consecutive(signs, -1)

    max_dd_duration = 0
    current_dd_start = None
    for i in range(len(drawdown)):
        if drawdown.iloc[i] < 0:
            if current_dd_start is None:
                current_dd_start = i
        else:
            if current_dd_start is not None:
                duration = i - current_dd_start
                if duration > max_dd_duration:
                    max_dd_duration = duration
                current_dd_start = None
    if current_dd_start is not None:
        duration = len(drawdown) - current_dd_start
        if duration > max_dd_duration:
            max_dd_duration = duration

    volatility = std_day * np.sqrt(252)

    stats_text = (
        f"Итого: {total_profit:,.0f} ₽ | Дней: {total_days} | "
        f"Win: {win_days} ({win_rate:.0f}%) | Loss: {loss_days} | "
        f"PF: {profit_factor:.2f} | RF: {recovery_factor:.2f} | "
        f"Sharpe: {sharpe:.2f} | MaxDD: {max_dd:,.0f}"
    )

    coefficients = [
        {
            "name": "Recovery Factor",
            "formula": "Чистая прибыль / |Max Drawdown|",
            "value": f"{recovery_factor:.2f}",
            "description": (
                "Коэффициент восстановления: во сколько раз чистая прибыль "
                "превышает максимальную просадку."
            ),
        },
        {
            "name": "Profit Factor",
            "formula": "Валовая прибыль / Валовый убыток",
            "value": f"{profit_factor:.2f}",
            "description": "Отношение суммы прибыльных дней к сумме убыточных дней по модулю.",
        },
        {
            "name": "Payoff Ratio",
            "formula": "Средний выигрыш / Средний проигрыш",
            "value": f"{payoff_ratio:.2f}",
            "description": "Показывает, насколько средний выигрыш больше среднего проигрыша.",
        },
        {
            "name": "Sharpe Ratio",
            "formula": "(Средний дневной P/L / Std дневного P/L) × √252",
            "value": f"{sharpe:.2f}",
            "description": "Отношение доходности к общей волатильности.",
        },
        {
            "name": "Sortino Ratio",
            "formula": "(Средний дневной P/L / Downside Std) × √252",
            "value": f"{sortino:.2f}",
            "description": "Отношение доходности к нисходящей волатильности.",
        },
        {
            "name": "Calmar Ratio",
            "formula": "Годовая доходность / |Max Drawdown|",
            "value": f"{calmar:.2f}",
            "description": "Отношение годовой прибыли к максимальной просадке.",
        },
        {
            "name": "Expectancy",
            "formula": "Win% × Ср.выигрыш − Loss% × Ср.проигрыш",
            "value": f"{expectancy:,.0f} ₽",
            "description": "Математическое ожидание на один торговый день.",
        },
    ]

    fig = make_subplots(
        rows=5,
        cols=2,
        subplot_titles=(
            "P/L по дням (руб.)",
            "Накопительная прибыль (руб.)",
            "P/L по месяцам (руб.)",
            "P/L по неделям (руб.)",
            "Баланс на счетах (руб.)",
            "Доходность: XIRR % и % годовых",
            "Распределение дневных P/L",
            "Drawdown от максимума (руб.)",
            "Скользящие средние P/L (7/14/30 дней)",
            "Recovery Factor (скользящий)",
        ),
        specs=[
            [{"type": "bar"}, {"type": "scatter"}],
            [{"type": "bar"}, {"type": "bar"}],
            [{"type": "scatter"}, {"type": "scatter"}],
            [{"type": "histogram"}, {"type": "scatter"}],
            [{"type": "scatter"}, {"type": "scatter"}],
        ],
        vertical_spacing=0.06,
        horizontal_spacing=0.06,
    )

    fig.add_trace(
        go.Bar(
            x=df["Дата"],
            y=pl,
            marker_color=day_colors,
            name="P/L день",
            hovertemplate="%{x|%Y-%m-%d}<br>P/L: %{y:,.0f} ₽<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df["Дата"],
            y=cum,
            mode="lines",
            fill="tozeroy",
            line=dict(color="#2e7d32", width=2),
            fillcolor="rgba(46,125,50,0.15)",
            name="Накопл. прибыль",
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.0f} ₽<extra></extra>",
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Bar(
            x=monthly["dt"],
            y=monthly["PL"],
            marker_color=month_colors,
            name="P/L месяц",
            text=[f"{v:,.0f}" for v in monthly["PL"]],
            textposition="outside",
            hovertemplate="%{x|%Y-%m}<br>P/L: %{y:,.0f} ₽<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=weekly["dt"],
            y=weekly["PL"],
            marker_color=week_colors,
            name="P/L неделя",
            hovertemplate="Нед. %{x|%Y-%m-%d}<br>P/L: %{y:,.0f} ₽<extra></extra>",
        ),
        row=2,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=df["Дата"],
            y=df["Всего на счетах"],
            mode="lines+markers",
            line=dict(color="#1565c0", width=2),
            marker=dict(size=3),
            name="Баланс",
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.0f} ₽<extra></extra>",
        ),
        row=3,
        col=1,
    )

    deposits = df[df["Вводы"] != 0]
    if not deposits.empty:
        fig.add_trace(
            go.Scatter(
                x=deposits["Дата"],
                y=deposits["Всего на счетах"],
                mode="markers+text",
                marker=dict(size=12, color="#ff6f00", symbol="triangle-up"),
                text=[f"Ввод {v:,.0f}" for v in deposits["Вводы"]],
                textposition="top center",
                name="Вводы",
                hovertemplate="%{x|%Y-%m-%d}<br>%{text}<extra></extra>",
            ),
            row=3,
            col=1,
        )

    fig.add_trace(
        go.Scatter(
            x=df["Дата"],
            y=df["XIRR %"] * 100,
            mode="lines",
            line=dict(color="#7b1fa2", width=1.5),
            name="XIRR %",
            hovertemplate="%{x|%Y-%m-%d}<br>XIRR: %{y:.1f}%<extra></extra>",
        ),
        row=3,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=df["Дата"],
            y=df["% годовых"] * 100,
            mode="lines",
            line=dict(color="#e65100", width=1.5),
            name="% годовых",
            hovertemplate="%{x|%Y-%m-%d}<br>% годовых: %{y:.1f}%<extra></extra>",
        ),
        row=3,
        col=2,
    )

    pl_pos = pl[pl > 0]
    pl_neg = pl[pl < 0]
    fig.add_trace(
        go.Histogram(
            x=pl_pos,
            marker_color="#2e7d32",
            opacity=0.7,
            name="Прибыль",
            nbinsx=30,
            hovertemplate="P/L: %{x:,.0f}<br>Кол-во: %{y}<extra></extra>",
        ),
        row=4,
        col=1,
    )
    fig.add_trace(
        go.Histogram(
            x=pl_neg,
            marker_color="#d32f2f",
            opacity=0.7,
            name="Убыток",
            nbinsx=30,
            hovertemplate="P/L: %{x:,.0f}<br>Кол-во: %{y}<extra></extra>",
        ),
        row=4,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df["Дата"],
            y=drawdown,
            mode="lines",
            fill="tozeroy",
            line=dict(color="#d32f2f", width=1.5),
            fillcolor="rgba(211,47,47,0.2)",
            name="Drawdown",
            hovertemplate="%{x|%Y-%m-%d}<br>DD: %{y:,.0f} ₽<extra></extra>",
        ),
        row=4,
        col=2,
    )

    for w, color in [(7, "#1565c0"), (14, "#ff6f00"), (30, "#7b1fa2")]:
        fig.add_trace(
            go.Scatter(
                x=df["Дата"],
                y=df[f"MA{w}"],
                mode="lines",
                line=dict(color=color, width=1.5),
                name=f"MA{w}",
                hovertemplate=f"MA{w}: " + "%{y:,.0f}<extra></extra>",
            ),
            row=5,
            col=1,
        )
    fig.add_hline(y=0, line_dash="dash", line_color="gray", row=5, col=1)

    rf_rolling = pd.Series(dtype=float, index=df.index)
    for i in range(len(df)):
        dd_so_far = (cum.iloc[: i + 1] - cum.iloc[: i + 1].cummax()).min()
        rf_rolling.iloc[i] = cum.iloc[i] / abs(dd_so_far) if dd_so_far != 0 else 0
    fig.add_trace(
        go.Scatter(
            x=df["Дата"],
            y=rf_rolling,
            mode="lines",
            line=dict(color="#00695c", width=2),
            name="Recovery Factor",
            hovertemplate="%{x|%Y-%m-%d}<br>RF: %{y:.2f}<extra></extra>",
        ),
        row=5,
        col=2,
    )
    fig.add_hline(y=1, line_dash="dash", line_color="gray", row=5, col=2, annotation_text="RF=1")

    fig.update_layout(
        height=2000,
        width=1500,
        title_text=f"Buhinvest Futures RTS+MIX — Анализ доходности<br><sub>{stats_text}</sub>",
        title_x=0.5,
        showlegend=True,
        legend=dict(orientation="h", yanchor="top", y=-0.07, xanchor="center", x=0.5),
        template="plotly_white",
        hovermode="x unified",
    )

    for row, col in [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (4, 2), (5, 1)]:
        fig.update_yaxes(tickformat=",", row=row, col=col)
    fig.update_yaxes(ticksuffix="%", row=3, col=2)
    fig.update_xaxes(tickformat="%Y-%m-%d", row=4, col=1, title_text="P/L (руб.)")
    fig.update_yaxes(title_text="RF", row=5, col=2)

    sec1 = [
        ["<b>ДОХОДНОСТЬ</b>", ""],
        ["Чистая прибыль", f"{total_profit:,.0f} ₽"],
        ["Годовая прибыль (экстрапол.)", f"{annual_profit:,.0f} ₽"],
        ["Средний P/L в день", f"{avg_day:,.0f} ₽"],
        ["Медианный P/L в день", f"{median_day:,.0f} ₽"],
        ["Лучший день", f"{best_day:,.0f} ₽"],
        ["Худший день", f"{worst_day:,.0f} ₽"],
    ]
    sec2 = [
        ["<b>РИСК</b>", ""],
        ["Max Drawdown", f"{max_dd:,.0f} ₽"],
        ["Длит. макс. просадки", f"{max_dd_duration} дней"],
        ["Волатильность (год.)", f"{volatility:,.0f} ₽"],
        ["Std дневного P/L", f"{std_day:,.0f} ₽"],
        ["VaR 95%", f"{np.percentile(pl, 5):,.0f} ₽"],
        ["CVaR 95%", f"{pl[pl <= np.percentile(pl, 5)].mean():,.0f} ₽"],
    ]
    sec3 = [
        ["<b>СТАТИСТИКА СДЕЛОК</b>", ""],
        ["Торговых дней", f"{total_days}"],
        ["Win / Loss / Zero", f"{win_days} / {loss_days} / {zero_days}"],
        ["Win rate", f"{win_rate:.1f}%"],
        ["Ср. выигрыш / проигрыш", f"{avg_win:,.0f} / {avg_loss:,.0f} ₽"],
        ["Макс. серия побед", f"{max_consec_wins}"],
        ["Макс. серия убытков", f"{max_consec_losses}"],
    ]

    num_rows = max(len(sec1), len(sec2), len(sec3))
    for sec in (sec1, sec2, sec3):
        while len(sec) < num_rows:
            sec.append(["", ""])

    cols = [[], [], [], [], [], []]
    colors = [[], [], []]
    for i in range(num_rows):
        for j, sec in enumerate((sec1, sec2, sec3)):
            name, value = sec[i]
            is_header = value == "" and name.startswith("<b>")
            cols[j * 2].append(name)
            cols[j * 2 + 1].append(f"<b>{value}</b>" if value and not is_header else value)
            colors[j].append("#e3f2fd" if is_header else ("#f5f5f5" if i % 2 == 0 else "white"))

    fig_stats = go.Figure(
        go.Table(
            columnwidth=[200, 130, 180, 120, 200, 140],
            header=dict(
                values=["<b>Показатель</b>", "<b>Значение</b>"] * 3,
                fill_color="#1565c0",
                font=dict(color="white", size=14),
                align="left",
                height=32,
            ),
            cells=dict(
                values=cols,
                fill_color=[colors[0], colors[0], colors[1], colors[1], colors[2], colors[2]],
                font=dict(size=13, color="#212121"),
                align=["left", "right", "left", "right", "left", "right"],
                height=26,
            ),
        )
    )
    fig_stats.update_layout(
        title_text="<b>Статистика стратегии</b>",
        title_x=0.5,
        title_font_size=18,
        height=32 + num_rows * 26 + 80,
        width=1500,
        margin=dict(l=20, r=20, t=60, b=20),
    )

    fig_table = go.Figure(
        go.Table(
            columnwidth=[150, 250, 80, 450],
            header=dict(
                values=[
                    "<b>Коэффициент</b>",
                    "<b>Формула</b>",
                    "<b>Значение</b>",
                    "<b>Расшифровка</b>",
                ],
                fill_color="#1565c0",
                font=dict(color="white", size=14),
                align="left",
                height=36,
            ),
            cells=dict(
                values=[
                    [f"<b>{c['name']}</b>" for c in coefficients],
                    [c["formula"] for c in coefficients],
                    [f"<b>{c['value']}</b>" for c in coefficients],
                    [c["description"] for c in coefficients],
                ],
                fill_color=[
                    ["#f5f5f5" if i % 2 == 0 else "white" for i in range(len(coefficients))]
                ]
                * 4,
                font=dict(size=13, color="#212121"),
                align=["left", "left", "center", "left"],
                height=80,
            ),
        )
    )
    fig_table.update_layout(
        title_text="<b>Ключевые коэффициенты торговой стратегии</b>",
        title_x=0.5,
        title_font_size=18,
        height=700,
        width=1500,
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig, fig_stats, fig_table


def build_plotly_report(df: pd.DataFrame, output_html: Path, title: str = "Buhinvest — Анализ доходности") -> None:
    output_html.parent.mkdir(parents=True, exist_ok=True)
    fig, fig_stats, fig_table = _build_plotly_figures(df.copy())

    with output_html.open("w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html>\n<html><head><meta charset='utf-8'>\n")
        f.write(f"<title>{title}</title>\n</head><body>\n")
        f.write(fig.to_html(include_plotlyjs="cdn", full_html=False))
        f.write("\n<hr style='margin:30px 0; border:1px solid #ccc'>\n")
        f.write(fig_stats.to_html(include_plotlyjs=False, full_html=False))
        f.write("\n<hr style='margin:30px 0; border:1px solid #ccc'>\n")
        f.write(fig_table.to_html(include_plotlyjs=False, full_html=False))
        f.write("\n</body></html>")


def build_qs_report(returns: pd.Series, output_html: Path, title: str) -> None:
    output_html.parent.mkdir(parents=True, exist_ok=True)
    clean_returns = returns.astype(float).sort_index()
    clean_returns.index.name = None
    qs.reports.html(clean_returns, benchmark=None, output=str(output_html), title=title)


def generate_reports(
    file_path: Path | str,
    output_dir: Path | str,
    plotly_name: str = "pl_buhinvest_interactive.html",
    qs_name: str = "pl_buhinvest_interactive_qs.html",
) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    df = load_buhinvest_data(file_path)
    plotly_output = output_dir / plotly_name
    qs_output = output_dir / qs_name

    build_plotly_report(df, plotly_output)
    returns = compute_real_capital_returns(df)
    build_qs_report(returns, qs_output, title="Buhinvest Futures RTS+MIX (QuantStats)")
    return plotly_output, qs_output
