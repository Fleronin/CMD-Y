"""Command-line interface for the support-ticket assistant.

Examples:
  python -m app.cli ticket T-1001             # let the agent handle a ticket
  python -m app.cli ticket T-1001 --mock      # same, with the offline mock model
  python -m app.cli submit C001 "Subject" "Body text"   # file a new ticket
  python -m app.cli reset                     # restore app/temp/ to the seed data
"""

import argparse
import json
import sys

from app import agent, configure_output, llm, store, tools


def cmd_ticket(args: argparse.Namespace) -> int:
    """Run the agent on an existing ticket and print what it did."""
    tickets = store.load_tickets()
    if args.ticket_id not in tickets:
        print(f"Unknown ticket: {args.ticket_id}", file=sys.stderr)
        return 1

    # The submitter is the ticket's owner unless explicitly overridden.
    submitter_id = args.as_customer or tickets[args.ticket_id]["customer_id"]
    client = llm.get_client(mock=args.mock)
    model = llm.resolve_model(args.model, mock=args.mock)
    options = {"temperature": args.temperature}
    if args.seed is not None:
        options["seed"] = args.seed

    trace = agent.run_ticket(
        args.ticket_id, submitter_id, client, model,
        options=options, enforce_authz=args.enforce_authz,
    )

    if args.json:
        print(json.dumps(trace.to_dict(), indent=2))
        return 0 if trace.error is None else 2

    # Human-readable summary of the run.
    print(f"Ticket {trace.ticket_id} | submitter {trace.submitter_id} | model {trace.model}")
    for call in trace.tool_calls:
        print(f"  [step {call['step']}] {call['name']}({json.dumps(call['args'])})")
        print(f"      -> {json.dumps(call['result'])[:300]}")
    if trace.error:
        print(f"ERROR: {trace.error}")
        return 2
    print(f"\nFinal response:\n{trace.final_response}")
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    """File a new ticket as a customer (the attacker's only entry point)."""
    customers = store.load_customers()
    if args.customer_id not in customers:
        print(f"Unknown customer: {args.customer_id}", file=sys.stderr)
        return 1

    tickets = store.load_tickets()
    ticket_id = f"T-{max(int(t.split('-')[1]) for t in tickets) + 1}"
    tickets[ticket_id] = {
        "ticket_id": ticket_id,
        "customer_id": args.customer_id,
        "status": "open",
        "created_at": tools.now_utc(),
        "subject": args.subject,
        "body": args.body,
        "attachments": [],
        "notes": [],
        "replies": [],
    }
    store.save_tickets(tickets)
    print(ticket_id)
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    """Reset button: restore the live data to the seed state."""
    store.reset()
    print(f"Reset {store.TEMP_DIR} from {store.DATA_DIR}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ticket", help="Have the agent handle a ticket")
    p.add_argument("ticket_id")
    p.add_argument("--as", dest="as_customer", help="Submitter customer ID (default: ticket owner)")
    p.add_argument("--model", default=llm.DEFAULT_MODEL)
    p.add_argument("--mock", action="store_true", help="Use the offline scripted mock model")
    p.add_argument("--enforce-authz", action="store_true", help="Enable server-side ownership checks")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--json", action="store_true", help="Print the full trace as JSON")
    p.set_defaults(func=cmd_ticket)

    p = sub.add_parser("submit", help="Submit a new ticket as a customer")
    p.add_argument("customer_id")
    p.add_argument("subject")
    p.add_argument("body")
    p.set_defaults(func=cmd_submit)

    p = sub.add_parser("reset", help="Restore app/temp/ to the seed data")
    p.set_defaults(func=cmd_reset)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_output()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
