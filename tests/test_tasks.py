import json

import pytest
from _server import sequence

from hiapi import (
    AuthenticationError,
    InvalidRequestError,
    ModelUnavailableError,
    NotFoundError,
    PollTimeout,
    ServiceUnavailableError,
    TaskFailed,
)

OK_CREATE = (200, {"code": 200, "message": "success", "data": {"taskId": "tk-hiapi-abc123"}})


def detail(status, **extra):
    data = {"taskId": "tk-hiapi-abc123", "model": "seedance-2-0", "status": status}
    data.update(extra)
    return (200, {"code": 200, "message": "success", "data": data})


def test_create_returns_task_id(client, server):
    server.set_responder(lambda *a: OK_CREATE)
    created = client.tasks.create(model="seedance-2-0", input={"prompt": "hi"})
    assert created.task_id == "tk-hiapi-abc123"

    req = server.requests[-1]
    assert req["method"] == "POST"
    assert req["path"] == "/v1/tasks"
    assert req["headers"]["Authorization"] == "Bearer sk-test"
    body = json.loads(req["body"])
    assert body == {"model": "seedance-2-0", "input": {"prompt": "hi"}}


def test_create_with_callback_includes_callback(client, server):
    server.set_responder(lambda *a: OK_CREATE)
    client.tasks.create(
        model="m",
        input={"prompt": "x"},
        callback={"url": "https://e.com/cb", "when": "final"},
    )
    body = json.loads(server.requests[-1]["body"])
    assert body["callback"] == {"url": "https://e.com/cb", "when": "final"}


def test_retrieve_parses_camelcase(client, server):
    server.set_responder(
        lambda *a: detail(
            "success",
            createdAt=1777800499,
            updatedAt=1777800799,
            output=[{"url": "https://cdn/x.mp4", "type": "video", "expireAt": 1777887199}],
        )
    )
    task = client.tasks.retrieve("tk-hiapi-abc123")
    assert task.task_id == "tk-hiapi-abc123"
    assert task.status == "success"
    assert task.succeeded and task.is_terminal
    assert task.created_at == 1777800499
    assert task.output[0].url == "https://cdn/x.mp4"
    assert task.output[0].type == "video"
    assert task.output[0].expire_at == 1777887199


def test_list_parses_page(client, server):
    page = {
        "code": 200,
        "message": "success",
        "data": {
            "items": [{"taskId": "tk-1", "model": "m", "status": "success"}],
            "page": 2,
            "size": 20,
            "total": 41,
        },
    }
    server.set_responder(lambda *a: (200, page))
    result = client.tasks.list(page=2, size=20)
    assert result.total == 41 and result.page == 2
    assert result.items[0].task_id == "tk-1"
    assert "page=2" in server.requests[-1]["path"]
    assert "size=20" in server.requests[-1]["path"]


def test_wait_polls_until_success(client, server):
    server.set_responder(
        sequence([detail("queued"), detail("handling"), detail("success")])
    )
    seen = []
    task = client.tasks.wait(
        "tk-hiapi-abc123", poll_interval=0.01, on_update=lambda t: seen.append(t.status)
    )
    assert task.status == "success"
    assert seen == ["queued", "handling", "success"]  # one callback per change


def test_wait_raises_on_fail(client, server):
    server.set_responder(
        lambda *a: detail("fail", error={"code": "TASK_FAILED", "message": "boom"})
    )
    with pytest.raises(TaskFailed) as exc:
        client.tasks.wait("tk-hiapi-abc123", poll_interval=0.01)
    assert exc.value.code == "TASK_FAILED"
    assert exc.value.task.status == "fail"


def test_wait_times_out(client, server):
    server.set_responder(lambda *a: detail("handling"))
    with pytest.raises(PollTimeout) as exc:
        client.tasks.wait("tk-hiapi-abc123", poll_interval=0.01, timeout=0.05)
    assert exc.value.task_id == "tk-hiapi-abc123"


def test_wait_polls_once_more_when_interval_exceeds_timeout(client, server):
    # poll_interval (5s) > timeout (0.3s): must still poll near the deadline and
    # see the success rather than bailing out with PollTimeout immediately.
    server.set_responder(sequence([detail("queued"), detail("success")]))
    task = client.tasks.wait("tk-hiapi-abc123", poll_interval=5.0, timeout=0.3)
    assert task.succeeded


def test_wait_rejects_bad_arguments(client, server):
    server.set_responder(lambda *a: detail("handling"))
    with pytest.raises(ValueError):
        client.tasks.wait("tk-x", poll_interval=0)
    with pytest.raises(ValueError):
        client.tasks.wait("tk-x", timeout=-1)


def test_run_creates_then_waits(client, server):
    server.set_responder(
        sequence([OK_CREATE, detail("handling"), detail("success")])
    )
    task = client.tasks.run(
        model="seedance-2-0", input={"prompt": "hi"}, poll_interval=0.01
    )
    assert task.succeeded
    assert server.requests[0]["method"] == "POST"
    assert server.requests[1]["method"] == "GET"


@pytest.mark.parametrize(
    "status,error_code,expected",
    [
        (400, "INVALID_REQUEST", InvalidRequestError),
        (400, "MODEL_UNAVAILABLE", ModelUnavailableError),
        (400, None, InvalidRequestError),  # 400 without error_code falls back
        (401, None, AuthenticationError),
        (404, None, NotFoundError),
        (503, None, ServiceUnavailableError),
    ],
)
def test_error_mapping(client, server, status, error_code, expected):
    body = {"code": status, "message": "nope", "data": None}
    if error_code:
        body["error_code"] = error_code
    server.set_responder(lambda *a: (status, body))
    with pytest.raises(expected) as exc:
        client.tasks.retrieve("tk-x")
    assert exc.value.status == status
    if error_code:
        assert exc.value.error_code == error_code


def test_retries_on_503_then_succeeds(client, server):
    server.set_responder(
        sequence([(503, {"code": 503, "message": "busy", "data": None}), OK_CREATE])
    )
    created = client.tasks.create(model="m", input={"prompt": "x"})
    assert created.task_id == "tk-hiapi-abc123"
    assert len(server.requests) == 2  # one retry
