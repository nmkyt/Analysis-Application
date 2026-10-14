"""Работа с базой из .env: создание таблиц и выгрузка датасета в CSV.

    python -m sales_analytics.storage create --yes   пересоздать таблицы (данные удаляются)
    python -m sales_analytics.storage export         выгрузить таблицы в data/ (DATASET_DIR)

Роль и база данных должны уже существовать - см. infra/.
"""
import argparse
import sys
from pathlib import Path

from ..config import settings
from ..exceptions import StorageError
from .export import export_dataset
from .schema import create_tables


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    create_parser = commands.add_parser('create', help='пересоздать таблицы')
    create_parser.add_argument('--yes', action='store_true', help='подтвердить удаление существующих данных')
    export_parser = commands.add_parser('export', help='выгрузить таблицы в CSV')
    export_parser.add_argument('--dir', type=Path, default=settings.dataset_dir,
                               help='папка датасета (по умолчанию: %(default)s)')
    args = parser.parse_args()

    where = f'"{settings.db.name}" на {settings.db.host}:{settings.db.port}'
    try:
        if args.command == 'create':
            if not args.yes:
                create_parser.print_help()
                sys.exit('\nТаблицы не созданы: добавьте --yes, чтобы подтвердить удаление существующих данных')
            print(f'Создание таблиц в базе {where}')
            create_tables()
        else:
            print(f'Выгрузка таблиц из базы {where} в {args.dir}')
            export_dataset(args.dir, progress=lambda table, path: print(
                f'  {table:<24} {path.stat().st_size / 1e6:6.1f} МБ'))
    except StorageError as e:
        sys.exit(str(e))
    print('Готово')


if __name__ == '__main__':
    main()
