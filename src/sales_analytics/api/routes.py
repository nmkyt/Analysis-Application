"""Эндпоинты API: состояние, модели, прогноз, датасет, фоновые задачи."""
import math
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request, status

from ..config import settings
from ..exceptions import StorageError
from ..forecasting.model import forecast, latest_forecast, save, save_forecast, saved_models, train
from ..forecasting.preprocessing import MAX_HORIZON, build_panel
from ..storage import connect, export_dataset, load_demand_data, load_demand_data_csv
from ..storage.export import TABLES
from .jobs import JobConflict
from .schemas import ForecastPage, ForecastRequest, ForecastRow, ForecastSummary, Health, Job, ModelDetail, \
    ModelSummary, NetworkWeek, Source, TrainRequest

router = APIRouter()


# ===== Сервис =====

@router.get('/health', response_model=Health, tags=['сервис'])
def health():
    """Доступна ли база, есть ли датасет и какие модели обучены."""
    try:
        with connect(connect_timeout=3) as conn:
            conn.execute('SELECT 1')
        database, error = True, None
    except StorageError as e:
        database, error = False, str(e)
    return Health(database=database, database_error=error, dataset=_dataset_ready(), models=list(saved_models()))


@router.get('/jobs', response_model=list[Job], tags=['сервис'])
def list_jobs(request: Request):
    """Фоновые задачи с момента запуска API."""
    return request.app.state.jobs.list()


@router.get('/jobs/{job_id}', response_model=Job, tags=['сервис'])
def get_job(job_id: str, request: Request):
    """Статус фоновой задачи: running, done или failed (с текстом ошибки)."""
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Задача {job_id} не найдена')
    return job


# ===== Модели =====

@router.get('/models', response_model=list[ModelSummary], tags=['модели'])
def list_models():
    """Обученные модели и их метрики на тесте."""
    return [_clean(metadata) for metadata in saved_models().values()]


@router.get('/models/{horizon}', response_model=ModelDetail, tags=['модели'])
def get_model(horizon: int):
    """Модель на горизонт horizon: признаки, периоды, метрики, WAPE по единицам измерения."""
    metadata = saved_models().get(horizon)
    if metadata is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Модель на горизонт {horizon} не обучена')
    return _clean(metadata)


@router.post('/models/train', response_model=Job, status_code=status.HTTP_202_ACCEPTED, tags=['модели'])
def start_training(body: TrainRequest, request: Request):
    """Запускает обучение в фоне (около 2,5 минут на горизонт); статус - GET /jobs/{id}."""
    horizons = sorted(set(body.horizons))

    def run():
        panel = build_panel(_load(body.source))
        metrics = {}
        for horizon in horizons:
            result = train(panel, horizon, save_data=body.save_data)
            save(result)
            metrics[horizon] = _clean(result.metrics.to_dict(orient='index'))
        return {'horizons': horizons, 'metrics': metrics}

    return _start(request, 'train', run)


# ===== Прогноз =====

@router.post('/forecasts', response_model=ForecastSummary, tags=['прогноз'])
def create_forecast(body: ForecastRequest):
    """Прогноз сохранёнными моделями на недели после конца данных; сохраняется в output/forecasts."""
    result = forecast(_load(body.source), sorted(set(body.horizons)))
    path = save_forecast(result)
    return _summary(result, path)


@router.get('/forecasts/latest', response_model=ForecastPage, tags=['прогноз'])
def get_latest_forecast(
        branch: Annotated[str | None, Query(description='код базы, например YUN')] = None,
        product_id: int | None = None,
        horizon: Annotated[int | None, Query(ge=1, le=MAX_HORIZON)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
):
    """Строки последнего прогноза по базам и позициям, с фильтрами и постранично."""
    frame, _ = _latest()
    origin = _origin(frame)
    if branch is not None:
        frame = frame[frame['branch_code'] == branch]
    if product_id is not None:
        frame = frame[frame['product_id'] == product_id]
    if horizon is not None:
        frame = frame[frame['horizon'] == horizon]
    page = frame.iloc[offset:offset + limit]
    rows = page.assign(origin_week=page['origin_week'].dt.date, week=page['week'].dt.date).to_dict('records')
    return ForecastPage(origin_week=origin, total=len(frame), offset=offset, limit=limit,
                        rows=[ForecastRow(**row) for row in rows])


@router.get('/forecasts/latest/summary', response_model=ForecastSummary, tags=['прогноз'])
def get_latest_summary():
    """Последний прогноз по всей сети: тонн в неделю."""
    frame, path = _latest()
    return _summary(frame, path)


# ===== Датасет =====

@router.post('/dataset/export', response_model=Job, status_code=status.HTTP_202_ACCEPTED, tags=['датасет'])
def start_export(request: Request):
    """Выгружает таблицы из базы в DATASET_DIR в фоне (около 2 минут); статус - GET /jobs/{id}."""
    def run():
        export_dataset(settings.dataset_dir)
        return {'directory': str(settings.dataset_dir), 'tables': TABLES}

    return _start(request, 'export', run)


# ===== Помощники =====

def _load(source: Source):
    return load_demand_data_csv() if source is Source.dataset else load_demand_data()


def _start(request, kind, func):
    try:
        return request.app.state.jobs.start(kind, func)
    except JobConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e


def _dataset_ready():
    return all((settings.dataset_dir / f'{table}.csv.gz').exists() for table in TABLES)


def _latest():
    frame, path = latest_forecast()
    if frame is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Прогнозов ещё нет: POST /forecasts')
    return frame, path


def _origin(frame: pd.DataFrame):
    return frame['origin_week'].iloc[0].date()


def _summary(frame: pd.DataFrame, path):
    weekly = frame.groupby(['horizon', 'week'], as_index=False)['forecast_kg'].sum()
    weeks = [NetworkWeek(horizon=row.horizon, week=row.week.date(), tonnes=row.forecast_kg / 1000)
             for row in weekly.itertuples()]
    return ForecastSummary(origin_week=_origin(frame), file=path.name, rows=len(frame), weeks=weeks)


def _clean(value):
    """NaN и бесконечность -> None: в JSON таких чисел нет."""
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
