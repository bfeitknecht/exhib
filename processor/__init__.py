"""Exhib ingest processor.

Read manifest.toml upload folders from the incoming queue.
Create Hugo page bundles.
Rebuild the public site with an atomic swap.

Run with ``python -m processor``.
"""
