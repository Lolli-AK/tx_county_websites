#!/usr/bin/env python3
"""Merge Batch 2 discovery output into manifest/targets.csv.

Combines:
  manifest/batch2_homepages.csv       -> the homepage row per county
  manifest/batch2_targets_draft.csv   -> the 4 election page rows per county

with the existing Batch 1 rows already in manifest/targets.csv, producing one
unified manifest of 124 counties x 5 page types = 620 rows.

Batch 1 rows are preserved exactly as-is, including their audit columns. Batch 2
rows are appended with empty audit columns for audit_targets.py to populate.

Idempotent: re-running replaces any existing batch-2 rows rather than duplicating.

Usage:
    python scripts/merge_batch2.py
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ROOT / "manifest" / "targets.csv"
HOMEPAGES = ROOT / "manifest" / "batch2_homepages.csv"
DRAFT = ROOT / "manifest" / "batch2_targets_draft.csv"

BASE = ["county", "batch", "page_type", "url", "external", "notes"]
AUDIT = ["verify_status", "http_status", "final_url", "audit_confidence",
         "audit_reason", "flag_for_review"]
PAGE_ORDER = ["homepage", "elections", "polling", "early_voting", "results"]


def main() -> None:
    existing = list(csv.DictReader(TARGETS.open(encoding="utf-8")))
    batch1 = [r for r in existing if str(r.get("batch", "1")).strip() == "1"]

    homes = {r["county"]: r for r in csv.DictReader(HOMEPAGES.open(encoding="utf-8"))}
    draft: dict[tuple[str, str], dict] = {}
    for r in csv.DictReader(DRAFT.open(encoding="utf-8")):
        draft[(r["county"], r["page_type"])] = r

    batch2: list[dict] = []
    for county, h in homes.items():
        for ptype in PAGE_ORDER:
            if ptype == "homepage":
                note = h.get("evidence", "")
                if h.get("confidence") != "confident":
                    note = f"REVIEW ({h.get('confidence')}): {note}"
                row = {"county": county, "batch": "2", "page_type": "homepage",
                       "url": h.get("homepage", "").strip(), "external": "false",
                       "notes": f"discovered homepage — {note}"[:300]}
            else:
                d = draft.get((county, ptype))
                if d is None:
                    row = {"county": county, "batch": "2", "page_type": ptype,
                           "url": "", "external": "false",
                           "notes": "GAP: not discovered (homepage unreachable during discovery)"}
                else:
                    row = {"county": county, "batch": "2", "page_type": ptype,
                           "url": d["url"].strip(), "external": d["external"],
                           "notes": d["notes"][:300]}
            row.update({f: "" for f in AUDIT})
            batch2.append(row)

    rows = batch1 + batch2
    for r in rows:
        for f in BASE + AUDIT:
            r.setdefault(f, "")

    with TARGETS.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=BASE + AUDIT, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    counties = {r["county"] for r in rows}
    urls = sum(1 for r in rows if r["url"])
    print(f"wrote {TARGETS}")
    print(f"  counties: {len(counties)}  rows: {len(rows)}  "
          f"with URLs: {urls}  gaps: {len(rows) - urls}")
    print(f"  batch 1: {len(batch1)} rows | batch 2: {len(batch2)} rows")


if __name__ == "__main__":
    main()
