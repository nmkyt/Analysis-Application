import json
import math

import numpy as np
import pandas as pd
import pytest

from sales_analytics.exceptions import ModelError
from sales_analytics.forecasting import model as model_module
from sales_analytics.forecasting.model import METHODS, DemandModel, baselines, evaluate, evaluation_path, forecast,     load, save, split_by_time, train
from sales_analytics.forecasting.preprocessing import build_panel, build_training_set
from tests.data import make_data

# Меньше итераций бустинга, чтобы тесты шли секунды
FAST_PARAMS = {**model_module.MODEL_PARAMS, 'max_iter': 30, 'early_stopping': False}


@pytest.fixture
def fast_model(monkeypatch):
    # train() передаёт валидационную выборку, поэтому ранняя остановка остаётся включённой
    monkeypatch.setitem(model_module.MODEL_PARAMS, 'max_iter', 30)


@pytest.fixture
def training_set(demand_data):
    return build_training_set(build_panel(demand_data), 1)


# ===== Метрики =====

def test_evaluate_on_hand_computed_example():
    # В кг: факт [0, 2, 2], прогноз [1, 2, 1], ошибка [1, 0, -1]
    metrics = evaluate(fact=[0, 2, 4], pred=[1, 2, 2], kg_per_unit=[1, 1, 0.5])
    assert metrics['mae_kg'] == pytest.approx(2 / 3)
    assert metrics['rmse_kg'] == pytest.approx(math.sqrt(2 / 3))
    assert metrics['wape'] == pytest.approx(0.5)
    assert metrics['bias'] == pytest.approx(0.0)
    # Сумма квадратов отклонений факта от среднего 4/3: 16/9 + 4/9 + 4/9 = 24/9
    assert metrics['r2'] == pytest.approx(1 - 2 / (24 / 9))


def test_bias_sign_shows_overforecast():
    assert evaluate([10, 10], [12, 13], [1, 1])['bias'] == pytest.approx(0.25)
    assert evaluate([10, 10], [8, 7], [1, 1])['bias'] == pytest.approx(-0.25)


def test_perfect_forecast():
    metrics = evaluate([1, 5, 3], [1, 5, 3], [2, 2, 2])
    assert metrics['mae_kg'] == metrics['rmse_kg'] == metrics['wape'] == metrics['bias'] == 0
    assert metrics['r2'] == 1


def test_zero_sales_give_undefined_relative_metrics():
    metrics = evaluate([0, 0], [1, 2], [1, 1])
    assert np.isnan(metrics['wape']) and np.isnan(metrics['bias'])
    assert metrics['mae_kg'] == pytest.approx(1.5)


def test_r2_is_undefined_for_constant_sales():
    metrics = evaluate([10, 10], [12, 13], [1, 1])
    assert np.isnan(metrics['r2'])
    assert metrics['wape'] == pytest.approx(0.25)


# ===== Разбиение и ориентиры =====

def test_split_by_time_is_ordered_and_disjoint(training_set):
    train_set, valid_set, test_set = split_by_time(training_set, test_weeks=10, valid_weeks=5)
    assert train_set.keys['week'].max() < valid_set.keys['week'].min()
    assert valid_set.keys['week'].max() < test_set.keys['week'].min()
    assert test_set.keys['week'].nunique() == 10
    assert valid_set.keys['week'].nunique() == 5
    assert len(train_set) + len(valid_set) + len(test_set) == len(training_set)


def test_split_by_time_needs_enough_weeks(training_set):
    with pytest.raises(ModelError, match='Недель'):
        split_by_time(training_set, test_weeks=60, valid_weeks=30)


def test_baselines_fall_back_to_long_mean():
    X = pd.DataFrame({'qty_lag2': [5.0, np.nan], 'qty_lag52': [np.nan, 7.0],
                      'qty_mean4': [3.0, np.nan], 'qty_mean26': [4.0, 6.0]})
    result = baselines(X, horizon=2)
    assert result['naive'].tolist() == [5.0, 6.0]
    assert result['seasonal'].tolist() == [4.0, 7.0]
    assert result['mean4'].tolist() == [3.0, 6.0]


# ===== DemandModel =====

def test_model_predicts_non_negative_values(training_set):
    model = DemandModel(**FAST_PARAMS).fit(training_set.X, training_set.y)
    predictions = model.predict(training_set.X)
    assert predictions.shape == (len(training_set),)
    assert (predictions >= 0).all()
    assert model.n_iter_ == 30


def test_model_uses_training_categories(training_set):
    """Коды категорий при прогнозе совпадают с обучением, даже если порядок категорий другой."""
    model = DemandModel(**FAST_PARAMS).fit(training_set.X, training_set.y)
    shuffled = training_set.X.copy()
    for column in ['category_id', 'branch_format', 'unit']:
        categories = list(reversed(shuffled[column].cat.categories))
        shuffled[column] = pd.Categorical(shuffled[column].astype(object), categories=categories)
    np.testing.assert_allclose(model.predict(shuffled), model.predict(training_set.X))


def test_model_scales_by_series_level(training_set):
    """Ряд с вдвое большей историей получает вдвое больший прогноз."""
    model = DemandModel(**FAST_PARAMS).fit(training_set.X, training_set.y)
    X = training_set.X.head(20)
    doubled = X.copy()
    history = [column for column in X.columns if column.startswith('qty_')]
    doubled[history] = X[history] * 2
    # Признак log_scale тоже меняется, поэтому равенство приблизительное
    ratio = model.predict(doubled) / model.predict(X)
    assert np.median(ratio) == pytest.approx(2, rel=0.5)


# ===== Обучение, сохранение, прогноз =====

@pytest.fixture
def long_data():
    # После теста (26 недель) и валидации (13) в обучении должен остаться хотя бы год: иначе лаг 52 пустой
    return make_data(n_weeks=110)


@pytest.fixture
def trained(long_data, fast_model):
    return train(build_panel(long_data), horizon=1)


def test_train_compares_model_with_baselines(trained):
    assert list(trained.metrics.index) == list(METHODS.values())
    assert list(trained.metrics.columns) == ['mae_kg', 'rmse_kg', 'wape', 'bias', 'r2']
    # Позиция в листах выведена из ассортимента до тестового периода
    assert set(trained.wape_by_unit.columns) == {'m', 'pcs'}
    assert len(trained.test) > 0 and trained.test['fact'].notna().all()
    assert trained.periods['train'][1] < trained.periods['valid'][0] < trained.periods['test'][0]


def test_save_and_load_roundtrip(trained, training_set, tmp_path):
    path = save(trained, tmp_path)
    assert path == tmp_path / 'demand_h1.joblib'
    assert evaluation_path(1, tmp_path).exists()

    loaded, metadata = load(1, tmp_path)
    np.testing.assert_allclose(loaded.predict(training_set.X), trained.model.predict(training_set.X))
    assert metadata['horizon'] == 1
    assert metadata['features'] == list(training_set.X.columns)
    assert json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))['metrics'].keys() == \
        set(METHODS.values())


def test_train_with_short_history_raises(demand_data, fast_model):
    # 85 недель: после теста и валидации в обучении меньше года, лаг 52 пустой
    with pytest.raises(ModelError, match='qty_lag52'):
        train(build_panel(demand_data), horizon=1)


def test_load_missing_model_raises(tmp_path):
    with pytest.raises(ModelError, match='не найдена'):
        load(1, tmp_path)


def test_forecast_after_end_of_data(long_data, trained, tmp_path):
    save(trained, tmp_path)
    result = forecast(long_data, horizons=(1,), directory=tmp_path)
    assert len(result) == 4
    assert (result['week'] == result['origin_week'] + pd.Timedelta(weeks=1)).all()
    assert (result['forecast'] >= 0).all()
    weights = result['product_id'].map({1: 2.0, 2: 0.5})
    np.testing.assert_allclose(result['forecast_kg'], result['forecast'] * weights)
    assert set(result['branch_code']) == {'A', 'B'}
