"""Подключение к базе данных учётной системы."""
import psycopg

from ..config import settings
from ..exceptions import StorageError


def connect(**kwargs):
    """Подключение к базе с параметрами из .env. Дополнительные аргументы передаются в psycopg.connect."""
    try:
        return psycopg.connect(
            host=settings.db.host,
            port=settings.db.port,
            user=settings.db.user,
            password=settings.db.password.get_secret_value(),
            dbname=settings.db.name,
            **kwargs,
        )
    except psycopg.OperationalError as e:
        raise StorageError(
            f'Не удалось подключиться к {settings.db.name} на {settings.db.host}:{settings.db.port}: {e}'
        ) from e
