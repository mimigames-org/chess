import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("MIMI_SECRET", "dev-mimi-secret")
os.environ.setdefault("CORE_URL", "http://core:8000")
os.environ.setdefault("SELF_BACKEND_URL", "http://chess:8001")
os.environ.setdefault("SELF_FRONTEND_URL", "http://chess:8001/ui")
os.environ.setdefault("SELF_NAME", "Шахматы")
os.environ.setdefault("PORT", "8001")


@pytest.fixture
async def chess_client():
    from main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
