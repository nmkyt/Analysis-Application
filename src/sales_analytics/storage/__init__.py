"""Хранилище: схема учётной системы в PostgreSQL и подключение к ней."""
from .postgres import connect

__all__ = ['connect']
