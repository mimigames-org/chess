import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("MIMI_SECRET", "dev-mimi-secret")


@pytest.fixture
async def chess_client():
    from main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
