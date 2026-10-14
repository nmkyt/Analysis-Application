"""Работа с базой из .env: создание роли и базы, таблиц и выгрузка датасета в CSV.

    python -m sales_analytics.storage init [--superuser postgres]   роль и база на установленном PostgreSQL
    python -m sales_analytics.storage create --yes                   пересоздать таблицы (данные удаляются)
    python -m sales_analytics.storage export                         выгрузить таблицы в data/ (DATASET_DIR)

В Docker роль и база создаются при первом запуске контейнера - см. infra/docker-compose.yml.
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

from ..config import settings
from ..exceptions import StorageError
from .export import export_dataset
from .postgres import create_database
from .schema import create_tables


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    init_parser = commands.add_parser('init', help='создать роль и базу')
    init_parser.add_argument('--superuser', default='postgres',
                             help='суперпользователь PostgreSQL (по умолчанию: %(default)s)')
    create_parser = commands.add_parser('create', help='пересоздать таблицы')
    create_parser.add_argument('--yes', action='store_true', help='подтвердить удаление существующих данных')
    export_parser = commands.add_parser('export', help='выгрузить таблицы в CSV')
    export_parser.add_argument('--dir', type=Path, default=settings.dataset_dir,
                               help='папка датасета (по умолчанию: %(default)s)')
    args = parser.parse_args()

    where = f'"{settings.db.name}" на {settings.db.host}:{settings.db.port}'
    try:
        if args.command == 'init':
            print(f'Создание роли "{settings.db.user}" и базы {where} от имени "{args.superuser}"')
            password = None if os.getenv('PGPASSWORD') else getpass.getpass(f'Пароль {args.superuser}: ')
            create_database(args.superuser, password)
        elif args.command == 'create':
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
