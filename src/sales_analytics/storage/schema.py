"""Таблицы учётной системы: создание по sql/tables.sql.

Роль и база данных создаются отдельно - см. infra/.
"""
from pathlib import Path

import psycopg

from ..exceptions import StorageError
from .postgres import connect

TABLES_SQL = Path(__file__).resolve().parent / 'sql' / 'tables.sql'


def tables_sql():
    """Текст tables.sql без команд psql (\\set и т. п.), которые драйвер не понимает."""
    return '\n'.join(line for line in TABLES_SQL.read_text(encoding='utf-8').splitlines()
                     if not line.lstrip().startswith('\\'))


def create_tables(conn=None):
    """Пересоздаёт таблицы, индексы и представления. Существующие данные удаляются."""
    try:
        if conn is not None:
            conn.execute(tables_sql())
            return
        with connect() as conn:
            conn.execute(tables_sql())
    except psycopg.Error as e:
        raise StorageError(f'Не удалось создать таблицы: {e}') from e
