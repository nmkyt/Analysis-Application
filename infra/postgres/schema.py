"""Создание роли приложения и базы данных на установленном PostgreSQL.

Имя роли, базы и пароль берутся из .env, скрипт выполняется через psql от имени
суперпользователя (по умолчанию postgres), пароль которого psql запросит в терминале.
Если роль и база уже есть, обновляется только пароль роли.

    python infra/postgres/schema.py [--superuser postgres]
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from sales_analytics.config import settings

SCHEMA_SQL = Path(__file__).resolve().parent / 'schema.sql'


def find_psql():
    # psql из переменной PSQL, из PATH или из стандартной папки установки на Windows
    candidates = [os.getenv('PSQL'), shutil.which('psql')]
    candidates += sorted(Path('C:/Program Files/PostgreSQL').glob('*/bin/psql.exe'), reverse=True)
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    sys.exit('psql не найден: добавьте его в PATH или укажите путь в переменной PSQL')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--superuser', default='postgres', help='суперпользователь PostgreSQL')
    args = parser.parse_args()

    password = settings.db.password.get_secret_value()
    if not password:
        sys.exit('В .env не задан DB_PASSWORD')

    print(f'Создание роли "{settings.db.user}" и базы "{settings.db.name}" '
          f'на {settings.db.host}:{settings.db.port} от имени "{args.superuser}"')
    sys.exit(subprocess.call([
        find_psql(), '-h', settings.db.host, '-p', str(settings.db.port), '-U', args.superuser, '-d', 'postgres',
        '-v', f'app_user={settings.db.user}',
        '-v', f'app_db={settings.db.name}',
        '-v', f'app_password={password}',
        '-f', str(SCHEMA_SQL),
    ]))


if __name__ == '__main__':
    main()
