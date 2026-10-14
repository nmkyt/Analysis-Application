import pytest

from tests.data import make_data


@pytest.fixture
def demand_data():
    return make_data()
