"""Run every harness case N times, score each trial, and report the numbers.

Examples:
  python -m harness.run --trials 10            # real model (needs OLLAMA_API_KEY or ollama signin)
  python -m harness.run --trials 3 --mock      # offline pipeline check, no key needed
  python -m harness.run --cases inj-stored-note benign-refund --trials 20
  python -m harness.run --enforce-authz        # measure the server-side authz fix

Output goes to results/<timestamp>_<model>[_authz]/:
  config.json   run settings
  runs.jsonl    one line per trial: full trace + score
  summary.json  per-case and overall rates with Wilson 95% confidence intervals
"""

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

from app import agent, configure_output, llm, store
from harness import cases as case_lib
from harness import score as scorer

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


# --- Statistics ---------------------------------------------------------------

def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% interval for a proportion; well-behaved at 0 and n."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (round(max(0.0, center - half), 4), round(min(1.0, center + half), 4))


def rate(successes: int, n: int) -> dict:
    lo, hi = wilson(successes, n)
    return {"successes": successes, "n": n, "rate": round(successes / n, 4) if n else 0.0,
            "ci95": [lo, hi]}


# --- Running one trial --------------------------------------------------------

def run_trial(case, client, model: str, options: dict, enforce_authz: bool,
              max_steps: int, retries: int) -> tuple[agent.Trace, dict, int]:
    """Reset the store, install the case, run the agent, and score the result.

    Transient API errors are retried from a fresh store. Hitting max_steps is
    not retried, since that is the model's behavior rather than a failure.
    """
    attempts = 0
    while True:
        attempts += 1
        store.reset()
        case_lib.install(case)
        before = store.snapshot()
        trace = agent.run_ticket(case.ticket_id, case.submitter_id, client, model,
                                 options=options, enforce_authz=enforce_authz, max_steps=max_steps)
        after = store.snapshot()

        api_error = trace.error is not None and not trace.error.startswith("max_steps")
        if api_error and attempts <= retries:
            time.sleep(2 * attempts)
            continue
        return trace, scorer.score(case, trace, before, after), attempts


# --- Summarizing --------------------------------------------------------------

def summarize(records: list[dict], cases: list) -> dict:
    """Aggregate per-case and overall rates. Errored trials are excluded from rates."""
    per_case = {}
    for case in cases:
        rows = [r for r in records if r["case_id"] == case.id]
        ok = [r for r in rows if not r["score"]["errored"]]
        entry = {"kind": case.kind, "trials": len(rows), "errored": len(rows) - len(ok)}
        if case.kind == "injection":
            entry.update(channel=case.channel, goal=case.goal, target=case.target_customer_id)
            entry["attack_success"] = rate(sum(r["score"]["attack_success"] for r in ok), len(ok))
            entry["goal_achieved"] = rate(sum(r["score"]["goal_achieved"] for r in ok), len(ok))
        else:
            entry["violation"] = rate(sum(r["score"]["any_violation"] for r in ok), len(ok))
            entry["task_completed"] = rate(sum(r["score"]["task_completed"] for r in ok), len(ok))
        entry["authz_attempted"] = rate(sum(bool(r["score"]["authz_attempts"]) for r in ok), len(ok))
        per_case[case.id] = entry

    inj = [r for r in records if r["kind"] == "injection" and not r["score"]["errored"]]
    ben = [r for r in records if r["kind"] == "benign" and not r["score"]["errored"]]
    overall = {
        "attack_success_rate": rate(sum(r["score"]["attack_success"] for r in inj), len(inj)),
        "goal_achieved_rate": rate(sum(r["score"]["goal_achieved"] for r in inj), len(inj)),
        "benign_violation_rate": rate(sum(r["score"]["any_violation"] for r in ben), len(ben)),
        "benign_task_completion_rate": rate(sum(r["score"]["task_completed"] for r in ben), len(ben)),
        "errored_trials": sum(r["score"]["errored"] for r in records),
        "total_trials": len(records),
    }
    return {"overall": overall, "per_case": per_case}


def _fmt(r: dict) -> str:
    return f"{r['successes']}/{r['n']} = {r['rate']:.0%} [{r['ci95'][0]:.0%}, {r['ci95'][1]:.0%}]"


def print_summary(summary: dict) -> None:
    """Print a compact table to the console."""
    print("\nPer case")
    print(f"  {'case':28} {'channel':20} {'metric':16} result (95% CI)")
    for cid, e in summary["per_case"].items():
        if e["kind"] == "injection":
            print(f"  {cid:28} {e['channel']:20} {'attack success':16} {_fmt(e['attack_success'])}")
        else:
            print(f"  {cid:28} {'-':20} {'task completed':16} {_fmt(e['task_completed'])}"
                  f"   violations {e['violation']['successes']}")
        if e["errored"]:
            print(f"  {'':28} {'':20} {'errored':16} {e['errored']}")

    o = summary["overall"]
    print("\nOverall")
    print(f"  Attack success rate (ASR):   {_fmt(o['attack_success_rate'])}")
    print(f"  Goal achieved rate:          {_fmt(o['goal_achieved_rate'])}")
    print(f"  Benign violation rate:       {_fmt(o['benign_violation_rate'])}")
    print(f"  Benign task completion rate: {_fmt(o['benign_task_completion_rate'])}")
    print(f"  Errored trials:              {o['errored_trials']}/{o['total_trials']}")


# --- CLI ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m harness.run", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--trials", type=int, default=5, help="Trials per case (default 5)")
    p.add_argument("--cases", nargs="*", help="Only run these case IDs (default: all)")
    p.add_argument("--kind", choices=case_lib.KINDS, help="Only run benign or injection cases")
    p.add_argument("--model", default=llm.DEFAULT_MODEL)
    p.add_argument("--mock", action="store_true", help="Use the offline scripted mock model")
    p.add_argument("--enforce-authz", action="store_true", help="Enable server-side ownership checks")
    p.add_argument("--temperature", type=float, default=None,
                   help="Sampling temperature (default: the model's own default)")
    p.add_argument("--seed", type=int, default=None, help="Base seed; trial i uses seed + i")
    p.add_argument("--max-steps", type=int, default=agent.MAX_STEPS)
    p.add_argument("--retries", type=int, default=1, help="Retries per trial on API errors")
    p.add_argument("--out", type=Path, default=None, help="Output directory (default: results/<timestamp>...)")
    return p


def main(argv: list[str] | None = None) -> int:
    configure_output()
    args = build_parser().parse_args(argv)

    # Select cases.
    cases = case_lib.load_cases()
    if args.cases:
        unknown = set(args.cases) - {c.id for c in cases}
        if unknown:
            print(f"Unknown case IDs: {sorted(unknown)}", file=sys.stderr)
            return 1
        cases = [c for c in cases if c.id in args.cases]
    if args.kind:
        cases = [c for c in cases if c.kind == args.kind]
    if not cases:
        print("No cases selected.", file=sys.stderr)
        return 1

    # Set up the model and the output directory.
    client = llm.get_client(mock=args.mock)
    model = llm.resolve_model(args.model, mock=args.mock)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = args.out or RESULTS_DIR / f"{stamp}_{model.replace(':', '-')}{'_authz' if args.enforce_authz else ''}"
    out.mkdir(parents=True, exist_ok=True)

    config = {
        "started_at": stamp, "model": model, "mock": args.mock, "enforce_authz": args.enforce_authz,
        "trials": args.trials, "temperature": args.temperature, "seed": args.seed,
        "max_steps": args.max_steps, "retries": args.retries, "cases": [c.id for c in cases],
    }
    (out / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"Running {len(cases)} cases x {args.trials} trials with {model} -> {out}")

    # Run every trial, appending each result to runs.jsonl as soon as it finishes
    # so a crash or Ctrl-C still leaves the completed trials on disk.
    records = []
    with open(out / "runs.jsonl", "w", encoding="utf-8") as runs_file:
        for case in cases:
            for i in range(args.trials):
                options = {}
                if args.temperature is not None:
                    options["temperature"] = args.temperature
                if args.seed is not None:
                    options["seed"] = args.seed + i

                started = time.time()
                trace, result, attempts = run_trial(case, client, model, options or None,
                                                    args.enforce_authz, args.max_steps, args.retries)
                record = {
                    "case_id": case.id, "kind": case.kind, "trial": i, "attempts": attempts,
                    "seconds": round(time.time() - started, 2), "options": options,
                    "score": result, "trace": trace.to_dict(),
                }
                records.append(record)
                runs_file.write(json.dumps(record) + "\n")
                runs_file.flush()

                flag = ("ERROR" if result["errored"]
                        else "SUCCESS" if result["attack_success"]
                        else "violation" if result["any_violation"] else "ok")
                print(f"  {case.id:28} trial {i + 1}/{args.trials}  {flag:9} {record['seconds']}s")

    # Leave the live store clean for the next interactive session.
    store.reset()

    summary = summarize(records, cases)
    summary["config"] = config
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print_summary(summary)
    print(f"\nWrote {out / 'summary.json'}")

    # Every trial failing means a setup problem, not a 0% result.
    if records and summary["overall"]["errored_trials"] == len(records):
        first_error = records[0]["trace"]["error"]
        print(f"\nWARNING: all {len(records)} trials errored ({first_error}).", file=sys.stderr)
        print("Check OLLAMA_API_KEY in .env (or `ollama signin`), or use --mock.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
