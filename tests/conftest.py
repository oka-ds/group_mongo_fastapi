import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from olist.config import get_settings
from olist.database import get_database
from olist.main import app

TEST_DB_NAME = "olist_test"


@pytest.fixture(scope="session")
def mongo_client():
    client = MongoClient(get_settings().mongo_uri)
    yield client
    client.drop_database(TEST_DB_NAME)
    client.close()


@pytest.fixture()
def db(mongo_client):
    database = mongo_client[TEST_DB_NAME]
    for name in database.list_collection_names():
        database[name].drop()
    yield database


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_database] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
