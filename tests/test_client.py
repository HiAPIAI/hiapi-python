from urllib.error import URLError

import pytest

from hiapi import APIConnectionError, HiAPI, HiAPIError
from hiapi._transport import Transport


class _FakeOpener:
    """An opener whose every request fails at the network level."""

    def __init__(self, exc, calls):
        self.exc = exc
        self.calls = calls

    def open(self, req, timeout=None):
        self.calls.append(req.get_method())
        raise self.exc


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("HIAPI_API_KEY", "sk-from-env")
    client = HiAPI()
    assert client.api_key == "sk-from-env"


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("HIAPI_API_KEY", raising=False)
    with pytest.raises(HiAPIError):
        HiAPI()


def test_base_url_trailing_slash_normalized():
    t = Transport("sk", "https://api.hiapi.ai/v1/", timeout=5, max_retries=0)
    assert t._build_url("/tasks", None) == "https://api.hiapi.ai/v1/tasks"


def test_base_url_without_v1_gets_prefixed():
    t = Transport("sk", "https://api.hiapi.ai", timeout=5, max_retries=0)
    assert t._build_url("/tasks", None) == "https://api.hiapi.ai/v1/tasks"


def test_build_url_skips_none_params():
    t = Transport("sk", "https://api.hiapi.ai/v1", timeout=5, max_retries=0)
    url = t._build_url("/tasks", {"page": 1, "size": None})
    assert url == "https://api.hiapi.ai/v1/tasks?page=1"


def test_retry_delay_honours_retry_after():
    t = Transport("sk", "https://x/v1", timeout=5, max_retries=2)

    class Headers:
        def get(self, name):
            return "2" if name == "Retry-After" else None

    assert t._retry_delay(0, Headers()) == 2.0


def test_retry_delay_exponential_backoff():
    t = Transport("sk", "https://x/v1", timeout=5, max_retries=3)
    assert t._retry_delay(0, None) == 0.5
    assert t._retry_delay(1, None) == 1.0
    assert t._retry_delay(2, None) == 2.0


def test_retry_delay_clamps_negative_retry_after():
    t = Transport("sk", "https://x/v1", timeout=5, max_retries=2)

    class Headers:
        def get(self, name):
            return "-5" if name == "Retry-After" else None

    # Must never return a negative delay (time.sleep would raise).
    assert t._retry_delay(0, Headers()) == 0.0


def test_post_not_retried_on_network_error():
    # A non-idempotent POST must not be retried — it might have created a task.
    calls = []
    t = Transport(
        "sk", "https://x/v1", timeout=1, max_retries=3,
        opener=_FakeOpener(URLError("boom"), calls),
    )
    with pytest.raises(APIConnectionError):
        t.request("POST", "/tasks", body={"model": "m", "input": {}})
    assert calls == ["POST"]  # one attempt, no retries


def test_get_retried_on_network_error():
    calls = []
    t = Transport(
        "sk", "https://x/v1", timeout=1, max_retries=2,
        opener=_FakeOpener(URLError("boom"), calls),
    )
    with pytest.raises(APIConnectionError):
        t.request("GET", "/tasks")
    assert len(calls) == 3  # initial + 2 retries


def test_socket_timeout_wrapped_as_connection_error():
    # urllib raises a bare TimeoutError on read timeout (not URLError); it must
    # still surface as APIConnectionError, not leak the stdlib exception.
    calls = []
    t = Transport(
        "sk", "https://x/v1", timeout=1, max_retries=0,
        opener=_FakeOpener(TimeoutError("slow"), calls),
    )
    with pytest.raises(APIConnectionError):
        t.request("GET", "/tasks")
