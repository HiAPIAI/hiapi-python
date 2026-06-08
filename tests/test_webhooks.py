import hashlib
import hmac
import json
import time

import pytest

from hiapi import HiAPI, WebhookVerificationError, verify_webhook

SECRET = "whsec_test_key"


def sign(body: bytes, ts: str, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()


def make_body() -> bytes:
    # Intentionally unusual spacing so re-serialization would change the bytes.
    return b'{"taskId":"tk-1",  "model":"m", "status":"success",' \
           b'"output":[{"url":"https://cdn/x.mp4","type":"video","expireAt":1}]}'


def test_verify_ok_returns_task():
    body = make_body()
    ts = str(int(time.time()))
    task = verify_webhook(body, signature=sign(body, ts), timestamp=ts, secret=SECRET)
    assert task.task_id == "tk-1"
    assert task.succeeded
    assert task.output[0].url == "https://cdn/x.mp4"


def test_verify_uses_raw_bytes_not_reserialized():
    # A signature computed over the raw bytes must still validate even though
    # json.dumps(json.loads(body)) would produce different bytes.
    body = make_body()
    assert json.dumps(json.loads(body)).encode() != body
    ts = str(int(time.time()))
    verify_webhook(body, signature=sign(body, ts), timestamp=ts, secret=SECRET)


def test_bad_signature_rejected():
    body = make_body()
    ts = str(int(time.time()))
    with pytest.raises(WebhookVerificationError):
        verify_webhook(body, signature="deadbeef", timestamp=ts, secret=SECRET)


def test_tampered_body_rejected():
    body = make_body()
    ts = str(int(time.time()))
    good = sign(body, ts)
    with pytest.raises(WebhookVerificationError):
        verify_webhook(body + b" ", signature=good, timestamp=ts, secret=SECRET)


def test_stale_timestamp_rejected():
    body = make_body()
    ts = str(int(time.time()) - 10_000)
    with pytest.raises(WebhookVerificationError):
        verify_webhook(body, signature=sign(body, ts), timestamp=ts, secret=SECRET)


def test_missing_headers_rejected():
    body = make_body()
    with pytest.raises(WebhookVerificationError):
        verify_webhook(body, signature="", timestamp="", secret=SECRET)


def test_wrong_secret_rejected():
    body = make_body()
    ts = str(int(time.time()))
    with pytest.raises(WebhookVerificationError):
        verify_webhook(body, signature=sign(body, ts), timestamp=ts, secret="other")


def test_client_verify_reads_headers_case_insensitively():
    client = HiAPI(api_key="sk-test", webhook_secret=SECRET)
    body = make_body()
    ts = str(int(time.time()))
    headers = {"x-hiapi-timestamp": ts, "X-HiAPI-Signature": sign(body, ts)}
    task = client.webhooks.verify(body, headers)
    assert task.task_id == "tk-1"


def test_client_verify_without_secret_raises(monkeypatch):
    monkeypatch.delenv("HIAPI_WEBHOOK_SECRET", raising=False)
    client = HiAPI(api_key="sk-test")  # no webhook_secret
    with pytest.raises(WebhookVerificationError):
        client.webhooks.verify(b"{}", {"X-HiAPI-Signature": "x", "X-HiAPI-Timestamp": "1"})
