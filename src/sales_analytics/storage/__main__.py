"""Создание таблиц учётной системы в базе из .env.

Таблицы пересоздаются, существующие данные удаляются, поэтому нужен флаг --yes.
Роль и база данных должны уже существовать - см. infra/.

    python -m sales_analytics.storage --yes
"""
import argparse
import sys

from ..config import settings
from ..exceptions import StorageError
from .schema import create_tables


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--yes', action='store_true', help='подтвердить пересоздание таблиц')
    args = parser.parse_args()

    if not args.yes:
        parser.print_help()
        sys.exit('\nТаблицы не созданы: добавьте --yes, чтобы подтвердить удаление существующих данных')
    try:
        print(f'Создание таблиц в базе "{settings.db.name}" на {settings.db.host}:{settings.db.port}')
        create_tables()
    except StorageError as e:
        sys.exit(str(e))
    print('Готово')


if __name__ == '__main__':
    main()
