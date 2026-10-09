"""Создание роли и базы данных проекта в PostgreSQL.

Имя роли, базы и пароль берутся из .env, подключение выполняется от суперпользователя
(по умолчанию postgres), пароль которого psql запросит в терминале.
С флагом --tables после этого создаются таблицы (существующие данные удаляются).

    python storage/schema.py [--superuser postgres] [--tables]
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import settings  # noqa: E402

STORAGE = ROOT / 'storage'


def find_psql():
    # psql из переменной PSQL, из PATH или из стандартной папки установки на Windows
    candidates = [os.getenv('PSQL'), shutil.which('psql')]
    candidates += sorted(Path('C:/Program Files/PostgreSQL').glob('*/bin/psql.exe'), reverse=True)
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    sys.exit('psql не найден: добавьте его в PATH или укажите путь в переменной PSQL')


def create_database(psql, superuser, password):
    print(f'Создание роли "{settings.db.user}" и базы "{settings.db.name}" '
          f'на {settings.db.host}:{settings.db.port} от имени "{superuser}"')
    return subprocess.call([
        psql, '-h', settings.db.host, '-p', str(settings.db.port), '-U', superuser, '-d', 'postgres',
        '-v', f'app_user={settings.db.user}',
        '-v', f'app_db={settings.db.name}',
        '-v', f'app_password={password}',
        '-f', str(STORAGE / 'schema.sql'),
    ])


def create_tables(psql, password):
    print('Создание таблиц')
    # Пароль роли приложения передаётся через окружение, чтобы psql его не спрашивал
    env = {**os.environ, 'PGPASSWORD': password}
    return subprocess.call([
        psql, '-h', settings.db.host, '-p', str(settings.db.port), '-U', settings.db.user,
        '-d', settings.db.name, '-q', '-f', str(STORAGE / 'tables.sql'),
    ], env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--superuser', default='postgres', help='суперпользователь PostgreSQL')
    parser.add_argument('--tables', action='store_true', help='создать таблицы (данные будут удалены)')
    args = parser.parse_args()

    password = settings.db.password.get_secret_value()
    if not password:
        sys.exit('В .env не задан DB_PASSWORD')

    psql = find_psql()
    code = create_database(psql, args.superuser, password)
    if code == 0 and args.tables:
        code = create_tables(psql, password)
    sys.exit(code)


if __name__ == '__main__':
    main()
