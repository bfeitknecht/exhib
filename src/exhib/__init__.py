"""exhib: the gallery's ingest, serving and editing code.

One package, one command (``exhib``, see ``__main__``):

- ``supervisor``: the container entrypoint. Runs the watcher, SWS and the
  web editor, and stops all of them when one exits.
- ``watch``, ``bundle``, ``media``, ``variants``: the processor. It reads
  upload folders from the inbox, converts the media, writes Hugo page
  bundles and rebuilds the public site with an atomic swap.
- ``editor``: the manifest editor page and its rules. ``editor.local``
  serves it on the owner's machine (``just manifest``); ``web`` serves it
  in the cluster on the PVC (``/upload``).
- ``rules``: the names and rules that the processor and the editor share.
- ``paths``: locations and tuning from the environment.
"""
