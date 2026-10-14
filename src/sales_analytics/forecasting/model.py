"""Модель прогноза спроса: обучение, сравнение с ориентирами, сохранение, прогноз.

Одна модель градиентного бустинга на все ряды, отдельная модель на каждый горизонт,
продажи нормируются на масштаб ряда (DemandModel). Пуассоновская функция потерь подходит
для неотрицательных количеств с большим числом нулей.

Качество оценивается на последних TEST_WEEKS неделях, ранняя остановка - по VALID_WEEKS неделям
перед ними. Метрики считаются в килограммах, чтобы позиции в метрах, штуках и листах
были сопоставимы. Сохраняется модель, переобученная на всех данных с найденным числом итераций.
"""
import json
from dataclasses import asdict, dataclass
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from ..config import settings
from ..exceptions import ModelError
from ..storage import DemandData
from .preprocessing import STATIC_FEATURES, WEIGHT, TrainingSet, build_forecast_set, build_panel, \
    build_training_set

HORIZONS = (1, 2, 3, 4)
TEST_WEEKS = 26
VALID_WEEKS = 13
MODEL_PARAMS = {
    'loss': 'poisson',
    'learning_rate': 0.05,
    'max_iter': 2000,
    'max_leaf_nodes': 63,
    'min_samples_leaf': 100,
    'l2_regularization': 1.0,
    'early_stopping': True,
    'n_iter_no_change': 50,
    'random_state': 0,
}
# Модель и ориентиры: колонка в таблице прогнозов теста -> название в отчётах
METHODS = {
    'model': 'модель',
    'naive': 'как h нед. назад',
    'seasonal': 'как год назад',
    'mean4': 'среднее за 4 нед.',
}


class DemandModel:
    """Бустинг по продажам, нормированным на масштаб ряда.

    Ряды отличаются по масштабу на порядки (метры труб и штуки метизов), и одной модели
    трудно работать со всеми сразу. Поэтому продажи и признаки из их истории делятся
    на среднее за 26 недель, а прогноз умножается обратно. Вес строки равен масштабу ряда,
    так что функция потерь соответствует ошибке в исходных единицах.
    """

    SCALE = 'qty_mean26'

    def __init__(self, **params):
        self.estimator = HistGradientBoostingRegressor(**params)
        self.categories = {}

    @property
    def n_iter_(self):
        return self.estimator.n_iter_

    def get_params(self):
        return self.estimator.get_params()

    def fit(self, X, y, X_val=None, y_val=None):
        # Категории запоминаются, чтобы при прогнозе коды категорий совпадали с обучением
        self.categories = {column: X[column].cat.categories.tolist() for column in STATIC_FEATURES}
        scale = self._scale(X)
        validation = {}
        if X_val is not None:
            scale_val = self._scale(X_val)
            validation = {'X_val': self._scaled(X_val), 'y_val': y_val / scale_val, 'sample_weight_val': scale_val}
        self.estimator.fit(self._scaled(X), y / scale, sample_weight=scale, **validation)
        return self

    def predict(self, X):
        return self.estimator.predict(self._scaled(X)) * self._scale(X).to_numpy()

    def _scale(self, X):
        # Ряд без продаж за 26 недель: масштаб 1, прогноз остаётся в исходных единицах
        return X[self.SCALE].where(X[self.SCALE] > 0, 1.0)

    def _scaled(self, X):
        history = [column for column in X.columns if column.startswith('qty_')]
        scaled = X.copy()
        scaled[history] = X[history].div(self._scale(X), axis=0)
        scaled['log_scale'] = np.log1p(X[self.SCALE])
        for column, categories in self.categories.items():
            scaled[column] = pd.Categorical(X[column].astype(object), categories=categories)
        return scaled


@dataclass(frozen=True)
class TrainingResult:
    """Обученная модель и её оценка на тестовом периоде."""

    model: DemandModel
    horizon: int
    features: list[str]
    periods: dict[str, list[str]]  # первая и последняя целевая неделя обучения, валидации и теста
    metrics: pd.DataFrame          # модель и ориентиры × метрики
    wape_by_unit: pd.DataFrame     # модель и ориентиры × единица измерения
    test: pd.DataFrame             # прогнозы теста: ключи, unit, факт, модель и ориентиры


def train(panel: pd.DataFrame, horizon: int, save_data=False) -> TrainingResult:
    """Обучает модель на горизонт horizon и сравнивает её с ориентирами на тесте.

    save_data - сохранить выборку для обучения в training_dir/training_h{h}.csv.gz.
    """
    data = build_training_set(panel, horizon)
    train_set, valid_set, test_set = split_by_time(data)
    # Бустинг не обучается на признаке без единого значения, например на лаге 52 при истории меньше года
    empty = [column for column in train_set.X.columns if train_set.X[column].isna().all()]
    if empty:
        raise ModelError(f'В обучающей части ({_period(train_set)[0]} - {_period(train_set)[1]}) нет значений '
                         f'признаков {", ".join(empty)}: нужна более длинная история продаж')
    if save_data:
        _save_training_set(data, valid_set, test_set)

    model = DemandModel(**MODEL_PARAMS)
    model.fit(train_set.X, train_set.y, X_val=valid_set.X, y_val=valid_set.y)

    test = test_set.keys.assign(unit=test_set.X['unit'].astype(str), fact=test_set.y,
                                model=model.predict(test_set.X), **baselines(test_set.X, horizon))
    metrics = pd.DataFrame({METHODS[m]: evaluate(test['fact'], test[m], test[WEIGHT]) for m in METHODS}).T
    wape_by_unit = pd.DataFrame({
        METHODS[m]: {unit: evaluate(part['fact'], part[m], part[WEIGHT])['wape']
                     for unit, part in test.groupby('unit')}
        for m in METHODS
    }).T

    final = DemandModel(**{**MODEL_PARAMS, 'max_iter': model.n_iter_, 'early_stopping': False})
    final.fit(data.X, data.y)

    return TrainingResult(
        model=final,
        horizon=horizon,
        features=list(data.X.columns),
        periods={name: _period(part) for name, part in
                 [('train', train_set), ('valid', valid_set), ('test', test_set)]},
        metrics=metrics,
        wape_by_unit=wape_by_unit,
        test=test,
    )


def split_by_time(data: TrainingSet, test_weeks=TEST_WEEKS, valid_weeks=VALID_WEEKS):
    """Обучение, валидация и тест по целевой неделе: тест - последние test_weeks недель."""
    weeks = np.sort(data.keys['week'].unique())
    if len(weeks) <= test_weeks + valid_weeks:
        raise ModelError(f'Недель в данных {len(weeks)}, нужно больше {test_weeks + valid_weeks}')
    valid_start, test_start = weeks[-(test_weeks + valid_weeks)], weeks[-test_weeks]
    week = data.keys['week']
    return (data.select(week < valid_start),
            data.select((week >= valid_start) & (week < test_start)),
            data.select(week >= test_start))


def baselines(X: pd.DataFrame, horizon: int) -> dict:
    """Наивные прогнозы; если значения нет (база была закрыта), берётся среднее за 26 недель."""
    fallback = X['qty_mean26']
    return {
        'naive': X[f'qty_lag{horizon}'].fillna(fallback).to_numpy(),
        'seasonal': X['qty_lag52'].fillna(fallback).to_numpy(),
        'mean4': X['qty_mean4'].fillna(fallback).to_numpy(),
    }


def evaluate(fact, pred, kg_per_unit) -> dict:
    """Метрики в килограммах: MAE, RMSE, WAPE, bias и R² (см. README)."""
    fact = np.asarray(fact, dtype=float) * np.asarray(kg_per_unit, dtype=float)
    error = np.asarray(pred, dtype=float) * np.asarray(kg_per_unit, dtype=float) - fact
    total, spread = fact.sum(), ((fact - fact.mean()) ** 2).sum()
    return {
        'mae_kg': np.abs(error).mean(),
        'rmse_kg': np.sqrt((error ** 2).mean()),
        'wape': np.abs(error).sum() / total if total else np.nan,
        'bias': error.sum() / total if total else np.nan,
        'r2': 1 - (error ** 2).sum() / spread if spread else np.nan,
    }


def forecast(data: DemandData, horizons=HORIZONS, directory=None) -> pd.DataFrame:
    """Прогноз сохранёнными моделями на horizons недель после конца данных."""
    panel = build_panel(data, future_weeks=max(horizons))
    origin = panel.loc[~panel['is_future'], 'week'].max()
    parts = []
    for horizon in horizons:
        model, _ = load(horizon, directory)
        rows = build_forecast_set(panel, horizon)
        parts.append(rows.keys.assign(horizon=horizon, forecast=model.predict(rows.X)))
    result = pd.concat(parts, ignore_index=True)

    branches = pd.DataFrame([asdict(b) for b in data.branches])[['id', 'code']]
    products = pd.DataFrame([asdict(p) for p in data.products])[['id', 'sku', 'name', 'unit']]
    result = (result.merge(branches.rename(columns={'id': 'branch_id', 'code': 'branch_code'}), on='branch_id')
              .merge(products.rename(columns={'id': 'product_id'}), on='product_id'))
    result['origin_week'] = origin
    result['forecast_kg'] = result['forecast'] * result[WEIGHT]
    columns = ['origin_week', 'week', 'horizon', 'branch_id', 'branch_code', 'product_id', 'sku', 'name',
               'unit', 'forecast', 'forecast_kg']
    return result[columns].sort_values(['horizon', 'branch_id', 'product_id'], ignore_index=True)


def save(result: TrainingResult, directory=None):
    """Сохраняет модель demand_h{h}.joblib, описание .json и прогнозы теста _test.csv.gz."""
    directory = directory or settings.models_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'demand_h{result.horizon}.joblib'
    metadata = {
        'horizon': result.horizon,
        'trained_at': datetime.now().isoformat(timespec='seconds'),
        'n_iter': result.model.n_iter_,
        'params': result.model.get_params(),
        'features': result.features,
        'categories': result.model.categories,
        'periods': result.periods,
        'metrics': result.metrics.to_dict(orient='index'),
        'wape_by_unit': result.wape_by_unit.to_dict(orient='index'),
    }
    try:
        joblib.dump(result.model, path)
        path.with_suffix('.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        result.test.to_csv(evaluation_path(result.horizon, directory), index=False)
    except OSError as e:
        raise ModelError(f'Не удалось сохранить модель в {path}: {e}') from e
    return path


def load(horizon: int, directory=None):
    """Модель и её описание, сохранённые save()."""
    path = (directory or settings.models_dir) / f'demand_h{horizon}.joblib'
    if not path.exists():
        raise ModelError(f'Модель на горизонт {horizon} не найдена: {path}. '
                         f'Обучите её: python -m sales_analytics.forecasting train')
    metadata = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    return joblib.load(path), metadata


def evaluation_path(horizon: int, directory=None):
    """Файл с прогнозами модели и ориентиров на тестовом периоде."""
    return (directory or settings.models_dir) / f'demand_h{horizon}_test.csv.gz'


def _save_training_set(data, valid_set, test_set):
    frame = data.to_frame()
    frame.insert(0, 'split', 'train')
    frame.loc[frame['week'] >= valid_set.keys['week'].min(), 'split'] = 'valid'
    frame.loc[frame['week'] >= test_set.keys['week'].min(), 'split'] = 'test'
    settings.training_dir.mkdir(parents=True, exist_ok=True)
    path = settings.training_dir / f'training_h{data.horizon}.csv.gz'
    try:
        frame.to_csv(path, index=False)
    except OSError as e:
        raise ModelError(f'Не удалось сохранить выборку в {path}: {e}') from e


def _period(part: TrainingSet):
    weeks = part.keys['week']
    return [weeks.min().date().isoformat(), weeks.max().date().isoformat()]
