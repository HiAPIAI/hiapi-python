"""The ``client.tasks`` resource — the unified async task API (/v1/tasks)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from ..errors import PollTimeout, TaskFailed
from ..models import CreatedTask, Task, TaskPage

if TYPE_CHECKING:
    from ..client import HiAPI

# Called once per status change while waiting; receives the latest Task.
OnUpdate = Callable[[Task], None]

DEFAULT_POLL_INTERVAL = 3.0
DEFAULT_TIMEOUT = 600.0


class Tasks:
    def __init__(self, client: HiAPI) -> None:
        self._client = client

    def create(
        self,
        *,
        model: str,
        input: Dict[str, Any],
        callback: Optional[Dict[str, Any]] = None,
    ) -> CreatedTask:
        """Submit a task and return immediately with its ``task_id``.

        ``input`` holds the model's business parameters (fields vary per model).
        Do not put callback/webhook fields inside ``input`` — pass ``callback``
        (``{"url": ..., "when": "final"}``) separately or the request is rejected.
        """
        body: Dict[str, Any] = {"model": model, "input": input}
        if callback is not None:
            body["callback"] = callback
        env = self._client._request("POST", "/tasks", body=body)
        return CreatedTask.from_dict(_data(env))

    def retrieve(self, task_id: str) -> Task:
        """Fetch a task's current status and (when ``success``) its output."""
        env = self._client._request("GET", "/tasks/" + _encode(task_id))
        return Task.from_dict(_data(env))

    def list(self, *, page: int = 1, size: int = 20) -> TaskPage:
        """List your tasks, newest first (paginated)."""
        env = self._client._request("GET", "/tasks", params={"page": page, "size": size})
        data = env.get("data")
        if isinstance(data, list):
            data = {"items": data, "page": page, "size": size}
        elif not isinstance(data, dict):
            data = {}
        return TaskPage.from_dict(data)

    def wait(
        self,
        task_id: str,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = DEFAULT_TIMEOUT,
        on_update: Optional[OnUpdate] = None,
    ) -> Task:
        """Poll ``task_id`` until it reaches a terminal state.

        Returns the :class:`Task` on ``success``. Raises :class:`TaskFailed` on
        ``fail`` and :class:`PollTimeout` only once ``timeout`` seconds have
        actually elapsed.
        """
        if poll_interval <= 0:
            raise ValueError("poll_interval must be > 0")
        if timeout < 0:
            raise ValueError("timeout must be >= 0")
        deadline = time.monotonic() + timeout
        last_status: Optional[str] = None
        while True:
            task = self.retrieve(task_id)
            if on_update is not None and task.status != last_status:
                last_status = task.status
                on_update(task)
            if task.status == "success":
                return task
            if task.status == "fail":
                raise TaskFailed(task)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PollTimeout(task_id, timeout)
            # Sleep the smaller of the poll interval and the time left, so the
            # last poll lands right at the deadline rather than before it.
            time.sleep(min(poll_interval, remaining))

    def run(
        self,
        *,
        model: str,
        input: Dict[str, Any],
        callback: Optional[Dict[str, Any]] = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = DEFAULT_TIMEOUT,
        on_update: Optional[OnUpdate] = None,
    ) -> Task:
        """Create a task and block until it finishes — the one-call workflow.

        Equivalent to :meth:`create` followed by :meth:`wait`. ``callback`` is
        optional and independent of polling; set it if you also want a webhook.
        """
        created = self.create(model=model, input=input, callback=callback)
        return self.wait(
            created.task_id,
            poll_interval=poll_interval,
            timeout=timeout,
            on_update=on_update,
        )


def _data(env: Dict[str, Any]) -> Dict[str, Any]:
    data = env.get("data")
    return data if isinstance(data, dict) else {}


def _encode(task_id: str) -> str:
    from urllib.parse import quote

    return quote(str(task_id), safe="")
