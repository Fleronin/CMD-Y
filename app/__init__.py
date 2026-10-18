"""Mock customer-support ticket assistant (target application for CMD-Y)."""

import sys


def configure_output() -> None:
    """Make stdout/stderr UTF-8 and never crash on unprintable characters.

    When output is redirected on Windows, Python falls back to a legacy code
    page (e.g. cp1252), and printing a model reply containing an emoji or other
    non-ASCII character would raise UnicodeEncodeError mid-run.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
