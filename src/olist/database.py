from functools import lru_cache

from pymongo import MongoClient
from pymongo.database import Database

from olist.config import get_settings


@lru_cache
def _client() -> MongoClient:
    return MongoClient(get_settings().mongo_uri)


def get_database() -> Database:
    """FastAPI dependency returning the configured MongoDB database."""
    return _client()[get_settings().mongo_db]
