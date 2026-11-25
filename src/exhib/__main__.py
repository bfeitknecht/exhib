"""The ``exhib`` command.

In the image (the container runs ``exhib serve``):

- ``exhib serve``     the supervisor: watcher, SWS and the web editor.
- ``exhib watch``     watch the inbox and publish uploads (forever).
- ``exhib rebuild``   rebuild the public site once.
- ``exhib variants``  make the missing small copies of every image, then rebuild.
- ``exhib metadata``  bring published images to the kept metadata, then rebuild.
- ``exhib web``       the gallery editor on the PVC (``/upload``).

On the owner's machine:

- ``exhib edit [folder] [--port N] [--no-browser]``  the manifest editor on
  ``uploads/`` (``just manifest``).
"""

from __future__ import annotations

import sys

USAGE = "usage: exhib {serve|watch|rebuild|variants|metadata|web|edit} [args]"


def main() -> int:
    command, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("", [])
    # Import late: `exhib edit` runs on a Mac with none of the image tools.
    if command == "serve" and not args:
        from .supervisor import main as run
    elif command == "watch" and not args:
        from .watch import main as run
    elif command == "rebuild" and not args:
        from .watch import rebuild as run
    elif command == "variants" and not args:
        from .watch import variants as run
    elif command == "metadata" and not args:
        from .watch import metadata as run
    elif command == "web" and not args:
        from .web import main as run
    elif command == "edit":
        from .editor.local import main as run

        return run(args)
    else:
        print(USAGE, file=sys.stderr)
        return 2
    return run() or 0


if __name__ == "__main__":
    sys.exit(main())
