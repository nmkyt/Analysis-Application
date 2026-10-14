"""REST API на маленьких данных: база не нужна, результаты пишутся во временную папку."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from sales_analytics.api import create_app, routes
from sales_analytics.api.jobs import JobConflict, JobRegistry
from sales_analytics.api.schemas import JobStatus
from sales_analytics.config import settings
from sales_analytics.exceptions import StorageError
from sales_analytics.forecasting import model as model_module
from sales_analytics.storage.export import TABLES
from tests.data import make_data


def database_unavailable(*args, **kwargs):
    raise StorageError('база недоступна')


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'output_dir', tmp_path / 'output')
    monkeypatch.setattr(settings, 'dataset_dir', tmp_path / 'data')
    # Данные датасета - маленькие искусственные, базы нет
    monkeypatch.setattr(routes, 'load_demand_data_csv', lambda: make_data(n_weeks=110))
    monkeypatch.setattr(routes, 'load_demand_data', database_unavailable)
    monkeypatch.setattr(routes, 'connect', database_unavailable)
    monkeypatch.setitem(model_module.MODEL_PARAMS, 'max_iter', 30)
    return TestClient(create_app())


@pytest.fixture
def trained_client(client):
    job = client.post('/models/train', json={'horizons': [1, 2]}).json()
    assert wait(client, job['id'])['status'] == 'done'
    return client


def wait(client, job_id, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f'/jobs/{job_id}').json()
        if job['status'] != 'running':
            return job
        time.sleep(0.1)
    raise TimeoutError(f'Задача {job_id} не завершилась за {timeout} с')


# ===== Сервис =====

def test_root_redirects_to_docs(client):
    response = client.get('/', follow_redirects=False)
    assert response.status_code == 307
    assert response.headers['location'] == '/docs'


def test_health_without_database_dataset_and_models(client):
    health = client.get('/health').json()
    assert health == {'database': False, 'database_error': 'база недоступна', 'dataset': False, 'models': []}


def test_health_sees_dataset(client):
    settings.dataset_dir.mkdir(parents=True)
    for table in TABLES:
        (settings.dataset_dir / f'{table}.csv.gz').touch()
    assert client.get('/health').json()['dataset'] is True


def test_unknown_job_returns_404(client):
    assert client.get('/jobs/unknown').status_code == 404


# ===== Модели и прогноз =====

def test_no_models_yet(client):
    assert client.get('/models').json() == []
    assert client.get('/models/1').status_code == 404


def test_forecast_before_training_returns_409(client):
    response = client.post('/forecasts', json={'horizons': [1]})
    assert response.status_code == 409
    assert 'не найдена' in response.json()['detail']


def test_latest_forecast_before_any_returns_404(client):
    assert client.get('/forecasts/latest').status_code == 404
    assert client.get('/forecasts/latest/summary').status_code == 404


@pytest.mark.parametrize('method, path, payload', [
    ('post', '/models/train', {'horizons': [0]}),
    ('post', '/models/train', {'horizons': [53]}),
    ('post', '/models/train', {'horizons': []}),
    ('post', '/forecasts', {'source': 'csv'}),
])
def test_invalid_requests_return_422(client, method, path, payload):
    assert getattr(client, method)(path, json=payload).status_code == 422


def test_invalid_query_returns_422(trained_client):
    trained_client.post('/forecasts', json={'horizons': [1]})
    assert trained_client.get('/forecasts/latest', params={'limit': 0}).status_code == 422
    assert trained_client.get('/forecasts/latest', params={'horizon': 99}).status_code == 422


def test_training_job_saves_models(client):
    response = client.post('/models/train', json={'horizons': [2, 1, 2]})
    assert response.status_code == 202
    assert response.json()['status'] == 'running'

    job = wait(client, response.json()['id'])
    assert job['status'] == 'done' and job['error'] is None
    assert job['result']['horizons'] == [1, 2]
    assert set(job['result']['metrics']['1']) == set(model_module.METHODS.values())

    models = client.get('/models').json()
    assert [m['horizon'] for m in models] == [1, 2]
    assert models[0]['metrics']['модель']['wape'] > 0
    detail = client.get('/models/2').json()
    assert detail['features'][0] == 'qty_lag2'
    assert set(detail['wape_by_unit']['модель']) == {'m', 'pcs'}


def test_forecast_and_filters(trained_client):
    summary = trained_client.post('/forecasts', json={'horizons': [1, 2]}).json()
    # Две базы × две позиции в ассортименте × два горизонта
    assert summary['rows'] == 8
    assert summary['file'] == f'forecast_{summary["origin_week"]}.csv'
    assert [w['horizon'] for w in summary['weeks']] == [1, 2]
    assert all(w['tonnes'] > 0 for w in summary['weeks'])
    assert trained_client.get('/forecasts/latest/summary').json() == summary

    page = trained_client.get('/forecasts/latest', params={'branch': 'A'}).json()
    assert page['total'] == 4 and {row['branch_code'] for row in page['rows']} == {'A'}

    page = trained_client.get('/forecasts/latest', params={'horizon': 2, 'limit': 1, 'offset': 1}).json()
    assert page['total'] == 4 and len(page['rows']) == 1 and page['offset'] == 1
    assert page['rows'][0]['horizon'] == 2

    page = trained_client.get('/forecasts/latest', params={'product_id': 2}).json()
    assert {row['product_id'] for row in page['rows']} == {2}
    assert page['origin_week'] == summary['origin_week']


def test_failed_job_reports_error(client):
    job = client.post('/models/train', json={'horizons': [1], 'source': 'db'}).json()
    job = wait(client, job['id'])
    assert job['status'] == 'failed'
    assert job['error'] == 'база недоступна'
    assert client.get('/jobs').json()[0]['id'] == job['id']


def test_forecast_from_unavailable_database_returns_503(trained_client):
    response = trained_client.post('/forecasts', json={'source': 'db'})
    assert response.status_code == 503
    assert response.json()['detail'] == 'база недоступна'


def test_export_job(client, monkeypatch):
    exported = []
    monkeypatch.setattr(routes, 'export_dataset', lambda directory: exported.append(directory))
    job = wait(client, client.post('/dataset/export').json()['id'])
    assert job['status'] == 'done'
    assert exported == [settings.dataset_dir]
    assert job['result']['tables'] == TABLES


# ===== Помощники =====

def test_one_job_of_each_kind_at_a_time():
    registry, release = JobRegistry(), threading.Event()
    first = registry.start('train', lambda: release.wait(5) and {})
    with pytest.raises(JobConflict):
        registry.start('train', dict)
    other = registry.start('export', dict)  # другой вид задачи не мешает
    release.set()
    for job in (first, other):
        deadline = time.monotonic() + 5
        while registry.get(job.id).status is JobStatus.running and time.monotonic() < deadline:
            time.sleep(0.01)
        assert registry.get(job.id).status is JobStatus.done
    registry.start('train', dict)  # после завершения можно снова


def test_clean_replaces_non_finite_numbers():
    assert routes._clean({'a': float('nan'), 'b': [1.0, float('inf')], 'c': 'x'}) == \
        {'a': None, 'b': [1.0, None], 'c': 'x'}
