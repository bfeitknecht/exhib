"""Run the gallery's serving stack in one container: media processor and
static-web-server (SWS), supervised from here.

If either process exits, the other is stopped and this supervisor exits
with the same code, so Kubernetes restarts the pod instead of leaving a
half-dead gallery. SIGTERM and SIGINT are forwarded to both children.
"""

import signal
import subprocess
import sys
import time

from processor.paths import CONTENT, INCOMING, ORIGINALS, PUBLIC

CHILDREN = [
    ["python", "-m", "processor"],
    ["static-web-server"],
]


def terminate_all(processes: list[subprocess.Popen]) -> None:
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    deadline = time.monotonic() + 10
    for proc in processes:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    # SWS exits at once if its root is missing. Create it before the start.
    for path in (INCOMING, CONTENT, ORIGINALS, PUBLIC):
        path.mkdir(parents=True, exist_ok=True)
    processes = [subprocess.Popen(cmd) for cmd in CHILDREN]
    shutting_down = {"flag": False}

    def forward(signum, _frame):
        shutting_down["flag"] = True
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()

    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)
    signal.signal(signal.SIGCHLD, lambda _signum, _frame: None)

    while True:
        for proc in processes:
            code = proc.poll()
            if code is not None:
                terminate_all(processes)
                # A negative code is a signal. Report it as 128 + N, like a shell.
                return 128 - code if code < 0 else code
        signal.pause()


if __name__ == "__main__":
    sys.exit(main())
