"""Zero-dependency HTTP transport built on the standard library.

Handles JSON request/response framing, authentication, retries with
exponential backoff (honouring ``Retry-After``), and mapping non-2xx
responses onto the typed exception hierarchy in :mod:`hiapi.errors`.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

from ._version import __version__
from .errors import (
    ERROR_CODE_TO_CLASS,
    STATUS_TO_CLASS,
    APIConnectionError,
    APIError,
)

# Statuses worth retrying: rate limiting and transient platform unavailability.
# These mean the server rejected the request *before* processing, so retrying is
# safe even for a non-idempotent POST (no duplicate task is created).
RETRY_STATUSES = frozenset({429, 503})
# Methods safe to retry after a network error, where the outcome is unknown.
# A POST /tasks must NOT be retried on a network error — it might have created a
# task the SDK never saw the response for, double-charging the account. The
# exception: a request carrying an Idempotency-Key header IS safe to retry (the
# server collapses duplicates into the first task).
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "PUT", "DELETE"})
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
# error_code of the retryable 409 the server returns while the first request
# with the same Idempotency-Key is still in flight (honours Retry-After).
IDEMPOTENCY_PROCESSING_CODE = "IDEMPOTENCY_KEY_PROCESSING"
_MAX_BACKOFF = 8.0
_MAX_RETRY_AFTER = 60.0


class Transport:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: float,
        max_retries: int,
        *,
        opener: Optional[urllib.request.OpenerDirector] = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = _normalize_base_url(base_url)
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        # A dedicated opener avoids depending on global urllib state.
        self._opener = opener or urllib.request.build_opener()

    # -- public ---------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Perform a request and return the parsed JSON envelope (a dict).

        Raises an :class:`~hiapi.errors.APIError` subclass on non-2xx responses
        and :class:`~hiapi.errors.APIConnectionError` on network failure.
        """
        env, _ = self.request_with_headers(
            method, path, body=body, params=params, extra_headers=extra_headers
        )
        return env

    def request_with_headers(
        self,
        method: str,
        path: str,
        *,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """Like :meth:`request`, but also returns the response headers.

        The header dict is lower-cased so lookups are case-insensitive.
        """
        url = self._build_url(path, params)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": f"hiapi-python/{__version__}",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)
        # An Idempotency-Key makes the POST safe to retry: the server collapses
        # duplicates of the same key+body into the first task.
        has_idempotency_key = bool(extra_headers and extra_headers.get(IDEMPOTENCY_KEY_HEADER))

        attempt = 0
        while True:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with self._opener.open(req, timeout=self.timeout) as resp:
                    return (
                        _decode_json(resp.read(), resp.status),
                        {k.lower(): v for k, v in resp.headers.items()},
                    )
            except urllib.error.HTTPError as exc:
                raw = _safe_read(exc)
                status = exc.code
                if status in RETRY_STATUSES and attempt < self.max_retries:
                    time.sleep(self._retry_delay(attempt, exc.headers))
                    attempt += 1
                    continue
                err = _error_from_response(status, raw)
                # A 409 IDEMPOTENCY_KEY_PROCESSING means the first request with
                # this key is still in flight; honour Retry-After and retry —
                # the next attempt hits the replay path and returns the task.
                if (
                    has_idempotency_key
                    and status == 409
                    and err.error_code == IDEMPOTENCY_PROCESSING_CODE
                    and attempt < self.max_retries
                ):
                    time.sleep(self._retry_delay(attempt, exc.headers))
                    attempt += 1
                    continue
                # The HTTPError itself is noise; the typed APIError carries detail.
                raise err from None
            except OSError as exc:
                # OSError covers URLError, socket.timeout and TimeoutError — any
                # of which urllib may raise on connect/read timeouts or TLS/reset.
                # Only retry network failures for idempotent methods (or a POST
                # carrying an Idempotency-Key); a blindly retried POST could
                # silently create a second task.
                if (
                    method.upper() in IDEMPOTENT_METHODS or has_idempotency_key
                ) and attempt < self.max_retries:
                    time.sleep(self._retry_delay(attempt, None))
                    attempt += 1
                    continue
                reason = getattr(exc, "reason", exc)
                raise APIConnectionError(f"request to {url} failed: {reason}") from exc

    # -- internals ------------------------------------------------------------

    def _build_url(self, path: str, params: Optional[Dict[str, Any]]) -> str:
        if not path.startswith("/"):
            path = "/" + path
        url = self._base_url + path
        if params:
            query = {k: v for k, v in params.items() if v is not None}
            if query:
                url = url + "?" + urllib.parse.urlencode(query)
        return url

    def _retry_delay(self, attempt: int, headers: Any) -> float:
        if headers is not None:
            retry_after = headers.get("Retry-After")
            if retry_after:
                try:
                    # Clamp to [0, max]: a negative Retry-After would make
                    # time.sleep() raise and break the retry loop.
                    return max(0.0, min(float(retry_after), _MAX_RETRY_AFTER))
                except (TypeError, ValueError):
                    pass  # HTTP-date form: fall back to backoff
        return float(min(0.5 * (2 ** attempt), _MAX_BACKOFF))


def _normalize_base_url(base_url: str) -> str:
    """Strip trailing slashes and ensure the ``/v1`` version prefix is present.

    Accepts both ``https://api.hiapi.ai`` and ``https://api.hiapi.ai/v1`` so a
    missing ``/v1`` doesn't silently send requests to the wrong path.
    """
    base = base_url.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    return base


def _safe_read(exc: urllib.error.HTTPError) -> bytes:
    try:
        return exc.read()
    except Exception:  # pragma: no cover - defensive
        return b""


def _decode_json(raw: bytes, status: int) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise APIError(
            f"could not decode response body as JSON: {exc}",
            status=status,
            body=raw.decode("utf-8", "replace"),
        ) from exc
    if not isinstance(parsed, dict):
        raise APIError(
            "expected a JSON object response",
            status=status,
            body=raw.decode("utf-8", "replace"),
        )
    return parsed


def _error_from_response(status: int, raw: bytes) -> APIError:
    error_code: Optional[str] = None
    message: Optional[str] = None
    body_text = raw.decode("utf-8", "replace") if raw else None
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(parsed, dict):
            error_code = parsed.get("error_code")
            message = parsed.get("message")
    except (ValueError, UnicodeDecodeError):
        pass

    cls = ERROR_CODE_TO_CLASS.get(error_code or "") or STATUS_TO_CLASS.get(status, APIError)
    return cls(
        message or f"HTTP {status}",
        status=status,
        error_code=error_code,
        body=body_text,
    )
