"""The :class:`HiAPI` client — the entry point to the SDK."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from ._transport import Transport
from .errors import HiAPIError
from .resources import Tasks
from .webhooks import Webhooks

DEFAULT_BASE_URL = "https://api.hiapi.ai/v1"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 2


class HiAPI:
    """Client for the HiAPI unified async task API.

    Args:
        api_key: Account API key (``sk-...``). Falls back to the ``HIAPI_API_KEY``
            environment variable.
        base_url: API base URL, including the ``/v1`` prefix.
        timeout: Per-request socket timeout in seconds.
        max_retries: Retries for 429/503 and network errors (exponential backoff).
        webhook_secret: Default signing key for ``client.webhooks.verify``;
            falls back to the ``HIAPI_WEBHOOK_SECRET`` environment variable.

    Example::

        from hiapi import HiAPI

        client = HiAPI(api_key="sk-...")
        task = client.tasks.run(
            model="seedance-2-0",
            input={"prompt": "a cyan glass data center", "resolution": "1080p"},
            on_update=lambda t: print(t.status),
        )
        print(task.output[0].url)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        webhook_secret: Optional[str] = None,
    ) -> None:
        key = api_key or os.environ.get("HIAPI_API_KEY")
        if not key:
            raise HiAPIError(
                "missing API key: pass api_key=... or set the HIAPI_API_KEY "
                "environment variable"
            )
        self.api_key = key
        self.base_url = base_url
        self._transport = Transport(key, base_url, timeout, max_retries)

        self.tasks = Tasks(self)
        self.webhooks = Webhooks(
            self, webhook_secret or os.environ.get("HIAPI_WEBHOOK_SECRET")
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        return self._transport.request(
            method, path, body=body, params=params, extra_headers=extra_headers
        )

    def _request_with_headers(
        self,
        method: str,
        path: str,
        *,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        return self._transport.request_with_headers(
            method, path, body=body, params=params, extra_headers=extra_headers
        )
