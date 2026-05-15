from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from compare_backtests import build_report


class CompareBacktestsReportTest(unittest.TestCase):
    def test_ticker_folder_mapping_uses_walk_forward_names(self) -> None:
        self.assertEqual(build_report.walk_ticker_for("rts"), "RTS")
        self.assertEqual(build_report.walk_ticker_for("mix"), "MIX")
        self.assertEqual(build_report.walk_ticker_for("ng"), "NG")
        self.assertEqual(build_report.walk_ticker_for("si"), "Si")
        self.assertEqual(build_report.walk_ticker_for("spyf"), "SPYF")

    def test_discover_pairs_reads_walk_forward_model_folders(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            walk_results = tmp_path / "walk_forward" / "results"
            (walk_results / "RTS" / "gemma3_12b").mkdir(parents=True)
            (walk_results / "RTS" / "qwen2.5_7b").mkdir(parents=True)
            (walk_results / "MIX" / "gemma3_12b").mkdir(parents=True)
            (walk_results / "RTS" / "gemma3_12b" / "trades.xlsx").write_bytes(b"placeholder")
            (walk_results / "RTS" / "qwen2.5_7b" / "trades.xlsx").write_bytes(b"placeholder")
            (walk_results / "MIX" / "gemma3_12b" / "trades.xlsx").write_bytes(b"placeholder")

            pairs = build_report.discover_pairs(root=tmp_path, walk_results_dir=walk_results)

            self.assertEqual(
                [(item.ticker_lc, item.walk_ticker, item.model_dir) for item in pairs],
                [
                    ("mix", "MIX", "gemma3_12b"),
                    ("rts", "RTS", "gemma3_12b"),
                    ("rts", "RTS", "qwen2.5_7b"),
                ],
            )
            self.assertEqual(
                pairs[0].ordinary_path,
                tmp_path / "mix" / "gemma3_12b" / "backtest" / "sentiment_backtest_results.xlsx",
            )
            self.assertEqual(pairs[0].walk_path, walk_results / "MIX" / "gemma3_12b" / "trades.xlsx")

    def test_prepare_comparison_uses_only_overlap_and_recalculates_cum_pnl(self) -> None:
        comparison = build_report.prepare_comparison(
            pair=build_report.ComparisonPair(
                ticker_lc="rts",
                walk_ticker="RTS",
                model_dir="model_a",
                ordinary_path=Path("ordinary.xlsx"),
                walk_path=Path("walk.xlsx"),
            ),
            ordinary=_ordinary_frame(),
            walk=_walk_frame(),
        )

        self.assertIsNone(comparison.error)
        self.assertEqual(comparison.ordinary["source_date"].astype(str).tolist(), ["2026-01-02", "2026-01-03"])
        self.assertEqual(comparison.walk["source_date"].astype(str).tolist(), ["2026-01-02", "2026-01-03"])
        self.assertEqual(comparison.ordinary["cum_pnl"].tolist(), [-3.0, 2.0])
        self.assertEqual(comparison.walk["cum_pnl"].tolist(), [-3.0, -8.0])
        self.assertEqual(comparison.metrics["ordinary_total_pnl"], 2.0)
        self.assertEqual(comparison.metrics["walk_total_pnl"], -8.0)
        self.assertEqual(comparison.metrics["delta_pnl"], -10.0)
        self.assertEqual(comparison.metrics["signal_match_rate"], 50.0)

    def test_build_report_writes_html_with_metrics_and_errors(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            walk_results = tmp_path / "walk_forward" / "results"
            walk_model = walk_results / "RTS" / "model_a"
            walk_model.mkdir(parents=True)
            ordinary_model = tmp_path / "rts" / "model_a" / "backtest"
            ordinary_model.mkdir(parents=True)

            _ordinary_frame().to_excel(ordinary_model / "sentiment_backtest_results.xlsx", index=False)
            _walk_frame().to_excel(walk_model / "trades.xlsx", index=False)

            missing_model = walk_results / "RTS" / "missing_model"
            missing_model.mkdir(parents=True)
            _walk_frame().to_excel(missing_model / "trades.xlsx", index=False)

            missing_walk_model = walk_results / "RTS" / "missing_walk"
            missing_walk_model.mkdir(parents=True)
            missing_walk_backtest = tmp_path / "rts" / "missing_walk" / "backtest"
            missing_walk_backtest.mkdir(parents=True)
            _ordinary_frame().to_excel(missing_walk_backtest / "sentiment_backtest_results.xlsx", index=False)

            output_html = tmp_path / "compare.html"

            build_report.build_report(
                root=tmp_path,
                walk_results_dir=walk_results,
                output_html=output_html,
                tickers=["rts"],
                models=None,
            )

            html = output_html.read_text(encoding="utf-8")
            self.assertIn("Сравнение Backtest и Walk-Forward", html)
            self.assertIn("RTS / model_a", html)
            self.assertIn("Delta P/L", html)
            self.assertIn("missing_model", html)
            self.assertIn("Не найден ordinary backtest", html)
            self.assertIn("missing_walk", html)
            self.assertIn("Не найден walk-forward trades", html)

    def test_parse_csv_returns_none_for_empty_and_values_for_list(self) -> None:
        self.assertIsNone(build_report.parse_csv(None))
        self.assertIsNone(build_report.parse_csv(""))
        self.assertEqual(build_report.parse_csv("rts, mix"), ["rts", "mix"])


def _ordinary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_date": "2026-01-01",
                "sentiment": 1,
                "action": "follow",
                "direction": "LONG",
                "next_body": 10,
                "quantity": 1,
                "pnl": 10,
                "cum_pnl": 10,
            },
            {
                "source_date": "2026-01-02",
                "sentiment": -1,
                "action": "invert",
                "direction": "LONG",
                "next_body": -3,
                "quantity": 1,
                "pnl": -3,
                "cum_pnl": 7,
            },
            {
                "source_date": "2026-01-03",
                "sentiment": 2,
                "action": "follow",
                "direction": "LONG",
                "next_body": 5,
                "quantity": 1,
                "pnl": 5,
                "cum_pnl": 12,
            },
        ]
    )


def _walk_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_date": "2026-01-02",
                "sentiment": -1,
                "action": "invert",
                "direction": "LONG",
                "next_body": -3,
                "quantity": 1,
                "pnl": -3,
                "cum_pnl": -3,
                "ticker": "RTS",
                "model_dir": "model_a",
            },
            {
                "source_date": "2026-01-03",
                "sentiment": 2,
                "action": "invert",
                "direction": "SHORT",
                "next_body": 5,
                "quantity": 1,
                "pnl": -5,
                "cum_pnl": -8,
                "ticker": "RTS",
                "model_dir": "model_a",
            },
            {
                "source_date": "2026-01-04",
                "sentiment": 3,
                "action": "follow",
                "direction": "LONG",
                "next_body": 7,
                "quantity": 1,
                "pnl": 7,
                "cum_pnl": -1,
                "ticker": "RTS",
                "model_dir": "model_a",
            },
        ]
    )
