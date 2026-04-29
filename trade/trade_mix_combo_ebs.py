"""
Исполнение сделок по фьючерсу MIX в QUIK через .tri-файлы.

Target-state модель:
  1. Читает комбинированный прогноз текущего дня.
  2. По сигналу вычисляет целевую позицию (up → +qty, down → -qty, skip → 0).
  3. Из read_positions.py получает текущую позицию (тикер + количество).
  4. Дельта = цель − текущая → пишет закрытие (противоположный ордер) + открытие (нужный ордер).
  5. При ролловере (ticker_close ≠ ticker_open): закрывает старый, открывает новый.

Поддержка ручного override позиций через trade/state/positions.yaml.
Логирование с ротацией (3 файла). Защита от двойной записи через маркер state/{ticker}_{date}.done.
"""

from pathlib import Path
from datetime import datetime, date, time
import re
import logging
import sys
import yaml

# --- Импорт read_positions ---
_TRADE_DIR = Path(__file__).resolve().parent
if str(_TRADE_DIR) not in sys.path:
    sys.path.insert(0, str(_TRADE_DIR))
from read_positions import get_position, get_exported_at, is_export_fresh, has_yaml_override
from rebalance import build_rebalance_orders

# --- Конфигурация из mix/settings.yaml (common + combine) ---
ticker_lc = 'mix'
TICKER_DIR = Path(__file__).resolve().parents[1] / ticker_lc
if str(TICKER_DIR) not in sys.path:
    sys.path.insert(0, str(TICKER_DIR))
from config_loader import load_settings_for

cfg = load_settings_for(TICKER_DIR / "combine" / "sentiment_combine.py", "combine")

trade_settings_path = Path(__file__).parent / 'settings.yaml'
with open(trade_settings_path, encoding='utf-8') as f:
    trade_cfg = yaml.safe_load(f)

ticker_close = cfg['ticker_close']
ticker_open = cfg['ticker_open']

account = trade_cfg['accounts']['ebs']
trade_account = account['trade_account']
target_quantity = int(account[ticker_lc].get('target_quantity', 0))
done_marker_reset_before = trade_cfg['done_marker_reset_before']

# Пути к файлам
predict_dir = Path(account[ticker_lc]['predict_dir'])
log_path = Path(__file__).parent / "log"
trade_filepath = Path(account['trade_filepath'])
trade_path = trade_filepath.parent

# Создание необходимых директорий
trade_path.mkdir(parents=True, exist_ok=True)
log_path.mkdir(parents=True, exist_ok=True)
state_path = Path(__file__).parent / "state"
state_path.mkdir(parents=True, exist_ok=True)

# Имя файла прогноза на текущую дату
today = date.today()
current_filename = today.strftime("%Y-%m-%d") + ".txt"
current_filepath = predict_dir / current_filename

# --- Настройка логгирования ---
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file = log_path / f'trade_{ticker_lc}_combo_{timestamp}.txt'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Очистка старых логов (оставляем только 3 самых новых)
def cleanup_old_logs(log_dir: Path, prefix: str, max_files: int = 3):
    """Удаляет старые лог-файлы, оставляя max_files самых новых."""
    log_files = sorted(log_dir.glob(f"{prefix}_*.txt"))
    if len(log_files) > max_files:
        for old_file in log_files[:-max_files]:
            try:
                old_file.unlink()
                logger.info(f"Удалён старый лог: {old_file.name}")
            except Exception as e:
                logger.warning(f"Не удалось удалить {old_file}: {e}")

cleanup_old_logs(log_path, prefix=f"trade_{ticker_lc}_combo")


def parse_hhmmss(value: str) -> time:
    return datetime.strptime(value, "%H:%M:%S").time()


def should_delete_existing_done_marker(marker: Path, today: date, reset_before: str) -> bool:
    """Удаляем только сегодняшний done-маркер, созданный сегодня до reset_before."""
    marker_mtime = datetime.fromtimestamp(marker.stat().st_mtime)
    return marker_mtime.date() == today and marker_mtime.time() < parse_hhmmss(reset_before)

# --- Вспомогательные функции ---
def get_direction(filepath):
    """
    Извлекает предсказание (up/down/skip) из указанного файла.
    Проверяет несколько кодировок для корректного чтения.
    """
    encodings = ['utf-8', 'cp1251']
    for encoding in encodings:
        try:
            with filepath.open('r', encoding=encoding) as f:
                for line in f:
                    if "Предсказанное направление:" in line:
                        direction = line.split(":", 1)[1].strip().lower()
                        if direction in ['up', 'down', 'skip']:
                            return direction
            return None
        except UnicodeDecodeError:
            continue
    logger.error(f"Не удалось прочитать файл {filepath} с кодировками {encodings}.")
    return None

def get_next_trans_id(trade_filepath):
    """
    Определяет следующий TRANS_ID на основе максимального значения в файле.
    """
    trans_id = 1
    if trade_filepath.exists():
        try:
            with trade_filepath.open('r', encoding='cp1251') as f:
                content = f.read()
                trans_ids = re.findall(r'TRANS_ID=(\d+);', content)
                if trans_ids:
                    trans_id = max(int(tid) for tid in trans_ids if tid.isdigit()) + 1
        except (UnicodeDecodeError, ValueError) as e:
            logger.error(f"Ошибка при чтении TRANS_ID из {trade_filepath}: {e}")
    return trans_id

def create_trade_block(tr_id, ticker, action, quantity):
    """Формирует блок транзакции QUIK .tri-файла."""
    expiry_date = today.strftime("%Y%m%d")
    return (
        f'TRANS_ID={tr_id};'
        f'CLASSCODE=SPBFUT;'
        f'ACTION=Ввод заявки;'
        f'Торговый счет={trade_account};'
        f'К/П={action};'
        f'Тип=Рыночная;'
        f'Класс=SPBFUT;'
        f'Инструмент={ticker};'
        f'Цена=0;'
        f'Количество={quantity};'
        f'Условие исполнения=Поставить в очередь;'
        f'Комментарий={tr_id} {today.strftime("%y%m%d")};'
        f'Переносить заявку=Нет;'
        f'Дата экспирации={expiry_date};'
        f'Код внешнего пользователя=;\n'
    )

# --- Основная логика ---
# Защита от повторной записи: один тикер + одна дата = один маркер
done_marker = state_path / f"{ticker_lc}_{trade_account}_{today.strftime('%Y-%m-%d')}.done"
if done_marker.exists():
    if should_delete_existing_done_marker(done_marker, today, done_marker_reset_before):
        done_marker.unlink()
        logger.info(
            f"Маркер {done_marker.name} создан сегодня до {done_marker_reset_before} "
            f"(тестовый) — удаляем перед торговой проверкой."
        )
    else:
        logger.info(f"Маркер {done_marker.name} уже существует — транзакция за сегодня уже записана. Пропуск.\n")
        sys.exit(0)

# Проверка наличия файла прогноза на сегодня
if not current_filepath.exists() or current_filepath.stat().st_size == 0:
    logger.info(f"Файл {current_filepath} не существует или пуст. Нет торгов.\n")
    sys.exit(0)

# Получение направления из текущего файла
current_predict = get_direction(current_filepath)

if current_predict is None:
    logger.warning("Не удалось найти предсказанное направление в файле.\n")
    sys.exit(0)

logger.info(f"Текущее предсказание: {current_predict} (файл: {current_filepath})")
logger.info(f"Источник позиций: LUA-экспорт из QUIK (если доступен), иначе positions.yaml")
exported_at = get_exported_at()
if exported_at:
    logger.info(f"LUA-экспорт: {exported_at}")

# Защита от устаревшего positions.json: если override через positions.yaml есть
# не для всех используемых тикеров и LUA-экспорт не обновлялся сегодня —
# останавливаем пайплайн (hard-fail). Пустой/закомментированный positions.yaml
# не защищает: считается отсутствием override.
# Причина: торговать по вчерашним позициям опаснее, чем пропустить день.
_all_overridden = (
    has_yaml_override(trade_account, ticker_open)
    and has_yaml_override(trade_account, ticker_close)
)
if not _all_overridden and not is_export_fresh(today):
    logger.error(
        f"positions.json не обновлялся сегодня ({today}). "
        f"Последний экспорт: {exported_at or 'n/a'}. "
        f"Проверь QUIK и quik_export_positions.lua. Остановка пайплайна."
    )
    sys.exit(1)

# --- Определение целевой позиции ---
if current_predict == 'up':
    target_position = target_quantity
elif current_predict == 'down':
    target_position = -target_quantity
else:  # skip
    target_position = 0

logger.info(f"Целевая позиция: {target_position} контрактов")

# --- Получение текущей позиции ---
# Для основного контракта (ticker_open)
current_position = get_position(trade_account, ticker_open)
logger.info(f"Текущая позиция {ticker_open}: {current_position} контрактов")

# --- Вычисление дельты и формирование заявок ---
delta = target_position - current_position
logger.info(f"Дельта (цель - текущая): {delta}")

if delta == 0:
    logger.info("Позиция уже в целевом состоянии. Ордеры не требуются.\n")
    done_marker.touch()
    sys.exit(0)

# Получаем TRANS_ID для первой заявки
trans_id = get_next_trans_id(trade_filepath)
trade_content = ""

# --- Логика: приводим текущую позицию к целевой ---
for action, quantity, reason in build_rebalance_orders(current_position, target_position):
    trade_content += create_trade_block(trans_id, ticker_open, action, str(quantity))
    logger.info(f"  {reason}: {action} {quantity} контрактов {ticker_open}")
    trans_id += 1

# --- Ролловер: если ticker_close ≠ ticker_open, закрываем позицию в старом контракте ---
if ticker_close != ticker_open:
    old_position = get_position(trade_account, ticker_close)
    if old_position != 0:
        trans_id += 1
        close_qty = abs(old_position)
        if old_position > 0:
            action = 'Продажа'
        else:
            action = 'Покупка'
        trade_content += create_trade_block(trans_id, ticker_close, action, str(close_qty))
        logger.info(f"  Ролловер: закрытие позиции {old_position} контрактов {ticker_close} ({action})")

# --- Запись результата ---
if trade_content:
    with trade_filepath.open('a', encoding='cp1251') as f:
        f.write(trade_content)
    done_marker.touch()
    logger.info(f"\nДобавлены заявки в файл {trade_filepath}.")
    logger.info(f"Сигнал: {current_predict}, переход {current_position} → {target_position}\n")
else:
    logger.info(f"На {today} никакие ордеры не требуются. Позиция уже совпадает с целью.\n")
    done_marker.touch()
