# HiAPI Python SDK

Zero-dependency Python client for the [HiAPI](https://hiapi.ai) **unified async task API** (`/v1/tasks`) — submit an image / video / audio generation task, poll it to completion, and read the output in **one call**.

- **Zero runtime dependencies.** Standard library only (`urllib`, `json`, `hmac`).
- **One-call workflow.** `client.tasks.run(...)` submits and waits for you.
- **Typed.** Dataclasses throughout, ships `py.typed`.
- **Webhook verification.** HMAC-SHA256 signature + replay check, built in.

> For OpenAI-compatible chat/image endpoints, keep using the `openai` library with
> `base_url="https://api.hiapi.ai/v1"`. This SDK focuses on what the OpenAI client
> can't do: the asynchronous **submit → poll → download** lifecycle.

## Install

```bash
pip install hiapi
```

Requires Python 3.8+.

## Quick start

```python
from hiapi import HiAPI

client = HiAPI(api_key="sk-...")  # or set HIAPI_API_KEY

task = client.tasks.run(
    model="seedance-2-0",
    input={"prompt": "a cyan glass data center entrance", "resolution": "1080p"},
    on_update=lambda t: print("status:", t.status),
)

for out in task.output:
    print(out.type, out.url)  # e.g. "video https://cdn.hiapi.ai/tasks/..."
```

`run()` blocks until the task reaches a terminal state. It raises `TaskFailed`
if the task fails and `PollTimeout` if it doesn't finish within `timeout`
(default 600s).

## Lower-level control

```python
created = client.tasks.create(
    model="seedance-2-0",
    input={"prompt": "...", "resolution": "720p"},
    callback={"url": "https://your-app.com/hiapi/callback", "when": "final"},
)
print(created.task_id)

task = client.tasks.retrieve(created.task_id)   # one status check
task = client.tasks.wait(created.task_id, poll_interval=3, timeout=900)
page = client.tasks.list(page=1, size=20)       # newest first
```

`input` fields are **defined per model** — see the relevant
[model page](https://docs.hiapi.ai/models/). Don't put callback fields inside
`input`; pass `callback` separately.

## Model routes

Some models expose multiple routes (e.g. `pro`, `ext`) with different pricing or
upstream capacity. Pass `route` instead of writing the `model@route` suffix:

```python
created = client.tasks.create(
    model="gpt-image-2/text-to-image",
    route="pro",                        # preferred over model="...@pro"
    input={"prompt": "..."},
)
```

Omitting `route` (or passing `"default"`) uses the model's default route. An
unknown route fails fast with a 400 whose message lists the available routes.
The legacy `model="x@pro"` spelling keeps working. When a task was submitted
with `route`, its detail echoes `task.route` and `task.model` holds the
resolved full name (`x@pro`).

## Idempotent retries

Pass `idempotency_key` (sent as the `Idempotency-Key` header, ≤255 bytes) to
make task submission safe to retry — same key + same body always returns the
first task instead of creating and billing a new one:

```python
created = client.tasks.create(
    model="seedance-2-0",
    input={"prompt": "..."},
    idempotency_key="order-8472:video",   # a stable key you derive per job
)
if created.idempotent_replay:
    print("hit the idempotency cache; no new task created")
```

With a key set, the SDK also retries the POST on network errors and
automatically waits out `409 IDEMPOTENCY_KEY_PROCESSING` (the first request is
still in flight). Reusing a key with a **different** body raises
`IdempotencyKeyMismatchError` — that's a key-construction bug, not retryable.

## Webhooks

If you set a **Webhook signing key** in the HiAPI console, terminal callbacks are
signed. Verify them against the **raw request body**:

```python
# Flask example
from flask import Flask, request
from hiapi import HiAPI, WebhookVerificationError

app = Flask(__name__)
client = HiAPI(api_key="sk-...", webhook_secret="whsec_...")

@app.post("/hiapi/callback")
def callback():
    try:
        task = client.webhooks.verify(request.get_data(), request.headers)
    except WebhookVerificationError:
        return "", 400
    if task.succeeded:
        print(task.output[0].url)
    return "", 200  # ack with 2xx; HiAPI retries non-2xx
```

Callbacks are delivered **at least once** — deduplicate by `task.task_id`.

## Errors

| Exception | When |
| --- | --- |
| `AuthenticationError` | 401 — bad/missing API key |
| `NotFoundError` | 404 — unknown task or not yours |
| `InvalidRequestError` | `INVALID_REQUEST` — fix the request |
| `ModelUnavailableError` | `MODEL_UNAVAILABLE` — retry or switch model |
| `TaskTimeoutError` / `StorageUnavailableError` | retryable upstream errors |
| `ServiceUnavailableError` | 503 — platform busy (auto-retried) |
| `IdempotencyKeyProcessingError` | 409 — same key still in flight (auto-retried; retryable) |
| `IdempotencyKeyMismatchError` | 422 — key reused with a different body (**not** retryable) |
| `APIConnectionError` | network failure (auto-retried for reads only — **not** a keyless `create()`) |
| `TaskFailed` | a polled task ended in `status=fail` |
| `PollTimeout` | `run()`/`wait()` exceeded its timeout |
| `WebhookVerificationError` | bad signature or stale timestamp |

429/503 are retried automatically with exponential backoff (`max_retries`, default 2;
honours `Retry-After`). Network errors are retried **only for idempotent GETs**
(`retrieve` / `list`, and the polling inside `wait` / `run`). The `POST` that `create()`
issues is **never** retried on a network failure — unless you pass
`idempotency_key`, which makes the retry safe server-side. Without a key, a dropped
connection can't silently create a second, double-charged task — if `create()` raises
`APIConnectionError`, confirm with `list()` before retrying.

## Configuration

```python
HiAPI(
    api_key=None,                       # falls back to HIAPI_API_KEY
    base_url="https://api.hiapi.ai/v1",
    timeout=60.0,                       # per-request seconds
    max_retries=2,
    webhook_secret=None,                # falls back to HIAPI_WEBHOOK_SECRET
)
```

## License

MIT
