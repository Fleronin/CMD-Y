"""Persistent JSON store that acts as the mock support "server".

app/data/ holds the committed seed dataset and is never written to.
app/temp/ holds the live state (gitignored). Every read and write goes
through temp/, which is seeded from data/ the first time it is needed.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
TEMP_DIR = APP_DIR / "temp"

CUSTOMERS = "customers.json"
TICKETS = "tickets.json"
FILES = (CUSTOMERS, TICKETS)


# --- Initialization and reset -------------------------------------------------

def init() -> None:
    """Create temp/ from the seed data if it (or any of its files) is missing.

    If temp/ is complete, it is left untouched so state persists between runs.
    If only some files are missing, all files are re-seeded together, because
    tickets reference customers and a half-reset store would be inconsistent.
    """
    if all((TEMP_DIR / name).exists() for name in FILES):
        return

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copyfile(DATA_DIR / name, TEMP_DIR / name)


def reset() -> None:
    """Reset button: wipe the live state and re-run initialization.

    After this call temp/ is an exact copy of the seed data in data/.
    """
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    init()


# --- Reading ------------------------------------------------------------------

def load(name: str) -> dict:
    """Read one live JSON file from temp/, seeding temp/ first if needed."""
    init()
    with open(TEMP_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def snapshot() -> dict:
    """Return a copy of the full live state, used by the harness for before/after diffs."""
    return {"customers": load(CUSTOMERS), "tickets": load(TICKETS)}


def load_seed(name: str) -> dict:
    """Read the original seed file from data/ (used to diff against live state)."""
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


# --- Writing ------------------------------------------------------------------

def save(name: str, data: dict) -> None:
    """Atomically write one live JSON file in temp/.

    The data is written to a temporary file in the same directory and then
    swapped in with os.replace, so a crash mid-write never leaves a
    half-written JSON file behind.
    """
    init()
    fd, tmp_path = tempfile.mkstemp(dir=TEMP_DIR, prefix=f".{name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, TEMP_DIR / name)
    except BaseException:
        # Clean up the partial temp file if anything went wrong before the swap.
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


# --- Convenience wrappers -----------------------------------------------------

def load_customers() -> dict:
    return load(CUSTOMERS)


def load_tickets() -> dict:
    return load(TICKETS)


def save_customers(data: dict) -> None:
    save(CUSTOMERS, data)


def save_tickets(data: dict) -> None:
    save(TICKETS, data)
