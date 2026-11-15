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

CHILDREN = [
    ["python3", "-m", "processor"],
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
                return code
        signal.pause()


if __name__ == "__main__":
    sys.exit(main())
