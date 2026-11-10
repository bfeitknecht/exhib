"""Exhib ingest processor.

Consumes manifest.toml upload folders from the incoming queue, creates Hugo
page bundles from them and rebuilds the public site atomically. Run with
``python -m processor``.
"""
