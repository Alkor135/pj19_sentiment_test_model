"""
Генерация двух HTML-отчетов по данным Buhinvest:
- Plotly-отчет с расширенной аналитикой
- QuantStats tearsheet на реальной доходности счета
"""

from pathlib import Path
import argparse
import subprocess
import yaml

try:
    from buhinvest_analize.buhinvest_reports import generate_reports
except ModuleNotFoundError:
    from buhinvest_reports import generate_reports


SAVE_PATH = Path(__file__).resolve().parent
SETTINGS_FILE = SAVE_PATH / "settings.yaml"
CHROME_PATH = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def load_file_path() -> Path:
    with SETTINGS_FILE.open(encoding="utf-8") as f:
        settings = yaml.safe_load(f) or {}
    return Path(settings["buhinvest_excel_path"])


def open_html_reports_in_chrome(chrome_path: Path, reports: list[Path]) -> None:
    if not chrome_path.exists():
        print(f"Google Chrome не найден: {chrome_path}")
        raise SystemExit(1)

    subprocess.Popen([str(chrome_path), "--new-window", *[str(report) for report in reports]])


def main() -> None:
    parser = argparse.ArgumentParser(description="Построить интерактивные HTML-отчёты из Excel-файла Buhinvest.")
    parser.add_argument("--file", type=Path, default=load_file_path(), help="Путь к Excel-файлу Buhinvest.")
    parser.add_argument(
        "--open-browser",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Открыть HTML-отчёты в новом окне Chrome после создания.",
    )
    parser.add_argument("--chrome-path", type=Path, default=CHROME_PATH, help="Путь к chrome.exe.")
    args = parser.parse_args()

    plotly_output, qs_output = generate_reports(args.file, SAVE_PATH)
    print(f"Интерактивный отчёт сохранён: {plotly_output}")
    print(f"QuantStats отчёт сохранён: {qs_output}")
    if args.open_browser:
        reports = [plotly_output, qs_output]
        open_html_reports_in_chrome(args.chrome_path, reports)
        print("Открываю HTML-отчёты в Chrome:")
        for report in reports:
            print(f"- {report}")


if __name__ == "__main__":
    main()
