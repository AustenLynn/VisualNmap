import pytest

from visualnmap.catalog import load_catalog


@pytest.fixture(scope="session")
def catalog():
    return load_catalog()
