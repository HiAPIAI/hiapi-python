"""Submit a task and wait for the result (polling), in one call.

    HIAPI_API_KEY=sk-... python examples/run_and_poll.py
"""

from hiapi import HiAPI, PollTimeout, TaskFailed

client = HiAPI()  # reads HIAPI_API_KEY

try:
    task = client.tasks.run(
        model="seedance-2-0",
        input={"prompt": "a cyan glass data center entrance", "resolution": "1080p"},
        on_update=lambda t: print("status:", t.status),
        poll_interval=3.0,
        timeout=600,
    )
except TaskFailed as exc:
    print("task failed:", exc.code, exc.message)
except PollTimeout as exc:
    print("still running after", exc.timeout, "s — retrieve later:", exc.task_id)
else:
    for out in task.output:
        print(out.type, out.url)
