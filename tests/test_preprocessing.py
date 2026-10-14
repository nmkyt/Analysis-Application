from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from sales_analytics.forecasting.preprocessing import build_forecast_set, build_panel, build_training_set
from tests.data import CLOSED_WEEKS, LATE_START, N_WEEKS, START, make_data


def series(panel, branch_id, product_id):
    return panel[(panel['branch_id'] == branch_id) & (panel['product_id'] == product_id)].set_index('week')


def week(n):
    return START + pd.Timedelta(weeks=n)


# ===== Панель =====

def test_panel_covers_all_full_weeks(demand_data):
    panel = build_panel(demand_data)
    assert panel['week'].min() == START
    assert panel['week'].max() == week(N_WEEKS - 1)
    assert panel['week'].nunique() == N_WEEKS


def test_partial_edge_weeks_are_excluded():
    # Календарь со среды по вторник: первая и последняя недели неполные
    data = make_data()
    calendar = data.calendar[(data.calendar['date'] >= START + pd.Timedelta(days=2))
                             & (data.calendar['date'] <= week(N_WEEKS - 1) + pd.Timedelta(days=1))]
    panel = build_panel(replace(data, calendar=calendar))
    assert panel['week'].min() == week(1)
    assert panel['week'].max() == week(N_WEEKS - 2)


def test_series_starts_when_product_appears_on_branch(demand_data):
    late = series(build_panel(demand_data), 2, 2)
    assert late.index.min() == pd.Timestamp(LATE_START) - pd.Timedelta(days=pd.Timestamp(LATE_START).weekday())


def test_series_ends_before_discontinuation(demand_data):
    # Вывод в среду 15.01.2025: последний день ряда - вторник 14.01, неделя с 13.01
    discontinued = series(build_panel(demand_data), 1, 3)
    assert discontinued.index.max() == pd.Timestamp('2025-01-13')


def test_weeks_without_sales_are_zero(demand_data):
    panel = series(build_panel(demand_data), 1, 1)
    # Позиция 1 не продаётся в недели, где week % 3 == 1
    assert (panel.loc[[week(1), week(4), week(7)], 'qty'] == 0).all()
    assert (panel.loc[[week(0), week(2), week(3)], 'qty'] > 0).all()


def test_weekly_sales_are_summed(demand_data):
    panel = series(build_panel(demand_data), 1, 2)
    sales = demand_data.daily_sales
    expected = sales[(sales['branch_id'] == 1) & (sales['product_id'] == 2)
                     & (sales['date'] >= week(3)) & (sales['date'] < week(4))]['qty'].sum()
    assert panel.loc[week(3), 'qty'] == expected


def test_closed_branch_weeks_are_missing(demand_data):
    panel = build_panel(demand_data)
    closed = panel[(panel['branch_id'] == 2) & panel['week'].isin([week(n) for n in CLOSED_WEEKS])]
    assert len(closed) > 0
    assert closed['qty'].isna().all()
    # На другой базе те же недели открыты
    other = panel[(panel['branch_id'] == 1) & panel['week'].isin([week(n) for n in CLOSED_WEEKS])]
    assert other['qty'].notna().all()


def test_calendar_features_of_target_week(demand_data):
    panel = build_panel(demand_data)
    assert set(panel['working_days']) == {5}
    assert panel['week_sin'].between(-1, 1).all() and panel['week_cos'].between(-1, 1).all()


# ===== Выборка для обучения =====

@pytest.mark.parametrize('horizon', [1, 2, 4])
def test_lags_are_shifted_by_horizon(demand_data, horizon):
    panel = build_panel(demand_data)
    data = build_training_set(panel, horizon)
    qty = panel.set_index(['week', 'branch_id', 'product_id'])['qty']
    rows = data.keys.assign(**data.X[[f'qty_lag{horizon}', 'qty_lag52']])
    sample = rows[rows['week'] >= week(60)].head(50)
    for row in sample.itertuples():
        key = (row.branch_id, row.product_id)
        assert _same(getattr(row, f'qty_lag{horizon}'), qty.get((row.week - pd.Timedelta(weeks=horizon), *key)))
        assert _same(row.qty_lag52, qty.get((row.week - pd.Timedelta(weeks=52), *key)))


def test_rolling_mean_uses_only_known_weeks(demand_data):
    panel = build_panel(demand_data)
    data = build_training_set(panel, 2)
    target = data.keys.index[(data.keys['week'] == week(40)) & (data.keys['branch_id'] == 1)
                             & (data.keys['product_id'] == 1)][0]
    history = series(panel, 1, 1).loc[week(35):week(38), 'qty']  # недели T-5 ... T-2
    assert data.X.loc[target, 'qty_mean4'] == pytest.approx(history.mean())


@pytest.mark.parametrize('horizon', [1, 3])
def test_features_do_not_see_the_future(demand_data, horizon):
    """Изменение продаж недели T меняет признаки только для целевых недель от T + horizon."""
    panel = build_panel(demand_data)
    changed_week = week(50)
    changed = panel.copy()
    changed.loc[changed['week'] == changed_week, 'qty'] *= 100

    before, after = build_training_set(panel, horizon), build_training_set(changed, horizon)
    known = before.keys['week'] < changed_week + pd.Timedelta(weeks=horizon)
    pd.testing.assert_frame_equal(before.X[known], after.X[known])
    assert not before.X[~known].equals(after.X[~known])


def test_training_set_excludes_closed_weeks(demand_data):
    data = build_training_set(build_panel(demand_data), 1)
    assert data.y.notna().all()
    closed = data.keys[(data.keys['branch_id'] == 2) & data.keys['week'].isin([week(n) for n in CLOSED_WEEKS])]
    assert closed.empty


def test_training_set_requires_history(demand_data):
    data = build_training_set(build_panel(demand_data), 1)
    # В первую неделю данных истории ещё нет
    assert data.keys['week'].min() == week(1)
    assert data.X['qty_mean26'].notna().all()


def test_training_set_columns(demand_data):
    data = build_training_set(build_panel(demand_data), 2)
    assert list(data.X.columns) == [
        'qty_lag2', 'qty_lag3', 'qty_lag4', 'qty_lag5', 'qty_lag52', 'qty_mean4', 'qty_mean13', 'qty_mean26',
        'nonzero_share13', 'week_sin', 'week_cos', 'working_days', 'category_id', 'branch_format', 'unit',
    ]
    assert list(data.keys.columns) == ['week', 'branch_id', 'product_id', 'kg_per_unit']
    assert all(data.X[column].dtype == 'category' for column in ['category_id', 'branch_format', 'unit'])
    assert len(data) == len(data.X) == len(data.keys)


@pytest.mark.parametrize('horizon', [0, 53])
def test_invalid_horizon_raises(demand_data, horizon):
    with pytest.raises(ValueError, match='Горизонт'):
        build_training_set(build_panel(demand_data), horizon)


# ===== Прогноз на будущее =====

def test_future_weeks_have_unknown_sales(demand_data):
    panel = build_panel(demand_data, future_weeks=3)
    future = panel[panel['is_future']]
    assert sorted(future['week'].unique()) == [week(N_WEEKS), week(N_WEEKS + 1), week(N_WEEKS + 2)]
    assert future['qty'].isna().all()
    # За пределами календаря рабочие дни - с понедельника по пятницу
    assert (future['working_days'] == 5).all()


def test_future_weeks_do_not_change_training_set(demand_data):
    plain = build_training_set(build_panel(demand_data), 2)
    extended = build_training_set(build_panel(demand_data, future_weeks=4), 2)
    pd.testing.assert_frame_equal(plain.X, extended.X)
    pd.testing.assert_series_equal(plain.y, extended.y)


@pytest.mark.parametrize('horizon', [1, 3])
def test_forecast_set_targets_week_after_data(demand_data, horizon):
    panel = build_panel(demand_data, future_weeks=3)
    rows = build_forecast_set(panel, horizon)
    assert set(rows.keys['week']) == {week(N_WEEKS - 1 + horizon)}
    assert rows.y.isna().all()
    # Выведенная из ассортимента позиция 3 не прогнозируется
    assert set(rows.keys['product_id']) == {1, 2}
    assert len(rows) == 4


def test_forecast_lag_is_last_known_week(demand_data):
    panel = build_panel(demand_data, future_weeks=1)
    rows = build_forecast_set(panel, 1)
    last = panel[panel['week'] == week(N_WEEKS - 1)].set_index(['branch_id', 'product_id'])['qty']
    lags = rows.X['qty_lag1'].set_axis(pd.MultiIndex.from_frame(rows.keys[['branch_id', 'product_id']]))
    pd.testing.assert_series_equal(lags.sort_index(), last.loc[lags.index].sort_index(), check_names=False)


def test_forecast_beyond_panel_raises(demand_data):
    panel = build_panel(demand_data, future_weeks=1)
    with pytest.raises(ValueError, match='future_weeks'):
        build_forecast_set(panel, 2)


def _same(a, b):
    a, b = np.nan if a is None else a, np.nan if b is None else b
    return (np.isnan(a) and np.isnan(b)) or a == b
