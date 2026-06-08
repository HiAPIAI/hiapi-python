"""Minimal webhook receiver using only the standard library.

    HIAPI_WEBHOOK_SECRET=whsec_... python examples/callback_server.py

Then create tasks with callback={"url": "https://<public-host>/hiapi/callback"}.
"""

import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from hiapi import HiAPI, WebhookVerificationError

client = HiAPI(
    api_key=os.environ.get("HIAPI_API_KEY", "sk-unused-for-receiving"),
    webhook_secret=os.environ["HIAPI_WEBHOOK_SECRET"],
)
seen = set()  # callbacks are at-least-once; dedupe by task id


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            task = client.webhooks.verify(body, self.headers)
        except WebhookVerificationError as exc:
            self.send_response(400)
            self.end_headers()
            print("rejected callback:", exc)
            return

        self.send_response(200)  # ack fast; non-2xx triggers retries
        self.end_headers()

        if task.task_id in seen:
            return
        seen.add(task.task_id)
        if task.succeeded:
            print("done", task.task_id, [o.url for o in task.output])
        else:
            print("failed", task.task_id, task.error and task.error.code)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
