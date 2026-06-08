"""A tiny in-process HTTP stub for exercising the SDK without a real backend."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, List, Tuple

# responder(method, path, headers, body) -> (status, payload[, extra_headers])
Responder = Callable[..., Tuple[Any, ...]]


class StubServer:
    def __init__(self) -> None:
        self.requests: List[dict] = []
        self._responder: Responder = lambda *a: (200, {})
        self._httpd = HTTPServer(("127.0.0.1", 0), self._make_handler())
        self.port = self._httpd.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}/v1"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def set_responder(self, fn: Responder) -> None:
        self._responder = fn

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=2)

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # silence test output
                pass

            def _handle(self) -> None:
                length = int(self.headers.get("Content-Length", 0) or 0)
                body = self.rfile.read(length) if length else b""
                server.requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "headers": dict(self.headers.items()),
                        "body": body,
                    }
                )
                result = server._responder(self.command, self.path, self.headers, body)
                status, payload = result[0], result[1]
                extra = result[2] if len(result) > 2 else {}

                if isinstance(payload, (dict, list)):
                    data = json.dumps(payload).encode("utf-8")
                    ctype = "application/json"
                elif isinstance(payload, bytes):
                    data, ctype = payload, "application/json"
                else:
                    data, ctype = str(payload).encode("utf-8"), "text/plain"

                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                for key, value in (extra or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(data)

            do_GET = _handle
            do_POST = _handle

        return Handler


def sequence(responses: List[Tuple[Any, ...]]) -> Responder:
    """A responder that returns each entry in turn; the last entry repeats."""
    state = {"i": 0}

    def responder(method: str, path: str, headers: Any, body: bytes) -> Tuple[Any, ...]:
        i = min(state["i"], len(responses) - 1)
        state["i"] += 1
        return responses[i]

    return responder
