#!/usr/bin/env python3
"""Why do only 19 of 254 Texas counties state all four facts, and 90 none?

Tests the "electoral lull" hypothesis: the 2026 primary (Mar 3) and runoffs
(May 26 / Jun 13) are over and the general (Nov 3) is ~10 weeks out, so counties
may simply not have posted November information yet.

Three programmatic tests:
  A. WHICH ELECTION are counties currently displaying? If the pages mostly
     reference PAST 2026 elections, they are stale rather than silent - a very
     different finding from "this county never publishes anything".
  B. Page STALENESS from git history: when did each county's election pages last
     change? A dormant county cannot have posted November info.
  C. Silence CONDITIONAL on having a page: among counties that do publish an
     elections page, how many still state nothing? This separates "no surface"
     from "surface, but empty".

Output: analysis/output/tx_why_silent.csv  (+ console summary)
"""
from __future__ import annotations

import collections
import csv
import re
import subprocess
from datetime import date
from pathlib import Path

import check_facts as cf          # reuse the vetted parsers

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "snapshots"
OUT = ROOT / "analysis" / "output"

# The 2026 Texas election calendar, so a referenced date can be named.
CALENDAR = [
    ((2026, 3, 3),   "Mar 3 primary (past)"),
    ((2026, 5, 2),   "May 2 uniform (past)"),
    ((2026, 5, 26),  "May 26 primary runoff (past)"),
    ((2026, 6, 13),  "Jun 13 runoff (past)"),
    ((2026, 11, 3),  "Nov 3 general (upcoming)"),
]
CAL = dict(CALENDAR)
TODAY = date(2026, 8, 20)


def git(*a) -> str:
    return subprocess.run(["git", "--no-optional-locks", *a], cwd=ROOT,
                          capture_output=True, text=True).stdout


def last_changed(county: str) -> tuple[str, int]:
    """Date a county's election page text last changed, and days ago."""
    out = git("log", "-1", "--format=%ad", "--date=short",
              "--", f"snapshots/{county}/*/page.txt").strip()
    if not out:
        return ("", -1)
    y, m, d = (int(x) for x in out.split("-"))
    return (out, (TODAY - date(y, m, d)).days)


def main() -> None:
    counties = sorted(p.name for p in SNAP.iterdir() if p.is_dir())
    facts = {}
    for r in csv.DictReader((OUT / "tx_facts.csv").open(encoding="utf-8")):
        facts.setdefault(r["county"], {})[r["fact"]] = r["verdict"]

    rows = []
    for c in counties:
        pages = cf.load_pages(c)
        blob = " ".join(" ".join(lines) for _, lines in pages)
        dates = cf.parse_dates(blob)

        seen = collections.Counter(d for d in dates if d in CAL)
        # Which elections does this county's site currently reference?
        refs = [CAL[d] for d, _ in seen.most_common()]
        mentions_nov = (2026, 11, 3) in seen
        mentions_past = any(d in seen for d, lab in CALENDAR if "past" in lab)

        stated = sum(1 for v in facts.get(c, {}).values() if v in ("Matches expected", "States something else"))
        ptypes = {p for p, _ in pages}
        changed, days = last_changed(c)

        rows.append({
            "county": c,
            "facts_stated": stated,
            "pages_captured": len(pages),
            "has_elections_page": "yes" if "elections" in ptypes else "no",
            "mentions_nov3": "yes" if mentions_nov else "no",
            "mentions_past_2026": "yes" if mentions_past else "no",
            "elections_referenced": "; ".join(refs) or "none of the 2026 calendar",
            "nov3_mentions": seen.get((2026, 11, 3), 0),
            "last_text_change": changed,
            "days_since_change": days,
        })

    dest = OUT / "tx_why_silent.csv"
    with dest.open("w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)

    silent = [r for r in rows if r["facts_stated"] == 0]
    full = [r for r in rows if r["facts_stated"] == 4]

    print(f"254 counties -> {dest.relative_to(ROOT)}\n")
    print("=== TEST A: which 2026 election does the site reference? ===")
    for grp, lab in ((rows, "all 254"), (silent, f"the {len(silent)} silent"),
                     (full, f"the {len(full)} stating all 4")):
        nov = sum(1 for r in grp if r["mentions_nov3"] == "yes")
        past = sum(1 for r in grp if r["mentions_past_2026"] == "yes")
        neither = sum(1 for r in grp if r["mentions_nov3"] == "no"
                      and r["mentions_past_2026"] == "no")
        print(f"  {lab:<24} mentions Nov 3: {nov:>3}/{len(grp):<3} "
              f"| mentions a past 2026 election: {past:>3} | neither: {neither:>3}")

    print("\n=== TEST A2: does mentioning Nov 3 predict stating facts? ===")
    for m in ("yes", "no"):
        g = [r for r in rows if r["mentions_nov3"] == m]
        avg = sum(r["facts_stated"] for r in g) / len(g)
        print(f"  mentions Nov 3 = {m:<3}  n={len(g):>3}  mean facts stated = {avg:.2f}")

    print("\n=== TEST B: page staleness ===")
    for grp, lab in ((rows, "all 254"), (silent, "silent (0 facts)"),
                     (full, "states all 4")):
        d = [r["days_since_change"] for r in grp if r["days_since_change"] >= 0]
        d.sort()
        med = d[len(d) // 2] if d else -1
        never = sum(1 for r in grp if r["days_since_change"] < 0)
        print(f"  {lab:<20} median days since any text change = {med:>3}  "
              f"(no recorded change: {never})")

    print("\n=== TEST C: silence conditional on having an elections page ===")
    for hp in ("yes", "no"):
        g = [r for r in rows if r["has_elections_page"] == hp]
        z = sum(1 for r in g if r["facts_stated"] == 0)
        print(f"  has elections page = {hp:<3}  n={len(g):>3}  "
              f"stating zero facts: {z:>3} ({100*z/len(g):.0f}%)")

    print("\n=== the calendar, as referenced across all counties ===")
    tally = collections.Counter()
    for r in rows:
        for lab in r["elections_referenced"].split("; "):
            tally[lab] += 1
    for lab, n in tally.most_common():
        print(f"  {n:>4}  {lab}")


if __name__ == "__main__":
    main()
