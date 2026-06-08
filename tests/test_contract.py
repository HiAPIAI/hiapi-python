"""Pin the SDK's parsing to the documented /v1/tasks contract.

The payloads below are copied verbatim from the HiAPI async-api docs and
openapi.json. If the contract changes, these break first.
"""

from hiapi.models import CreatedTask, Task

CREATE_SUCCESS = {
    "code": 200,
    "message": "success",
    "data": {"taskId": "tk-hiapi-01HZTQ8BX2N3GM3YFK4Z9D7VQR"},
}

DETAIL_SUCCESS = {
    "code": 200,
    "message": "success",
    "data": {
        "taskId": "tk-hiapi-abc123",
        "model": "seedance-2-0",
        "status": "success",
        "createdAt": 1777800499,
        "updatedAt": 1777800799,
        "output": [
            {"url": "https://cdn.hiapi.ai/tasks/tk-hiapi-abc123/0.mp4",
             "type": "video", "expireAt": 1777887199}
        ],
    },
}

DETAIL_FAIL = {
    "code": 200,
    "message": "success",
    "data": {
        "taskId": "tk-hiapi-abc123",
        "model": "seedance-2-0",
        "status": "fail",
        "error": {"code": "TASK_FAILED", "message": "upstream rejected the prompt"},
    },
}


def test_created_task_contract():
    created = CreatedTask.from_dict(CREATE_SUCCESS["data"])
    assert created.task_id == "tk-hiapi-01HZTQ8BX2N3GM3YFK4Z9D7VQR"
    assert len(created.task_id) == 35  # tk-hiapi- + 26 chars


def test_detail_success_contract():
    task = Task.from_dict(DETAIL_SUCCESS["data"])
    assert task.status == "success"
    assert task.is_terminal and task.succeeded
    assert task.model == "seedance-2-0"
    assert task.created_at == 1777800499
    assert task.updated_at == 1777800799
    out = task.output[0]
    assert out.type == "video"
    assert out.url.endswith("0.mp4")
    assert out.expire_at == 1777887199


def test_detail_fail_contract():
    task = Task.from_dict(DETAIL_FAIL["data"])
    assert task.status == "fail" and task.is_terminal and not task.succeeded
    assert task.error is not None
    assert task.error.code == "TASK_FAILED"
    assert task.output == []


def test_all_documented_statuses_recognized():
    for status in ("queued", "handling", "archiving", "success", "fail"):
        task = Task.from_dict({"taskId": "t", "model": "m", "status": status})
        assert task.is_terminal == (status in ("success", "fail"))


def test_parsing_tolerates_malformed_output_items():
    # A non-dict slipped into output[] must not raise; it is skipped.
    task = Task.from_dict(
        {
            "taskId": "t",
            "model": "m",
            "status": "success",
            "output": [None, "oops", {"url": "https://cdn/x.png", "type": "image"}],
        }
    )
    assert len(task.output) == 1
    assert task.output[0].url == "https://cdn/x.png"
