"""Исключения пакета."""


class SalesAnalyticsError(Exception):
    """Базовое исключение пакета."""


class StorageError(SalesAnalyticsError):
    """Ошибка при работе с базой данных: подключение, создание схемы, загрузка."""


class DataError(SalesAnalyticsError):
    """Данные не соответствуют ожидаемой структуре."""


class ModelError(SalesAnalyticsError):
    """Ошибка при обучении, сохранении или загрузке модели."""
