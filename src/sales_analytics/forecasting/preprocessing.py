"""Предобработка данных для прогноза спроса.

build_panel() строит недельную панель «неделя × база × позиция»:
  - ряд существует с появления позиции на базе до её вывода из ассортимента;
  - недели без продаж - нули;
  - недели, когда на базе не было ни одной продажи, - база закрыта, продажи неизвестны (NaN);
  - future_weeks недель после конца данных - будущее, для прогноза (продажи NaN).

Строка выборки - ряд и целевая неделя T. y - продажи в неделю T, признаки из истории продаж -
только по неделям не позже T - h, то есть известные на момент прогноза.
build_training_set() отдаёт строки с известными продажами, build_forecast_set() - строки
будущей недели T = последняя известная неделя + h.
"""
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from ..storage import DemandData

SERIES_KEY = ['branch_id', 'product_id']
KEY_COLUMNS = ['week'] + SERIES_KEY
TARGET = 'qty'
MAX_HORIZON = 52
EXTRA_LAGS = 3                    # лаги h, h+1, ..., h+EXTRA_LAGS
ROLLING_WINDOWS = (4, 13, 26)
WEEKS_PER_YEAR = 52.18
# Признаки целевой недели, известные заранее: календарь и справочники
CALENDAR_FEATURES = ['week_sin', 'week_cos', 'working_days']
STATIC_FEATURES = ['category_id', 'branch_format', 'unit']
# Вес единицы товара: не признак, нужен для пересчёта продаж в тонны
WEIGHT = 'kg_per_unit'


@dataclass(frozen=True)
class TrainingSet:
    """Выборка для модели: признаки X, целевая переменная y (NaN для будущих недель)
    и описание строк keys: неделя, база, позиция, вес единицы товара."""

    X: pd.DataFrame
    y: pd.Series
    keys: pd.DataFrame
    horizon: int

    def __len__(self):
        return len(self.y)

    def select(self, mask):
        """Подвыборка по булевой маске строк."""
        mask = np.asarray(mask)
        return TrainingSet(self.X[mask], self.y[mask], self.keys[mask], self.horizon)

    def to_frame(self):
        """Ключи, y и признаки одной таблицей."""
        return pd.concat([self.keys, self.y, self.X], axis=1)


def build_panel(data: DemandData, future_weeks: int = 0) -> pd.DataFrame:
    """Недельная панель продаж с календарными и справочными признаками целевой недели."""
    known_weeks = _full_weeks(data.calendar)
    future = pd.date_range(known_weeks[-1], periods=future_weeks + 1, freq='7D')[1:]
    weeks = known_weeks.append(future)
    series = _series(data, last_day=weeks[-1] + pd.Timedelta(days=6))

    # Сетка: каждый ряд × недели, в которые он существовал
    panel = series.merge(pd.DataFrame({'week': weeks}), how='cross')
    panel = panel[(panel['week'] >= _monday(panel['start'])) & (panel['week'] <= _monday(panel['end']))]

    sales = data.daily_sales.assign(week=_monday(data.daily_sales['date']))
    weekly = sales.groupby(KEY_COLUMNS, as_index=False)[TARGET].sum()
    panel = panel.merge(weekly, on=KEY_COLUMNS, how='left')
    panel[TARGET] = panel[TARGET].fillna(0.0)
    panel['is_future'] = panel['week'] > known_weeks[-1]

    # База закрыта, если за неделю на ней не было ни одной продажи
    open_weeks = sales[['week', 'branch_id']].drop_duplicates().assign(is_open=True)
    panel = panel.merge(open_weeks, on=['week', 'branch_id'], how='left')
    panel.loc[panel['is_open'].isna() | panel['is_future'], TARGET] = np.nan

    panel = panel.merge(_calendar_features(data.calendar, weeks), on='week', how='left')
    panel = panel[KEY_COLUMNS + [TARGET, 'is_future', WEIGHT] + CALENDAR_FEATURES + STATIC_FEATURES]
    return panel.sort_values(KEY_COLUMNS, ignore_index=True)


def build_training_set(panel: pd.DataFrame, horizon: int = 1) -> TrainingSet:
    """Строки с известными продажами: база работала и у ряда есть история."""
    frame, features = _features(panel, horizon)
    return _training_set(frame[frame[TARGET].notna() & ~frame['is_future']], features, horizon)


def build_forecast_set(panel: pd.DataFrame, horizon: int = 1) -> TrainingSet:
    """Строки будущей недели T = последняя известная неделя + horizon."""
    last_known = panel.loc[~panel['is_future'], 'week'].max()
    target_week = last_known + pd.Timedelta(weeks=horizon)
    if target_week > panel['week'].max():
        raise ValueError(f'В панели нет недели {target_week.date()}: постройте её с future_weeks >= {horizon}')
    frame, features = _features(panel, horizon)
    return _training_set(frame[frame['week'] == target_week], features, horizon)


def _features(panel, horizon):
    """Панель с признаками из истории продаж и список всех признаков модели."""
    if not 1 <= horizon <= MAX_HORIZON:
        raise ValueError(f'Горизонт должен быть от 1 до {MAX_HORIZON} недель, получено {horizon}')
    h = horizon

    # Широкая таблица недели × ряды; вне ряда, в закрытые и будущие недели - NaN
    qty = panel.pivot(index='week', columns=SERIES_KEY, values=TARGET).asfreq('7D')
    known = qty.shift(h)  # для недели T - продажи недели T - h, последние известные
    features = {f'qty_lag{h + k}': known.shift(k) for k in range(EXTRA_LAGS + 1)}
    features['qty_lag52'] = qty.shift(52)
    for window in ROLLING_WINDOWS:
        features[f'qty_mean{window}'] = known.rolling(window, min_periods=1).mean()
    sold = known.gt(0).astype(float).where(known.notna())
    features['nonzero_share13'] = sold.rolling(13, min_periods=1).mean()

    history = pd.concat({name: frame.stack(SERIES_KEY) for name, frame in features.items()}, axis=1)
    frame = panel.join(history, on=KEY_COLUMNS)
    for column in STATIC_FEATURES:
        frame[column] = frame[column].astype('category')
    return frame, list(features) + CALENDAR_FEATURES + STATIC_FEATURES


def _training_set(frame, features, horizon):
    # Ряд без продаж за 26 недель до прогноза прогнозировать не по чему
    frame = frame[frame[f'qty_mean{ROLLING_WINDOWS[-1]}'].notna()].reset_index(drop=True)
    return TrainingSet(X=frame[features], y=frame[TARGET],
                       keys=frame[KEY_COLUMNS + [WEIGHT]], horizon=horizon)


def _series(data, last_day):
    """Ряды «база × позиция» с датами начала и конца и справочными признаками."""
    branches = pd.DataFrame([asdict(b) for b in data.branches]).rename(
        columns={'id': 'branch_id', 'format': 'branch_format'})
    products = pd.DataFrame([asdict(p) for p in data.products]).rename(columns={'id': 'product_id'})
    series = data.assortment.merge(products, on='product_id').merge(branches, on='branch_id')

    dates = series[['first_stocked_on', 'introduced_on', 'opened_on']].apply(pd.to_datetime)
    series['start'] = dates.max(axis=1)
    discontinued = pd.to_datetime(series['discontinued_on'])
    series['end'] = (discontinued - pd.Timedelta(days=1)).fillna(last_day)
    return series[series['end'] >= series['start']]


def _full_weeks(calendar):
    """Понедельники недель, целиком входящих в период календаря."""
    first, last = calendar['date'].min(), calendar['date'].max()
    weeks = pd.date_range(_monday(pd.Series([first])).iloc[0], last, freq='7D')
    return weeks[(weeks >= first) & (weeks + pd.Timedelta(days=6) <= last)]


def _calendar_features(calendar, weeks):
    # За пределами календаря рабочими считаются дни с понедельника по пятницу
    days = pd.DataFrame({'date': pd.date_range(weeks[0], weeks[-1] + pd.Timedelta(days=6))})
    days = days.merge(calendar[['date', 'is_working_day']].astype({'date': days['date'].dtype}), on='date', how='left')
    days['is_working_day'] = days['is_working_day'].fillna(days['date'].dt.weekday < 5).astype(bool)
    weekly = (days.assign(week=_monday(days['date']))
              .groupby('week', as_index=False)
              .agg(working_days=('is_working_day', 'sum')))
    week_of_year = weekly['week'].dt.isocalendar().week.astype(float)
    weekly['week_sin'] = np.sin(2 * np.pi * week_of_year / WEEKS_PER_YEAR)
    weekly['week_cos'] = np.cos(2 * np.pi * week_of_year / WEEKS_PER_YEAR)
    return weekly


def _monday(dates):
    dates = pd.to_datetime(dates)
    return dates - pd.to_timedelta(dates.dt.weekday, unit='D')
