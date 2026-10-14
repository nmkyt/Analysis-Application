"""Маленький DemandData без базы и без датасета для тестов.

Две базы, три позиции, 85 полных недель с понедельника 01.01.2024:
  - позиция 3 выводится из ассортимента в среду 15.01.2025;
  - позиция 2 появляется на базе 2 в среду 06.03.2024;
  - база 2 закрыта недели CLOSED_WEEKS: ни одной продажи;
  - продажи - по вторникам, каждая третья неделя ряда без продаж.
"""
from datetime import date

import numpy as np
import pandas as pd

from sales_analytics.storage import Branch, DemandData, Product

START = pd.Timestamp('2024-01-01')
N_WEEKS = 85
CLOSED_WEEKS = range(20, 24)
DISCONTINUED = date(2025, 1, 15)
LATE_START = date(2024, 3, 6)


def make_data(start=START, n_weeks=N_WEEKS):
    days = pd.date_range(start, periods=n_weeks * 7)
    calendar = pd.DataFrame({'date': days, 'is_working_day': days.weekday < 5})

    branches = [Branch(1, 'A', 'hypermarket', date(2010, 1, 1)),
                Branch(2, 'B', 'minimarket', date(2010, 1, 1))]
    products = [
        Product(1, 'P1', 'Труба 20x20', 10, 'm', 2.0, date(2020, 1, 1), None),
        Product(2, 'P2', 'Саморез', 20, 'pcs', 0.5, date(2020, 1, 1), None),
        Product(3, 'P3', 'Лист 1 мм', 10, 'sheet', 8.0, date(2020, 1, 1), DISCONTINUED),
    ]
    assortment = pd.DataFrame([
        {'branch_id': b.id, 'product_id': p.id,
         'first_stocked_on': pd.Timestamp(LATE_START if (b.id, p.id) == (2, 2) else start)}
        for b in branches for p in products
    ])

    rng = np.random.default_rng(0)
    rows = []
    for week in range(n_weeks):
        tuesday = start + pd.Timedelta(weeks=week, days=1)
        for branch in branches:
            if branch.id == 2 and week in CLOSED_WEEKS:
                continue
            for product in products:
                if week % 3 == product.id % 3:
                    continue
                if (branch.id, product.id) == (2, 2) and tuesday < pd.Timestamp(LATE_START):
                    continue
                if product.discontinued_on and tuesday >= pd.Timestamp(product.discontinued_on):
                    continue
                rows.append({'date': tuesday, 'branch_id': branch.id, 'product_id': product.id,
                             'qty': float(rng.integers(1, 50) * product.id)})
    daily_sales = pd.DataFrame(rows)
    return DemandData(branches, products, assortment, daily_sales, calendar)
