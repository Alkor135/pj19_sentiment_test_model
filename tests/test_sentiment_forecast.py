import pandas as pd

from sentiment_forecast import build_next_month_forecast_html


def test_next_month_forecast_html_contains_forecast_sections() -> None:
    result = pd.DataFrame({"pnl": [-1000, 0, 1000, 2000]})

    html = build_next_month_forecast_html(
        result,
        forecast_days=2,
        bootstrap_samples=5000,
    )

    assert 'id="next-month-forecast"' in html
    assert "Прогноз на следующий месяц" in html
    assert "Оценка распределения PnL на 2 будущих сигналов/дней" in html
    assert "Нормальные интервалы" in html
    assert "Бутстрэп" in html
    assert "Вероятности порогов по бутстрэпу" in html
    assert "<td>Наблюдений</td><td style=\"text-align:right;\"><b>4</b></td>" in html


def test_next_month_forecast_html_is_deterministic() -> None:
    result = pd.DataFrame({"pnl": [-1000, 0, 1000, 2000]})

    first = build_next_month_forecast_html(result, forecast_days=2, bootstrap_samples=5000)
    second = build_next_month_forecast_html(result, forecast_days=2, bootstrap_samples=5000)

    assert first == second


def test_next_month_forecast_html_returns_empty_for_too_little_history() -> None:
    result = pd.DataFrame({"pnl": [1000]})

    assert build_next_month_forecast_html(result) == ""
