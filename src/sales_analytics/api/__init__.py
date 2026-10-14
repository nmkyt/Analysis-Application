"""REST API: единая точка входа для обучения моделей, прогноза и выгрузки датасета."""
from .app import create_app

app = create_app()

__all__ = ['app', 'create_app']
