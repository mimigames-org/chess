import pytest
import redis.asyncio as aioredis
from testcontainers.redis import RedisContainer

import redis_client as rc_module


@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7-alpine") as rc:
        yield rc


@pytest.fixture
async def redis(redis_container):
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    client = aioredis.from_url(f"redis://{host}:{port}/0", decode_responses=True)
    rc_module._redis = client
    yield client
    await client.flushall()
    await client.aclose()
    rc_module._redis = None
