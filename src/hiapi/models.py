"""Typed data models for the unified async task API.

The wire format uses camelCase (``taskId``, ``expireAt``); these dataclasses
expose snake_case attributes and parse defensively — unknown fields are kept in
``raw`` so a server-side addition never breaks an older SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

TaskStatus = Literal["queued", "handling", "archiving", "success", "fail"]

# Terminal statuses a task can never leave once reached.
TERMINAL_STATUSES = frozenset({"success", "fail"})


@dataclass
class Output:
    """One generated artifact produced by a successful task."""

    url: str
    type: str
    expire_at: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Output:
        return cls(
            url=d.get("url", ""),
            type=d.get("type", ""),
            expire_at=d.get("expireAt"),
            raw=d,
        )


@dataclass
class TaskError:
    """The failure reason attached to a task in ``fail`` state."""

    code: Optional[str] = None
    message: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> TaskError:
        return cls(code=d.get("code"), message=d.get("message"), raw=d)


@dataclass
class Task:
    """An async generation task and (when finished) its output."""

    task_id: str
    model: str
    # Kept as ``str`` (not the ``TaskStatus`` literal above) on purpose: a status
    # the server adds later must still parse rather than break an older SDK.
    status: str
    created_at: Optional[int] = None
    completed_at: Optional[int] = None
    storage: Optional[str] = None
    output: List[Output] = field(default_factory=list)
    error: Optional[TaskError] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def succeeded(self) -> bool:
        return self.status == "success"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Task:
        output = [
            Output.from_dict(o) for o in (d.get("output") or []) if isinstance(o, dict)
        ]
        err = d.get("error")
        # The API sends `completed: 0` (not omitted) while a task is non-terminal;
        # normalize that sentinel to None so callers don't read it as epoch 0.
        completed = d.get("completed")
        return cls(
            task_id=d.get("taskId", ""),
            model=d.get("model", ""),
            status=d.get("status", ""),
            created_at=d.get("created"),
            completed_at=completed or None,
            storage=d.get("storage"),
            output=output,
            error=TaskError.from_dict(err) if isinstance(err, dict) else None,
            raw=d,
        )


@dataclass
class CreatedTask:
    """The thin response of ``POST /v1/tasks`` — just the new task id."""

    task_id: str
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> CreatedTask:
        return cls(task_id=d.get("taskId", ""), raw=d)


@dataclass
class TaskPage:
    """One page of ``GET /v1/tasks`` (newest first)."""

    items: List[Task] = field(default_factory=list)
    page: Optional[int] = None
    size: Optional[int] = None
    total: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> TaskPage:
        raw_items = None
        # The API returns the page array under "tasks"; accept common alternates
        # too so a paginated list never silently parses to empty. The full
        # payload is kept in raw.
        for key in ("tasks", "items", "list", "data", "records"):
            value = d.get(key)
            if isinstance(value, list):
                raw_items = value
                break
        items = [Task.from_dict(t) for t in (raw_items or []) if isinstance(t, dict)]
        return cls(
            items=items,
            page=d.get("page"),
            size=d.get("size"),
            total=d.get("total"),
            raw=d,
        )
