import pytest
from unittest.mock import MagicMock

# Configure pytest-asyncio as the default async plugin
pytest_plugins = ['pytest_asyncio']

# Mark all async tests with asyncio by default
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as requiring asyncio"
    )

@pytest.fixture
def mock_env_vars():
    """Fixture to provide common environment variable mocks for Vertex AI + asyncpg stack"""
    return {
        'GOOGLE_CLOUD_PROJECT': 'test-project',
        'GOOGLE_CLOUD_REGION': 'us-central1',
        'LLM_CHOICE': 'gemini-2.0-flash',
        'EMBEDDING_MODEL_CHOICE': 'gemini-embedding-001',
        'EMBEDDING_DIMENSIONS': '768',
        'DATABASE_URL': 'postgresql://user:password@localhost:5432/testdb'
    }

@pytest.fixture
def mock_memory():
    """Fixture to provide a mock Memory instance"""
    memory = MagicMock()
    memory.from_config = MagicMock()
    return memory
