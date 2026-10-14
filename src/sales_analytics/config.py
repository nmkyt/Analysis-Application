from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень репозитория: src/sales_analytics/config.py -> ../..
BASE_DIR = Path(__file__).resolve().parents[2]

# Общие параметры чтения настроек: файл .env в корне проекта,
# переменные окружения имеют приоритет над значениями из файла
ENV_FILE_CONFIG = SettingsConfigDict(
    env_file=BASE_DIR / '.env',
    env_file_encoding='utf-8',
    extra='ignore',
)


class DatabaseSettings(BaseSettings):
    """Параметры подключения к PostgreSQL (переменные DB_*)."""

    model_config = SettingsConfigDict(**ENV_FILE_CONFIG, env_prefix='DB_')

    host: str = 'localhost'
    port: int = Field(default=5432, ge=1, le=65535)
    user: str = 'metal_market'
    password: SecretStr = SecretStr('')
    name: str = 'metal_market'


class Settings(BaseSettings):
    """Настройки приложения."""

    model_config = ENV_FILE_CONFIG

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)

    # Датасет в CSV: выгрузка таблиц учётной системы
    dataset_dir: Path = Path('data')
    # Результаты: модели, прогнозы, выборки для обучения
    output_dir: Path = Path('output')

    # Адрес REST API: по умолчанию доступен только с этого компьютера
    api_host: str = '127.0.0.1'
    api_port: int = Field(default=8000, ge=1, le=65535)

    @field_validator('dataset_dir', 'output_dir')
    @classmethod
    def resolve_dir(cls, value: Path) -> Path:
        # Относительный путь считается от корня проекта
        return value if value.is_absolute() else BASE_DIR / value

    @property
    def models_dir(self) -> Path:
        return self.output_dir / 'models'

    @property
    def forecasts_dir(self) -> Path:
        return self.output_dir / 'forecasts'

    @property
    def training_dir(self) -> Path:
        return self.output_dir / 'training'


settings = Settings()
