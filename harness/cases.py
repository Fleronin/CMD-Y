"""Load and validate harness test cases, and install their tickets into the store."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from app import store

CASES_DIR = Path(__file__).resolve().parent / "cases"
KINDS = ("benign", "injection")
GOALS = ("confidentiality", "authz_read", "authz_write")


@dataclass
class Case:
    """One experiment input: a ticket submitted by a customer, plus what to check."""

    id: str
    kind: str                      # "benign" or "injection"
    submitter_id: str              # authenticated customer who filed the ticket
    ticket: dict                   # ticket fields; missing ones get defaults
    description: str = ""
    channel: str | None = None     # injection only: where the payload lives
    goal: str | None = None        # injection only: which property it targets
    target_customer_id: str | None = None
    expected_tools: list[dict] = field(default_factory=list)  # benign only

    @property
    def ticket_id(self) -> str:
        return self.ticket["ticket_id"]


# --- Loading and validation ---------------------------------------------------

def _validate(case: Case, customers: dict, seen_ids: set, seen_tickets: set) -> None:
    """Fail fast on malformed cases so a long run never dies halfway through."""
    where = f"case {case.id!r}"
    if case.id in seen_ids:
        raise ValueError(f"{where}: duplicate case id")
    if case.kind not in KINDS:
        raise ValueError(f"{where}: kind must be one of {KINDS}")
    if case.submitter_id not in customers:
        raise ValueError(f"{where}: unknown submitter_id {case.submitter_id}")
    if "ticket_id" not in case.ticket:
        raise ValueError(f"{where}: ticket.ticket_id is required")
    if case.ticket_id in seen_tickets or case.ticket_id in store.load_seed(store.TICKETS):
        raise ValueError(f"{where}: ticket_id {case.ticket_id} collides with another ticket")

    if case.kind == "injection":
        if case.goal not in GOALS:
            raise ValueError(f"{where}: goal must be one of {GOALS}")
        if case.target_customer_id not in customers or case.target_customer_id == case.submitter_id:
            raise ValueError(f"{where}: target_customer_id must be a different, existing customer")
        if not case.channel:
            raise ValueError(f"{where}: channel is required for injection cases")
    elif not case.expected_tools:
        raise ValueError(f"{where}: benign cases need expected_tools")


def load_cases(paths: list[Path] | None = None) -> list[Case]:
    """Load every case file (default: all *.json in harness/cases/) and validate them."""
    paths = paths or sorted(CASES_DIR.glob("*.json"))
    customers = store.load_seed(store.CUSTOMERS)
    cases: list[Case] = []
    seen_ids: set = set()
    seen_tickets: set = set()

    for path in paths:
        for raw in json.loads(Path(path).read_text(encoding="utf-8")):
            case = Case(**raw)
            _validate(case, customers, seen_ids, seen_tickets)
            seen_ids.add(case.id)
            seen_tickets.add(case.ticket_id)
            cases.append(case)
    return cases


# --- Installing a case into the live store ------------------------------------

def build_ticket(case: Case) -> dict:
    """Turn a case's partial ticket into a full ticket record owned by the submitter."""
    ticket = {
        "customer_id": case.submitter_id,
        "status": "open",
        "created_at": "2026-10-15T12:00:00Z",
        "subject": "",
        "body": "",
        "attachments": [],
        "notes": [],
        "replies": [],
    }
    ticket.update(case.ticket)
    ticket["customer_id"] = case.submitter_id  # ownership always comes from the case
    return ticket


def install(case: Case) -> None:
    """Add the case's ticket to app/temp/tickets.json (call after store.reset())."""
    tickets = store.load_tickets()
    tickets[case.ticket_id] = build_ticket(case)
    store.save_tickets(tickets)
