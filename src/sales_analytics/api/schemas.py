"""Модели запросов и ответов API."""
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

from ..forecasting.model import HORIZONS
from ..forecasting.preprocessing import MAX_HORIZON

Horizon = Annotated[int, Field(ge=1, le=MAX_HORIZON, description='горизонт прогноза в неделях')]
Metrics = dict[str, dict[str, float | None]]


class Source(StrEnum):
    """Откуда читать данные: база из .env или датасет в DATASET_DIR."""

    db = 'db'
    dataset = 'dataset'


class TrainRequest(BaseModel):
    horizons: list[Horizon] = Field(default=list(HORIZONS), min_length=1)
    source: Source = Source.dataset
    save_data: bool = Field(default=False, description='сохранить выборки для обучения в output/training')


class ForecastRequest(BaseModel):
    horizons: list[Horizon] = Field(default=list(HORIZONS), min_length=1)
    source: Source = Source.dataset


class JobStatus(StrEnum):
    running = 'running'
    done = 'done'
    failed = 'failed'


class Job(BaseModel):
    """Фоновая задача: обучение моделей или выгрузка датасета."""

    id: str
    kind: str
    status: JobStatus = JobStatus.running
    started_at: datetime
    finished_at: datetime | None = None
    result: dict | None = None
    error: str | None = None


class Health(BaseModel):
    database: bool
    database_error: str | None = None
    dataset: bool
    models: list[int] = Field(description='горизонты обученных моделей')


class ModelSummary(BaseModel):
    horizon: int
    trained_at: datetime
    n_iter: int
    periods: dict[str, list[date]] = Field(description='первая и последняя неделя обучения, валидации и теста')
    metrics: Metrics = Field(description='модель и ориентиры на тесте: MAE и RMSE в кг, WAPE, bias, R²')


class ModelDetail(ModelSummary):
    features: list[str]
    wape_by_unit: Metrics


class ForecastRow(BaseModel):
    origin_week: date
    week: date
    horizon: int
    branch_id: int
    branch_code: str
    product_id: int
    sku: str
    name: str
    unit: str
    forecast: float = Field(description='прогноз продаж в единицах товара')
    forecast_kg: float


class ForecastPage(BaseModel):
    origin_week: date = Field(description='последняя известная неделя')
    total: int
    offset: int
    limit: int
    rows: list[ForecastRow]


class NetworkWeek(BaseModel):
    horizon: int
    week: date
    tonnes: float


class ForecastSummary(BaseModel):
    origin_week: date
    file: str
    rows: int
    weeks: list[NetworkWeek] = Field(description='прогноз по всей сети, тонн в неделю')
