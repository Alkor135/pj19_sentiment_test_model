"""
Генерация двух HTML-отчетов по данным Buhinvest:
- Plotly-отчет с расширенной аналитикой
- QuantStats tearsheet на реальной доходности счета
"""

from pathlib import Path
import argparse
import yaml

try:
    from buhinvest_analize.buhinvest_reports import generate_reports
except ModuleNotFoundError:
    from buhinvest_reports import generate_reports


SAVE_PATH = Path(__file__).resolve().parent
SETTINGS_FILE = SAVE_PATH / "settings.yaml"


def load_file_path() -> Path:
    with SETTINGS_FILE.open(encoding="utf-8") as f:
        settings = yaml.safe_load(f) or {}
    return Path(settings["buhinvest_excel_path"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Построить интерактивные HTML-отчёты из Excel-файла Buhinvest.")
    parser.add_argument("--file", type=Path, default=load_file_path(), help="Путь к Excel-файлу Buhinvest.")
    args = parser.parse_args()

    plotly_output, qs_output = generate_reports(args.file, SAVE_PATH)
    print(f"Интерактивный отчёт сохранён: {plotly_output}")
    print(f"QuantStats отчёт сохранён: {qs_output}")


if __name__ == "__main__":
    main()
