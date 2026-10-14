from pathlib import Path

from sales_analytics.config import BASE_DIR, Settings


def test_relative_dirs_are_resolved_from_project_root():
    settings = Settings(dataset_dir='my_data', output_dir='my_output')
    assert settings.dataset_dir == BASE_DIR / 'my_data'
    assert settings.output_dir == BASE_DIR / 'my_output'


def test_absolute_dirs_are_kept(tmp_path):
    settings = Settings(output_dir=tmp_path)
    assert settings.output_dir == tmp_path


def test_result_dirs_are_inside_output_dir(tmp_path):
    settings = Settings(output_dir=tmp_path)
    assert settings.models_dir == tmp_path / 'models'
    assert settings.forecasts_dir == tmp_path / 'forecasts'
    assert settings.training_dir == tmp_path / 'training'


def test_base_dir_is_project_root():
    assert (BASE_DIR / 'pyproject.toml').exists()
    assert isinstance(BASE_DIR, Path)
