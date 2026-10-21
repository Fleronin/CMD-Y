"""Flask app for the CMD-Y web UI.

Run it with:
  python -m webapp.server [--port 5000] [--debug]

This is a developer console over app/, not part of the system under test:
it talks to the same store the CLI and harness use, so it can read and
write any customer's data directly (there is no ownership check here,
unlike the agent's tools).
"""

import argparse

from flask import Flask, abort, jsonify, render_template, request

from app import store


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/customers")
    def api_customers():
        """All customers, full records: this console has god-mode access to the store."""
        customers = store.load_customers()
        return jsonify(sorted(customers.values(), key=lambda c: c["customer_id"]))

    @app.get("/api/tickets")
    def api_tickets():
        """Tickets, optionally filtered to one customer via ?customer_id=."""
        customer_id = request.args.get("customer_id")
        tickets = list(store.load_tickets().values())
        if customer_id:
            tickets = [t for t in tickets if t["customer_id"] == customer_id]
        tickets.sort(key=lambda t: t["created_at"])
        return jsonify(tickets)

    @app.get("/api/tickets/<ticket_id>")
    def api_ticket(ticket_id):
        ticket = store.load_tickets().get(ticket_id)
        if ticket is None:
            abort(404, description=f"Unknown ticket_id: {ticket_id}")
        return jsonify(ticket)

    @app.post("/api/tickets")
    def api_submit_ticket():
        """File a new ticket as a customer: the attacker's only entry point."""
        body = request.get_json(silent=True) or {}
        customer_id = (body.get("customer_id") or "").strip()
        subject = (body.get("subject") or "").strip()
        text = (body.get("body") or "").strip()

        if customer_id not in store.load_customers():
            abort(400, description=f"Unknown customer_id: {customer_id}")
        if not subject or not text:
            abort(400, description="subject and body are required")

        ticket_id = store.create_ticket(customer_id, subject, text)
        return jsonify(store.load_tickets()[ticket_id]), 201

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m webapp.server", description=__doc__)
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true", help="Enable Flask's auto-reload and debugger")
    args = parser.parse_args(argv)

    create_app().run(port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
