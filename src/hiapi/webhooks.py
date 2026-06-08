"""Verify HiAPI callback (webhook) signatures.

When a "Webhook signing key" is set in the HiAPI console, each terminal callback
carries two headers:

    X-HiAPI-Timestamp: Unix seconds (string)
    X-HiAPI-Signature: hex( HMAC_SHA256(secret, timestamp + "." + body) )

``verify_webhook`` recomputes the signature over the **raw request body** (never
the re-serialized JSON — re-encoding can change bytes and break the check),
guards against replay with a timestamp tolerance, and returns the parsed
:class:`~hiapi.models.Task`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import TYPE_CHECKING, Any, Mapping, Optional, Union

from .errors import WebhookVerificationError
from .models import Task

if TYPE_CHECKING:
    from .client import HiAPI

TIMESTAMP_HEADER = "X-HiAPI-Timestamp"
SIGNATURE_HEADER = "X-HiAPI-Signature"
DEFAULT_TOLERANCE = 300  # seconds; reject callbacks older/newer than this


def verify_webhook(
    body: Union[bytes, str],
    *,
    signature: str,
    timestamp: str,
    secret: str,
    tolerance: int = DEFAULT_TOLERANCE,
    now: Optional[int] = None,
) -> Task:
    """Verify a raw callback and return the parsed :class:`Task`.

    Args:
        body: The raw request body, exactly as received (bytes preferred).
        signature: Value of the ``X-HiAPI-Signature`` header.
        timestamp: Value of the ``X-HiAPI-Timestamp`` header.
        secret: The webhook signing key configured in the HiAPI console.
        tolerance: Max allowed clock skew in seconds (0 disables the check).
        now: Override the current Unix time (for testing).

    Raises:
        WebhookVerificationError: missing/blank headers, bad timestamp, stale
            timestamp, or signature mismatch.
    """
    if not signature or not timestamp:
        raise WebhookVerificationError("missing signature or timestamp header")
    if not secret:
        raise WebhookVerificationError("no webhook signing secret configured")

    try:
        ts = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise WebhookVerificationError("invalid timestamp header") from exc

    if tolerance:
        current = int(time.time()) if now is None else int(now)
        if abs(current - ts) > tolerance:
            raise WebhookVerificationError(
                "timestamp outside the allowed tolerance (possible replay)"
            )

    body_bytes = body.encode("utf-8") if isinstance(body, str) else body
    signed = timestamp.encode("ascii") + b"." + body_bytes
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise WebhookVerificationError("signature mismatch")

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise WebhookVerificationError(f"verified body is not valid JSON: {exc}") from exc
    return Task.from_dict(payload)


def _header(headers: Mapping[str, Any], name: str) -> Optional[str]:
    """Case-insensitive header lookup that also accepts framework header maps."""
    getter = getattr(headers, "get", None)
    if getter is not None:
        # Most frameworks' header containers are already case-insensitive.
        value = headers.get(name)
        if value is None:
            value = headers.get(name.lower())
        if value is not None:
            return str(value)
    lowered = name.lower()
    for key, value in dict(headers).items():
        if str(key).lower() == lowered:
            return None if value is None else str(value)
    return None


class Webhooks:
    """Bound helper: ``client.webhooks.verify(body, headers)``."""

    def __init__(self, client: HiAPI, secret: Optional[str]) -> None:
        self._client = client
        self._secret = secret

    def verify(
        self,
        body: Union[bytes, str],
        headers: Mapping[str, Any],
        *,
        secret: Optional[str] = None,
        tolerance: int = DEFAULT_TOLERANCE,
        now: Optional[int] = None,
    ) -> Task:
        """Verify a callback using its request headers.

        Pulls ``X-HiAPI-Timestamp`` / ``X-HiAPI-Signature`` from ``headers``
        (case-insensitive). ``secret`` defaults to the ``webhook_secret`` given
        when constructing the client.
        """
        resolved = secret if secret is not None else self._secret
        if not resolved:
            raise WebhookVerificationError(
                "no webhook secret: pass secret= or set webhook_secret on the client"
            )
        return verify_webhook(
            body,
            signature=_header(headers, SIGNATURE_HEADER) or "",
            timestamp=_header(headers, TIMESTAMP_HEADER) or "",
            secret=resolved,
            tolerance=tolerance,
            now=now,
        )
