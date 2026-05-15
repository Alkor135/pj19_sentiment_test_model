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
