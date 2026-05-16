from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from buhinvest_analize import pl_buhinvest_interactive


class BuhinvestInteractiveCliTest(unittest.TestCase):
    def test_cli_opens_generated_html_reports_in_chrome(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            excel_path = tmp_path / "buhinvest.xlsx"
            plotly_output = tmp_path / "pl_buhinvest_interactive.html"
            qs_output = tmp_path / "pl_buhinvest_interactive_qs.html"

            with (
                patch.object(
                    pl_buhinvest_interactive,
                    "generate_reports",
                    return_value=(plotly_output, qs_output),
                ),
                patch.object(
                    pl_buhinvest_interactive,
                    "open_html_reports_in_chrome",
                    create=True,
                ) as open_html_reports_in_chrome,
                patch.object(sys, "argv", ["pl_buhinvest_interactive.py", "--file", str(excel_path)]),
            ):
                pl_buhinvest_interactive.main()

            open_html_reports_in_chrome.assert_called_once_with(
                Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                [plotly_output, qs_output],
            )


if __name__ == "__main__":
    unittest.main()
