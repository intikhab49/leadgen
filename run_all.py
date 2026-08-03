"""Run the full leadgen pipeline: NPI fetch -> website discovery -> email extraction."""
import subprocess
import sys
import time
from datetime import datetime

STAGES = [
    ("npi_fetch.py", "Stage 1: NPI Registry providers", []),
    ("find_websites.py", "Stage 2: Website discovery", ["--only-orgs"]),
    ("find_emails.py", "Stage 3: Email extraction", []),
]


def run_stage(script, label, extra_args):
    print(f"\n{'=' * 60}\n{label}\n{'=' * 60}")
    t0 = time.time()
    result = subprocess.run([sys.executable, script] + extra_args, cwd=".")
    dt = time.time() - t0
    print(f"[{label}] finished in {dt:.1f}s with exit code {result.returncode}")
    return result.returncode == 0


def summary():
    import csv
    import os

    final = "outputs/final_leads.csv"
    raw = "outputs/raw_providers.csv"
    web = "outputs/with_websites.csv"

    def count(path):
        if not os.path.exists(path):
            return 0, 0, 0
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        with_site = sum(1 for r in rows if r.get("website", "").strip())
        with_email = sum(1 for r in rows if r.get("emails", "").strip())
        return len(rows), with_site, with_email

    n_raw, _, _ = count(raw)
    n_web, _, _ = count(web)
    n_final, with_site, with_email = count(final)

    print("\n" + "=" * 60)
    print("PIPELINE SUMMARY")
    print("=" * 60)
    print(f"Stage 1 — providers found:       {n_raw}")
    print(f"Stage 2 — websites found:        {with_site} / {n_web}")
    print(f"Stage 3 — sites with emails:     {with_email} / {n_final}")
    if n_final:
        print(f"  Email coverage rate:           {100 * with_email / n_final:.1f}%")
    print("=" * 60)


if __name__ == "__main__":
    args = sys.argv[1:]
    only = None
    if args and args[0] in ("--stage", "-s"):
        if len(args) > 1:
            only = args[1]
        else:
            print("Usage: python run_all.py [--stage 1|2|3]")
            sys.exit(1)

    if only:
        for num, (script, label, extra) in enumerate(STAGES, start=1):
            if str(num) == only:
                run_stage(script, label, extra)
                break
    else:
        for script, label, extra in STAGES:
            if not run_stage(script, label, extra):
                print(f"Stopping: {script} failed.")
                sys.exit(1)

    if only != "1":
        summary()
