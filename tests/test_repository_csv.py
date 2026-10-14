"""load_demand_data_csv() на маленьких файлах в формате выгрузки PostgreSQL."""
from datetime import date

import pandas as pd
import pytest

from sales_analytics.exceptions import DataError
from sales_analytics.storage import Branch, Product, load_demand_data_csv

TABLES = {
    'branches': pd.DataFrame({
        'id': [1], 'code': ['A'], 'name': ['База'], 'format': ['hypermarket'], 'opened_on': ['2010-01-01'],
    }),
    'products': pd.DataFrame({
        'id': [1, 2], 'sku': ['P1', 'P2'], 'name': ['Труба', 'Лист'], 'category_id': [10, 20],
        'unit': ['m', 'sheet'], 'kg_per_unit': [2.5, 8.0], 'attributes': ['{"diameter_mm": 20}', '{}'],
        'introduced_on': ['2020-01-01', '2020-02-01'], 'discontinued_on': [None, '2024-06-01'],
    }),
    'stock_movements': pd.DataFrame({
        'id': [1, 2, 3], 'moved_on': ['2024-01-05', '2024-01-02', '2024-01-03'],
        'branch_id': [1, 1, 1], 'product_id': [1, 1, 2], 'quantity': [10, 5, 3],
    }),
    'sales_orders': pd.DataFrame({
        'id': [1, 2, 3], 'branch_id': [1, 1, 1],
        # PostgreSQL выгружает время то с долями секунды, то без них
        'created_at': ['2024-01-08 10:00:00', '2024-01-08 18:30:15.123456', '2024-01-09 09:00:00'],
        'status': ['completed', 'completed', 'cancelled'],
    }),
    'sales_order_lines': pd.DataFrame({
        'order_id': [1, 2, 2, 3], 'line_no': [1, 1, 2, 1],
        'product_id': [1, 1, 2, 1], 'quantity': [1.5, 2.0, 4.0, 100.0],
    }),
    'calendar': pd.DataFrame({'date': ['2024-01-06', '2024-01-08'], 'is_working_day': ['f', 't']}),
}


@pytest.fixture
def dataset_dir(tmp_path):
    for table, frame in TABLES.items():
        frame.to_csv(tmp_path / f'{table}.csv.gz', index=False)
    return tmp_path


def test_reference_tables_become_dataclasses(dataset_dir):
    data = load_demand_data_csv(dataset_dir)
    assert data.branches == [Branch(1, 'A', 'hypermarket', date(2010, 1, 1))]
    assert data.products[0] == Product(1, 'P1', 'Труба', 10, 'm', 2.5, date(2020, 1, 1), None)
    assert data.products[1].discontinued_on == date(2024, 6, 1)


def test_assortment_starts_at_first_movement(dataset_dir):
    assortment = load_demand_data_csv(dataset_dir).assortment.set_index('product_id')
    assert assortment.loc[1, 'first_stocked_on'] == pd.Timestamp('2024-01-02')
    assert assortment.loc[2, 'first_stocked_on'] == pd.Timestamp('2024-01-03')


def test_daily_sales_count_only_completed_orders(dataset_dir):
    sales = load_demand_data_csv(dataset_dir).daily_sales.set_index(['date', 'product_id'])['qty']
    assert sales.to_dict() == {
        (pd.Timestamp('2024-01-08'), 1): 3.5,
        (pd.Timestamp('2024-01-08'), 2): 4.0,
    }


def test_calendar_booleans_are_parsed(dataset_dir):
    calendar = load_demand_data_csv(dataset_dir).calendar
    assert calendar['is_working_day'].tolist() == [False, True]
    assert calendar['is_working_day'].dtype == bool


def test_missing_file_raises_data_error(dataset_dir):
    (dataset_dir / 'calendar.csv.gz').unlink()
    with pytest.raises(DataError, match='calendar'):
        load_demand_data_csv(dataset_dir)
