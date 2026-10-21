"""Flask app for the CMD-Y web UI.

Run it with:
  python -m webapp.server [--port 5000] [--debug]

This is a developer console over app/, not part of the system under test:
it talks to the same store the CLI and harness use, so it can read and
write any customer's data directly (there is no ownership check here,
unlike the agent's tools).
"""

import argparse

from flask import Flask, render_template


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template("index.html")

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
