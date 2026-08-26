#!/usr/bin/env python3
"""Re-run the four-fact check against HISTORICAL snapshots.

The lull hypothesis says counties simply have not switched to the November
general yet. "Counties mentioning Nov 3" already rises monotonically across the
history, but that is a proxy. This runs the actual fact checker at several past
commits so the OUTCOME variable can be measured over time.

Each commit's snapshots/ tree is extracted to a scratch directory with
`git archive` and the vetted checker is pointed at it - no working-tree changes,
and nothing in the repo is touched.

Output: analysis/output/tx_coverage_over_time.csv
"""
from __future__ import annotations

import csv
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import check_facts as cf                                    # noqa: E402

OUT = ROOT / "analysis" / "output"

# Roughly weekly across the 756-target era. The two 381-target runs on 07-29 are
# excluded: a different manifest scope is not comparable.
COMMITS = ["44063a9e", "8e9d784d", "3a856395", "d021fbdf",
           "cb5e70c69", "c92ed8a15", "fba0768b6", "5aee6dddf",
           "2bc697f5f", "3be83ac67", "2a01e26ea"]


def git(*a) -> str:
    return subprocess.run(["git", "--no-optional-locks", *a], cwd=ROOT,
                          capture_output=True, text=True).stdout


def run_at(commit: str, workdir: Path) -> dict:
    """Extract snapshots/ at `commit` and run the checker against it."""
    dest = workdir / commit
    dest.mkdir(parents=True, exist_ok=True)
    tar = subprocess.run(["git", "archive", commit, "snapshots"],
                         cwd=ROOT, capture_output=True)
    subprocess.run(["tar", "-x", "-C", str(dest)], input=tar.stdout, check=True)

    original = cf.SNAP
    cf.SNAP = dest / "snapshots"                            # point the checker at history
    try:
        counties = sorted(p.name for p in cf.SNAP.iterdir() if p.is_dir())
        tally = {"counties": len(counties), "stated_total": 0, "all_four": 0,
                 "zero": 0, "pages": 0}
        per_fact = {f: 0 for f in cf.FACTS}
        for c in counties:
            pages = cf.load_pages(c)
            tally["pages"] += len(pages)
            n = 0
            for fact in cf.FACTS:
                verdict, _, _ = cf.CHECKS[fact](pages)
                if verdict in ("Matches expected", "States something else"):
                    n += 1
                    per_fact[fact] += 1
            tally["stated_total"] += n
            tally["all_four"] += (n == 4)
            tally["zero"] += (n == 0)
        tally.update({f"stated_{k}": v for k, v in per_fact.items()})
        return tally
    finally:
        cf.SNAP = original
        shutil.rmtree(dest, ignore_errors=True)


def main() -> None:
    rows = []
    with tempfile.TemporaryDirectory(prefix="txhist-") as tmp:
        work = Path(tmp)
        for c in COMMITS:
            d = git("log", "-1", "--format=%ad", "--date=format:%Y-%m-%d", c).strip()
            t = run_at(c, work)
            t.update({"commit": c, "run_date": d})
            rows.append(t)
            print(f"  {d}  {c}  counties={t['counties']:>3}  "
                  f"pages={t['pages']:>4}  all4={t['all_four']:>3}  "
                  f"zero={t['zero']:>3}  mean_stated={t['stated_total']/t['counties']:.2f}",
                  flush=True)

    cols = ["run_date", "commit", "counties", "pages", "stated_total", "all_four",
            "zero"] + [f"stated_{f}" for f in cf.FACTS]
    dest = OUT / "tx_coverage_over_time.csv"
    with dest.open("w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(rows)
    print(f"\nwrote {dest.relative_to(ROOT)}")

    a, b = rows[0], rows[-1]
    days = 22
    print(f"\n{a['run_date']} -> {b['run_date']}")
    print(f"  counties stating all four : {a['all_four']:>3} -> {b['all_four']:>3}")
    print(f"  counties stating none     : {a['zero']:>3} -> {b['zero']:>3}")
    print(f"  mean facts stated         : {a['stated_total']/a['counties']:.2f}"
          f" -> {b['stated_total']/b['counties']:.2f}")
    for f in cf.FACTS:
        print(f"  {cf.FACT_LABEL[f]:<24} {a['stated_'+f]:>3} -> {b['stated_'+f]:>3}")


if __name__ == "__main__":
    main()
