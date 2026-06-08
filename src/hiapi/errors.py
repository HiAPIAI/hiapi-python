"""Exception hierarchy for the HiAPI SDK.

    HiAPIError                     base for everything raised by this SDK
    ├── APIError                   the server returned a non-2xx HTTP response
    │   ├── AuthenticationError    401 — missing / invalid API key
    │   ├── NotFoundError          404 — task does not exist or not yours
    │   ├── ServiceUnavailableError 503 — platform temporarily unavailable
    │   ├── InvalidRequestError    error_code=INVALID_REQUEST
    │   ├── ModelUnavailableError  error_code=MODEL_UNAVAILABLE
    │   ├── TaskFailedError        error_code=TASK_FAILED (synchronous rejection)
    │   ├── TaskTimeoutError       error_code=TASK_TIMEOUT
    │   └── StorageUnavailableError error_code=STORAGE_UNAVAILABLE
    ├── APIConnectionError         network failure / DNS / connection reset
    ├── TaskFailed                 a polled task reached terminal status=fail
    ├── PollTimeout                run()/wait() exceeded the client-side timeout
    └── WebhookVerificationError   callback signature / timestamp check failed
"""

from __future__ import annotations

from typing import Optional


class HiAPIError(Exception):
    """Base class for every error raised by the SDK."""


class APIError(HiAPIError):
    """The server returned a non-2xx response.

    Attributes:
        status: HTTP status code.
        error_code: Business error code from the response envelope, if any.
        message: Human-readable message from the response, if any.
        body: Raw decoded response body (best-effort).
    """

    def __init__(
        self,
        message: str,
        *,
        status: int,
        error_code: Optional[str] = None,
        body: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.error_code = error_code
        self.message = message
        self.body = body


class AuthenticationError(APIError):
    """401 — the API key is missing or invalid."""


class NotFoundError(APIError):
    """404 — the task does not exist or does not belong to this account."""


class ServiceUnavailableError(APIError):
    """503 — the platform is temporarily unavailable; retry with backoff."""


class InvalidRequestError(APIError):
    """error_code=INVALID_REQUEST — fix the request; do not retry as-is."""


class ModelUnavailableError(APIError):
    """error_code=MODEL_UNAVAILABLE — retry shortly or switch models."""


class TaskFailedError(APIError):
    """error_code=TASK_FAILED on a synchronous response."""


class TaskTimeoutError(APIError):
    """error_code=TASK_TIMEOUT — the upstream task timed out; retryable."""


class StorageUnavailableError(APIError):
    """error_code=STORAGE_UNAVAILABLE — output storage error; retryable."""


class APIConnectionError(HiAPIError):
    """A network-level failure prevented the request from completing."""


class TaskFailed(HiAPIError):
    """A task being polled reached the terminal ``fail`` status.

    Attributes:
        task: The full :class:`~hiapi.models.Task` in its failed state.
        code: The task ``error.code`` if present.
    """

    def __init__(self, task: object) -> None:
        # ``task`` is a hiapi.models.Task; typed loosely to avoid an import cycle.
        err = getattr(task, "error", None)
        code = getattr(err, "code", None)
        message = getattr(err, "message", None) or "task failed"
        super().__init__(f"task {getattr(task, 'task_id', '?')} failed: {message}")
        self.task = task
        self.code = code
        self.message = message


class PollTimeout(HiAPIError):
    """``run()`` / ``wait()`` gave up before the task reached a terminal state.

    Attributes:
        task_id: The task that was being polled.
        timeout: The client-side timeout (seconds) that was exceeded.
    """

    def __init__(self, task_id: str, timeout: float) -> None:
        super().__init__(
            f"task {task_id} did not finish within {timeout:g}s; "
            f"it may still complete — poll tasks.retrieve({task_id!r}) later"
        )
        self.task_id = task_id
        self.timeout = timeout


class WebhookVerificationError(HiAPIError):
    """A callback could not be verified (bad signature or stale timestamp)."""


# Maps the API ``error_code`` enum onto the matching exception class.
ERROR_CODE_TO_CLASS = {
    "INVALID_REQUEST": InvalidRequestError,
    "MODEL_UNAVAILABLE": ModelUnavailableError,
    "TASK_FAILED": TaskFailedError,
    "TASK_TIMEOUT": TaskTimeoutError,
    "STORAGE_UNAVAILABLE": StorageUnavailableError,
}

# Falls back to a status-based class when no (recognized) error_code is present.
STATUS_TO_CLASS = {
    400: InvalidRequestError,
    401: AuthenticationError,
    404: NotFoundError,
    503: ServiceUnavailableError,
}
