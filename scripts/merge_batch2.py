#!/usr/bin/env python3
"""Merge a batch's discovery output into manifest/targets.csv.

Combines:
  manifest/batch<N>_homepages.csv       -> the homepage row per county
  manifest/batch<N>_targets_draft.csv   -> the 4 election page rows per county

with whatever is already in manifest/targets.csv, producing one unified manifest
of 254 counties x 5 page types = 1,270 rows once every batch is merged.

Rows from other batches are preserved exactly as-is, including their audit
columns. The merged batch is (re)written with empty audit columns for
audit_targets.py to populate.

Idempotent: re-running replaces that batch's rows rather than duplicating them.

Usage:
    python scripts/merge_batch2.py --batch 3
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ROOT / "manifest" / "targets.csv"


BASE = ["county", "batch", "page_type", "url", "external", "notes"]
AUDIT = ["verify_status", "http_status", "final_url", "audit_confidence",
         "audit_reason", "flag_for_review"]
PAGE_ORDER = ["homepage", "elections", "polling", "early_voting", "results"]


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="2", help="which batch to merge (default 2)")
    args = ap.parse_args()
    batch = str(args.batch)
    HOMEPAGES = ROOT / "manifest" / f"batch{batch}_homepages.csv"
    DRAFT = ROOT / "manifest" / f"batch{batch}_targets_draft.csv"
    for f in (HOMEPAGES, DRAFT):
        if not f.exists():
            raise SystemExit(f"missing {f} — run Phase 1 discovery for batch {batch} first")

    existing = list(csv.DictReader(TARGETS.open(encoding="utf-8")))
    keep = [r for r in existing if str(r.get("batch", "1")).strip() != batch]

    homes = {r["county"]: r for r in csv.DictReader(HOMEPAGES.open(encoding="utf-8"))}
    draft: dict[tuple[str, str], dict] = {}
    for r in csv.DictReader(DRAFT.open(encoding="utf-8")):
        draft[(r["county"], r["page_type"])] = r

    merged: list[dict] = []
    for county, h in homes.items():
        for ptype in PAGE_ORDER:
            if ptype == "homepage":
                note = h.get("evidence", "")
                if h.get("confidence") != "confident":
                    note = f"REVIEW ({h.get('confidence')}): {note}"
                row = {"county": county, "batch": batch, "page_type": "homepage",
                       "url": h.get("homepage", "").strip(), "external": "false",
                       "notes": f"discovered homepage — {note}"[:300]}
            else:
                d = draft.get((county, ptype))
                if d is None:
                    row = {"county": county, "batch": batch, "page_type": ptype,
                           "url": "", "external": "false",
                           "notes": "GAP: not discovered (homepage unreachable during discovery)"}
                else:
                    row = {"county": county, "batch": batch, "page_type": ptype,
                           "url": d["url"].strip(), "external": d["external"],
                           "notes": d["notes"][:300]}
            row.update({f: "" for f in AUDIT})
            merged.append(row)

    rows = keep + merged
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
    print(f"  kept: {len(keep)} rows | batch {batch}: {len(merged)} rows")


if __name__ == "__main__":
    main()
