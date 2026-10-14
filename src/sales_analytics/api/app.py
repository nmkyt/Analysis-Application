"""Приложение FastAPI: эндпоинты, фоновые задачи и ошибки пакета как HTTP-ответы."""
from importlib.metadata import version

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from ..exceptions import DataError, ModelError, StorageError
from .jobs import JobRegistry
from .routes import router

DESCRIPTION = """
Прогноз спроса сети металлобаз по позициям, базам и неделям.

Обычный порядок: **POST /models/train** (в фоне, статус - GET /jobs/{id}) → **POST /forecasts** →
**GET /forecasts/latest**. Данные читаются из датасета в CSV (`source: dataset`) или из базы (`source: db`).
"""

# Ошибки пакета: база недоступна - 503, нет данных или модели - 409
ERROR_STATUS = {
    StorageError: status.HTTP_503_SERVICE_UNAVAILABLE,
    DataError: status.HTTP_409_CONFLICT,
    ModelError: status.HTTP_409_CONFLICT,
}


def create_app() -> FastAPI:
    app = FastAPI(title='Sales Analytics API', version=version('sales-analytics'), description=DESCRIPTION)
    app.state.jobs = JobRegistry()
    app.include_router(router)

    for error, code in ERROR_STATUS.items():
        app.add_exception_handler(error, _handler(code))

    @app.get('/', include_in_schema=False)
    def root():
        return RedirectResponse('/docs')

    return app


def _handler(code):
    async def handle(request: Request, error: Exception):
        return JSONResponse(status_code=code, content={'detail': str(error)})
    return handle
