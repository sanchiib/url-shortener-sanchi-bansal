import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shortener import create_app
from shortener.config import Config
from tests.fake_supabase import FakeSupabaseClient


def make_test_config(**overrides):
    class TestConfig(Config):
        pass

    # Dummy but well-formed values so create_app()/create_client() are
    # happy; the real client gets swapped out for a fake right after.
    TestConfig.SUPABASE_URL = "https://fake-project.supabase.co"
    TestConfig.SUPABASE_KEY = "fake-service-role-key"
    TestConfig.MASTER_API_KEY = "test-master-key"
    TestConfig.BASE_URL = "http://localhost:5000"
    TestConfig.RATE_LIMIT_MAX = 1000
    TestConfig.RATE_LIMIT_WINDOW = 60
    for key, value in overrides.items():
        setattr(TestConfig, key, value)
    return TestConfig


@pytest.fixture
def app():
    config = make_test_config()
    flask_app = create_app(config)
    flask_app.testing = True

    # Swap the real Supabase client for an in-memory fake so tests run
    # fully offline and never touch a real project.
    flask_app.supabase = FakeSupabaseClient()

    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()
