import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def chess_client():
    from main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
