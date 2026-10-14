"""Чтение данных учётной системы: из базы или из датасета в CSV (см. export.py).

Оба источника дают одинаковый DemandData.
"""
from dataclasses import fields
from pathlib import Path

import pandas as pd
import psycopg
from psycopg.rows import class_row

from ..config import settings
from ..exceptions import DataError, StorageError
from .entities import Branch, DemandData, Product
from .postgres import connect

BRANCHES_SQL = 'SELECT id, code, format, opened_on FROM branches ORDER BY id'

PRODUCTS_SQL = """
SELECT id, sku, name, category_id, unit, kg_per_unit::float8 AS kg_per_unit, introduced_on, discontinued_on
FROM products
ORDER BY id
"""

# Позиция появляется на базе с первым движением товара по ней
ASSORTMENT_SQL = """
SELECT branch_id, product_id, min(moved_on) AS first_stocked_on
FROM stock_movements
GROUP BY branch_id, product_id
"""

DAILY_SALES_SQL = """
SELECT sale_date AS date, branch_id, product_id, quantity::float8 AS qty
FROM mv_daily_sales
"""

CALENDAR_SQL = 'SELECT date, is_working_day FROM calendar ORDER BY date'


# ===== База данных =====

def load_demand_data(conn=None):
    """Справочники и история продаж для прогноза спроса из базы."""
    if conn is None:
        with connect() as conn:
            return load_demand_data(conn)
    try:
        return DemandData(
            branches=_objects(conn, BRANCHES_SQL, Branch),
            products=_objects(conn, PRODUCTS_SQL, Product),
            assortment=_frame(conn, ASSORTMENT_SQL, dates=['first_stocked_on']),
            daily_sales=_frame(conn, DAILY_SALES_SQL, dates=['date']),
            calendar=_frame(conn, CALENDAR_SQL, dates=['date']),
        )
    except psycopg.Error as e:
        raise StorageError(f'Не удалось прочитать данные для прогноза: {e}') from e


def _objects(conn, sql, cls):
    with conn.cursor(row_factory=class_row(cls)) as cursor:
        return cursor.execute(sql).fetchall()


def _frame(conn, sql, dates=()):
    with conn.cursor() as cursor:
        cursor.execute(sql)
        frame = pd.DataFrame(cursor.fetchall(), columns=[column.name for column in cursor.description])
    for column in dates:
        frame[column] = pd.to_datetime(frame[column])
    return frame


# ===== Датасет в CSV =====

def load_demand_data_csv(directory=None):
    """То же, что load_demand_data(), но из файлов {таблица}.csv.gz (по умолчанию DATASET_DIR)."""
    directory = Path(directory or settings.dataset_dir)

    def read(table, columns, dates=()):
        path = directory / f'{table}.csv.gz'
        if not path.exists():
            raise DataError(f'Нет файла {path}: выгрузите датасет командой python -m sales_analytics.storage export')
        # PostgreSQL выгружает boolean как t/f
        frame = pd.read_csv(path, usecols=columns, true_values=['t'], false_values=['f'])
        for column in dates:
            frame[column] = pd.to_datetime(frame[column], format='ISO8601')
        return frame

    branches = read('branches', [f.name for f in fields(Branch)], dates=['opened_on'])
    products = read('products', [f.name for f in fields(Product)], dates=['introduced_on', 'discontinued_on'])

    movements = read('stock_movements', ['moved_on', 'branch_id', 'product_id'], dates=['moved_on'])
    assortment = (movements.groupby(['branch_id', 'product_id'], as_index=False)['moved_on'].min()
                  .rename(columns={'moved_on': 'first_stocked_on'}))

    # Как в mv_daily_sales: строки выполненных заказов, суммы по дням, базам и позициям
    orders = read('sales_orders', ['id', 'branch_id', 'created_at', 'status'], dates=['created_at'])
    orders = orders[orders['status'] == 'completed']
    lines = read('sales_order_lines', ['order_id', 'product_id', 'quantity'])
    sales = lines.merge(orders, left_on='order_id', right_on='id')
    sales['date'] = sales['created_at'].dt.normalize()
    daily_sales = (sales.groupby(['date', 'branch_id', 'product_id'], as_index=False)['quantity'].sum()
                   .rename(columns={'quantity': 'qty'}))

    return DemandData(
        branches=_records(branches, Branch, ['opened_on']),
        products=_records(products, Product, ['introduced_on', 'discontinued_on']),
        assortment=assortment,
        daily_sales=daily_sales,
        calendar=read('calendar', ['date', 'is_working_day'], dates=['date']),
    )


def _records(frame, cls, dates):
    frame = frame.astype(object).where(frame.notna(), None)
    for column in dates:
        frame[column] = [value.date() if value is not None else None for value in frame[column]]
    return [cls(**record) for record in frame.to_dict('records')]
