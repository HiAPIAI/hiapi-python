import pytest
from _server import StubServer

from hiapi import HiAPI


@pytest.fixture
def server():
    s = StubServer()
    try:
        yield s
    finally:
        s.stop()


@pytest.fixture
def client(server):
    return HiAPI(
        api_key="sk-test",
        base_url=server.base_url,
        timeout=5.0,
        max_retries=1,
    )
