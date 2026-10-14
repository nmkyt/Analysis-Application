"""Выгрузка таблиц учётной системы в CSV: датасет в data/.

Каждая таблица - файл {таблица}.csv.gz с заголовком, строки отсортированы по первичному ключу.
Файлы сжимаются без даты в заголовке gzip, поэтому повторная выгрузка тех же данных
даёт те же файлы.
"""
import gzip

import psycopg

from ..config import settings
from ..exceptions import StorageError
from .postgres import connect

# Порядок, в котором таблицы можно загрузить обратно: справочники раньше документов
TABLES = [
    'branches', 'categories', 'suppliers', 'products', 'services', 'customers',
    'calendar', 'metal_price_index', 'price_history',
    'sales_orders', 'sales_order_lines', 'order_services',
    'purchase_receipts', 'purchase_receipt_lines',
    'stock_transfers', 'stock_transfer_lines',
    'stock_movements',
]


def export_dataset(directory=None, conn=None, progress=None):
    """Выгружает все таблицы в directory (по умолчанию DATASET_DIR). progress(table, path) - после каждой."""
    directory = directory or settings.dataset_dir
    if conn is None:
        with connect() as conn:
            return export_dataset(directory, conn, progress)

    directory.mkdir(parents=True, exist_ok=True)
    try:
        for table in TABLES:
            path = directory / f'{table}.csv.gz'
            # Первичный ключ у всех таблиц - первая или первые две колонки
            sql = f'COPY (SELECT * FROM {table} ORDER BY 1, 2) TO STDOUT (FORMAT csv, HEADER)'
            with conn.cursor() as cursor, gzip.GzipFile(path, 'wb', mtime=0) as file:
                with cursor.copy(sql) as copy:
                    for chunk in copy:
                        file.write(chunk)
            if progress:
                progress(table, path)
    except psycopg.Error as e:
        raise StorageError(f'Не удалось выгрузить таблицы: {e}') from e
    except OSError as e:
        raise StorageError(f'Не удалось записать датасет в {directory}: {e}') from e
