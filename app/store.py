"""Persistent JSON store that acts as the mock support "server".

app/data/ holds the committed seed dataset and is never written to.
app/temp/ holds the live state (gitignored). Every read and write goes
through temp/, which is seeded from data/ the first time it is needed.
"""

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
TEMP_DIR = APP_DIR / "temp"

CUSTOMERS = "customers.json"
TICKETS = "tickets.json"
FILES = (CUSTOMERS, TICKETS)

# "utf-8-sig" also accepts files saved with a byte-order mark (e.g. by Windows Notepad).
READ_ENCODING = "utf-8-sig"


# --- Low-level file helpers ---------------------------------------------------

def _replace(src: str, dst: Path, attempts: int = 10) -> None:
    """os.replace with retries.

    On Windows, antivirus or search indexing can hold a file open for a moment,
    which makes os.replace raise PermissionError. Retrying briefly avoids a
    spurious failure; anything still locked after ~1s is a real error.
    """
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.1)


def _atomic_write(name: str, text: str) -> None:
    """Write text to temp/<name> via a temporary file and an atomic swap."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=TEMP_DIR, prefix=f".{name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        _replace(tmp_path, TEMP_DIR / name)
    except BaseException:
        # Clean up the partial temp file if anything went wrong before the swap.
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


# --- Initialization and reset -------------------------------------------------

def init(force: bool = False) -> None:
    """Create temp/ from the seed data if it (or any of its files) is missing.

    If temp/ is complete, it is left untouched so state persists between runs.
    If only some files are missing, all files are re-seeded together, because
    tickets reference customers and a half-reset store would be inconsistent.
    force=True re-seeds unconditionally.
    """
    if not force and all((TEMP_DIR / name).exists() for name in FILES):
        return

    for name in FILES:
        _atomic_write(name, (DATA_DIR / name).read_text(encoding=READ_ENCODING))


def reset() -> None:
    """Reset button: clear the live state and re-run initialization.

    After this call temp/ is an exact copy of the seed data in data/. The seed
    files are written over the live ones instead of deleting the folder first,
    so a file briefly locked on Windows raises an error rather than silently
    leaving old data behind.
    """
    if TEMP_DIR.exists():
        for path in TEMP_DIR.iterdir():
            if path.is_file() and path.name not in FILES:
                path.unlink(missing_ok=True)  # stray .tmp files from an interrupted save
    init(force=True)


# --- Reading ------------------------------------------------------------------

def load(name: str) -> dict:
    """Read one live JSON file from temp/, seeding temp/ first if needed."""
    init()
    with open(TEMP_DIR / name, encoding=READ_ENCODING) as f:
        return json.load(f)


def snapshot() -> dict:
    """Return a copy of the full live state, used by the harness for before/after diffs."""
    return {"customers": load(CUSTOMERS), "tickets": load(TICKETS)}


def load_seed(name: str) -> dict:
    """Read the original seed file from data/ (used to diff against live state)."""
    with open(DATA_DIR / name, encoding=READ_ENCODING) as f:
        return json.load(f)


# --- Writing ------------------------------------------------------------------

def save(name: str, data: dict) -> None:
    """Atomically write one live JSON file in temp/.

    The data is written to a temporary file in the same directory and then
    swapped in with os.replace, so a crash mid-write never leaves a
    half-written JSON file behind.
    """
    init()
    _atomic_write(name, json.dumps(data, indent=2) + "\n")


# --- Convenience wrappers -----------------------------------------------------

def load_customers() -> dict:
    return load(CUSTOMERS)


def load_tickets() -> dict:
    return load(TICKETS)


def save_customers(data: dict) -> None:
    save(CUSTOMERS, data)


def save_tickets(data: dict) -> None:
    save(TICKETS, data)


def create_ticket(customer_id: str, subject: str, body: str) -> str:
    """File a new ticket for a customer and return its ID.

    Shared by the CLI's `submit` command and the web UI, so the ticket-ID
    scheme (next T-NNNN after the highest existing one) only lives in one
    place. The caller is responsible for checking that customer_id exists.
    """
    tickets = load_tickets()
    ticket_id = f"T-{max(int(t.split('-')[1]) for t in tickets) + 1}"
    tickets[ticket_id] = {
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "status": "open",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "subject": subject,
        "body": body,
        "attachments": [],
        "notes": [],
        "replies": [],
    }
    save_tickets(tickets)
    return ticket_id
