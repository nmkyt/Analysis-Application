"""Исключения пакета."""


class SalesAnalyticsError(Exception):
    """Базовое исключение пакета."""


class StorageError(SalesAnalyticsError):
    """Ошибка при работе с базой данных: подключение, создание схемы, загрузка."""
