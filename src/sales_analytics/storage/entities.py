"""Данные учётной системы, нужные для прогноза спроса.

Справочники - датаклассы, история продаж - таблицы pandas с фиксированным набором колонок:
продаж сотни тысяч строк, и список объектов был бы медленным и тяжёлым.
"""
from dataclasses import dataclass
from datetime import date
from typing import ClassVar

import pandas as pd

from ..exceptions import DataError


@dataclass(frozen=True)
class Branch:
    """Металлобаза или пункт выдачи."""

    id: int
    code: str
    format: str
    opened_on: date


@dataclass(frozen=True)
class Product:
    """Позиция номенклатуры."""

    id: int
    sku: str
    name: str
    category_id: int
    unit: str
    kg_per_unit: float
    introduced_on: date
    discontinued_on: date | None


@dataclass(frozen=True)
class DemandData:
    """Справочники и история продаж для прогноза спроса.

    assortment  - когда позиция впервые появилась на базе
    daily_sales - продажи по выполненным заказам, в единицах товара
    calendar    - производственный календарь, задаёт период данных
    """

    branches: list[Branch]
    products: list[Product]
    assortment: pd.DataFrame
    daily_sales: pd.DataFrame
    calendar: pd.DataFrame

    COLUMNS: ClassVar[dict[str, list[str]]] = {
        'assortment': ['branch_id', 'product_id', 'first_stocked_on'],
        'daily_sales': ['date', 'branch_id', 'product_id', 'qty'],
        'calendar': ['date', 'is_working_day'],
    }

    def __post_init__(self):
        for name, columns in self.COLUMNS.items():
            missing = set(columns) - set(getattr(self, name).columns)
            if missing:
                raise DataError(f'В таблице {name} нет колонок: {", ".join(sorted(missing))}')
