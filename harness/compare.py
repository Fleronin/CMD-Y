"""Build the D3 before/after tables from the committed summary.json files.

Usage (from the repo root):
  python -m harness.compare            # every injection case
  python -m harness.compare --strongest  # one case per vector (Table 4 in the report)

Reads results/{baseline,after_prompt,after_authz}/{gemma,gptoss}/summary.json
and prints Markdown tables, so every number in the report traces back to a
committed file.
"""

import argparse
import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "results"
MODELS = [("gemma", "Gemma 4 31B"), ("gptoss", "gpt-oss 20B")]
CONDITIONS = [("baseline", "Baseline"), ("after_prompt", "Prompt defense"), ("after_authz", "Code check")]

# Strongest case per vector, as listed in Table 4 of the report.
STRONGEST = [
    ("V1", "inj2-subject-merge"),
    ("V2", "inj3-hidden-authorized-user"),
    ("V3", "inj3-metadata-authorized-user"),
    ("V4", "inj2-note-authorized-user"),
]


def load(condition: str, model: str) -> dict:
    path = RESULTS / condition / model / "summary.json"
    if not path.exists():
        sys.exit(f"Missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def frac(r: dict) -> str:
    return f"{r['successes']}/{r['n']}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m harness.compare", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--strongest", action="store_true", help="Only the strongest case per vector")
    args = p.parse_args(argv)

    data = {(c, m): load(c, m) for c, _ in CONDITIONS for m, _ in MODELS}

    if args.strongest:
        rows = STRONGEST
    else:
        cases = data[("baseline", "gemma")]["per_case"]
        rows = [("", cid) for cid, e in cases.items() if e["kind"] == "injection"]

    print("| Vector | Case | Model | Baseline | Prompt defense | Code check | Attempts under code check |")
    print("|---|---|---|---|---|---|---|")
    for vec, cid in rows:
        for m, label in MODELS:
            cells = [frac(data[(c, m)]["per_case"][cid]["attack_success"]) for c, _ in CONDITIONS]
            attempts = frac(data[("after_authz", m)]["per_case"][cid]["authz_attempted"])
            print(f"| {vec} | {cid} | {label} | " + " | ".join(cells) + f" | {attempts} |")

    print()
    print("| Model | Metric | Baseline | Prompt defense | Code check |")
    print("|---|---|---|---|---|")
    for m, label in MODELS:
        for key, name in [("attack_success_rate", "Attack success (all injection trials)"),
                          ("benign_task_completion_rate", "Benign task completion"),
                          ("benign_violation_rate", "Benign violations")]:
            cells = [frac(data[(c, m)]["overall"][key]) for c, _ in CONDITIONS]
            print(f"| {label} | {name} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())