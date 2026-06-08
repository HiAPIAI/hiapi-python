"""HiAPI Python SDK — a zero-dependency client for the unified async task API.

Quick start::

    from hiapi import HiAPI

    client = HiAPI(api_key="sk-...")  # or set HIAPI_API_KEY
    task = client.tasks.run(
        model="seedance-2-0",
        input={"prompt": "...", "resolution": "1080p"},
    )
    print(task.output[0].url)
"""

from __future__ import annotations

from ._version import __version__
from .client import HiAPI
from .errors import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    HiAPIError,
    InvalidRequestError,
    ModelUnavailableError,
    NotFoundError,
    PollTimeout,
    ServiceUnavailableError,
    StorageUnavailableError,
    TaskFailed,
    TaskFailedError,
    TaskTimeoutError,
    WebhookVerificationError,
)
from .models import CreatedTask, Output, Task, TaskError, TaskPage
from .webhooks import verify_webhook

__all__ = [
    "__version__",
    "HiAPI",
    # models
    "Task",
    "Output",
    "TaskError",
    "CreatedTask",
    "TaskPage",
    # webhooks
    "verify_webhook",
    # errors
    "HiAPIError",
    "APIError",
    "APIConnectionError",
    "AuthenticationError",
    "NotFoundError",
    "ServiceUnavailableError",
    "InvalidRequestError",
    "ModelUnavailableError",
    "TaskFailedError",
    "TaskTimeoutError",
    "StorageUnavailableError",
    "TaskFailed",
    "PollTimeout",
    "WebhookVerificationError",
]
