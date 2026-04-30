"""
Удаление PKL-артефактов отчётного пайплайна.

Скрипт запускается из корня проекта и рекурсивно ищет все `*.pkl` файлы
во вложенных папках. Основной сценарий использования — очистить кэш
`sentiment_scores.pkl` перед полным пересозданием отчётов через `run_report.py`.
Если передать имена папок-тикеров, очистка будет выполнена только внутри них.

Служебные директории проекта (`.git`, `.venv`, `__pycache__` и похожие) не
обрабатываются, чтобы не трогать файлы окружения и внутренние кэши инструментов.
Для предварительной проверки списка файлов используйте флаг `--dry-run`.

Запуск:
.venv/Scripts/python.exe del_pkl.py
.venv/Scripts/python.exe del_pkl.py --dry-run
.venv/Scripts/python.exe del_pkl.py rts mix
.venv/Scripts/python.exe del_pkl.py rts mix --dry-run
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path


SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "env",
    "venv",
}


def find_pkl_files(root: Path) -> list[Path]:
    """
    Возвращает отсортированный список PKL-файлов внутри `root`.

    Поиск выполняется рекурсивно, но файлы внутри служебных директорий из
    `SKIP_DIRS` пропускаются. Сортировка по относительному POSIX-пути делает
    вывод стабильным между запусками.
    """
    root = root.resolve()
    files: list[Path] = []

    for path in root.rglob("*.pkl"):
        relative_parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in relative_parts[:-1]):
            continue
        files.append(path)

    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def resolve_target_roots(project_root: Path, folders: Iterable[str]) -> list[Path]:
    """
    Возвращает корни поиска по позиционным аргументам CLI.

    Если папки не переданы, используется весь проект. Если переданы имена
    тикеров или относительные пути, каждый путь должен существовать и быть
    директорией внутри корня проекта.
    """
    folder_names = list(folders)
    if not folder_names:
        return [project_root]

    roots: list[Path] = []
    for folder in folder_names:
        target = (project_root / folder).resolve()
        try:
            target.relative_to(project_root)
        except ValueError as exc:
            raise ValueError(f"Папка вне проекта: {folder}") from exc
        if not target.is_dir():
            raise ValueError(f"Папка не найдена: {folder}")
        roots.append(target)

    return roots


def delete_files(paths: Iterable[Path]) -> list[Path]:
    """
    Удаляет переданные файлы и возвращает список реально обработанных путей.

    Функция не ищет файлы сама: вызывающий код явно передаёт набор путей,
    поэтому её удобно тестировать на временных файлах.
    """
    deleted: list[Path] = []

    for path in paths:
        path.unlink()
        deleted.append(path)

    return deleted


def parse_args() -> argparse.Namespace:
    """
    Разбирает аргументы командной строки.

    Позиционные аргументы задают папки-тикеры для выборочной очистки. `--dry-run`
    показывает список PKL-файлов, которые были бы удалены, но не выполняет
    удаление.
    """
    parser = argparse.ArgumentParser(
        description="Delete all *.pkl files generated inside this project."
    )
    parser.add_argument(
        "folders",
        nargs="*",
        help="Optional project folders to clean, for example: rts mix ng.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show files that would be deleted without removing them.",
    )
    return parser.parse_args()


def main() -> None:
    """
    Точка входа CLI.

    Определяет корень проекта как папку, где лежит `del_pkl.py`, выбирает корни
    поиска по аргументам, находит PKL, печатает список файлов и удаляет их, если
    запуск не был dry-run.
    """
    args = parse_args()
    root = Path(__file__).resolve().parent
    try:
        target_roots = resolve_target_roots(root, args.folders)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    pkl_files_by_text: dict[str, Path] = {}
    for target_root in target_roots:
        for path in find_pkl_files(target_root):
            pkl_files_by_text[path.relative_to(root).as_posix()] = path
    pkl_files = [pkl_files_by_text[key] for key in sorted(pkl_files_by_text)]

    if not pkl_files:
        print("PKL files not found.")
        return

    action = "Would delete" if args.dry_run else "Deleting"
    print(f"{action} {len(pkl_files)} PKL file(s):")
    for path in pkl_files:
        print(path.relative_to(root).as_posix())

    if args.dry_run:
        return

    delete_files(pkl_files)
    print("Done.")


if __name__ == "__main__":
    main()
