import pytest
import os

# Ensure a fake API key is set before main.py is imported
os.environ.setdefault("GEMINI_API_KEY", "test-fake-key-do-not-use")

import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock

from main import app, rate_limits


# ---------------------------------------------------------------------------
# Shared fake Gemini response
# ---------------------------------------------------------------------------
def _make_fake_gemini_response(text: str = "This is a test reply from Learnr."):
    mock_response = MagicMock()
    mock_response.text = text
    return mock_response


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Clear the in-memory rate limit store before each test."""
    rate_limits.clear()
    yield
    rate_limits.clear()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
