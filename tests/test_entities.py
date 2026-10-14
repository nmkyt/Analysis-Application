from dataclasses import replace

import pytest

from sales_analytics.exceptions import DataError


def test_valid_data_is_accepted(demand_data):
    assert len(demand_data.branches) == 2
    assert len(demand_data.products) == 3


@pytest.mark.parametrize('table, column', [
    ('assortment', 'first_stocked_on'),
    ('daily_sales', 'qty'),
    ('calendar', 'is_working_day'),
])
def test_missing_column_raises_data_error(demand_data, table, column):
    broken = getattr(demand_data, table).drop(columns=column)
    with pytest.raises(DataError, match=column):
        replace(demand_data, **{table: broken})
