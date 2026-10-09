from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень проекта (папка над src)
BASE_DIR = Path(__file__).resolve().parent.parent

# Общие параметры чтения настроек: файл .env в корне проекта,
# переменные окружения имеют приоритет над значениями из файла
ENV_FILE_CONFIG = SettingsConfigDict(
    env_file=BASE_DIR / '.env',
    env_file_encoding='utf-8',
    extra='ignore',
)


class DatabaseSettings(BaseSettings):
    """Параметры подключения к MySQL (переменные DB_*)."""

    model_config = SettingsConfigDict(**ENV_FILE_CONFIG, env_prefix='DB_')

    host: str = 'localhost'
    port: int = Field(default=3306, ge=1, le=65535)
    user: str = 'user'
    password: SecretStr = SecretStr('')
    name: str = 'analysissystem'


class Settings(BaseSettings):
    """Настройки приложения."""

    model_config = ENV_FILE_CONFIG

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)

    # Папка для сохранения отчётов и графиков
    data_dir: Path = Path('data')

    @field_validator('data_dir')
    @classmethod
    def resolve_data_dir(cls, value: Path) -> Path:
        # Относительный путь считается от корня проекта, папка создаётся при необходимости
        if not value.is_absolute():
            value = BASE_DIR / value
        value.mkdir(parents=True, exist_ok=True)
        return value


settings = Settings()
