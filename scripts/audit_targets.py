#!/usr/bin/env python3
"""Verify + audit every URL in manifest/targets.csv.

For each row with a URL: re-fetch it fresh (plain first, escalate to headless on
JS-shell / failure, same as the pipeline), then audit whether the content really
belongs to the intended county + page type by looking for identity keywords
(county name, county seat) and page-type keywords (early voting, polling, ...).

Writes the findings BACK into targets.csv as extra columns (the pipeline ignores
unknown columns, so this is safe):
    verify_status   ok | broken | gap
    http_status
    final_url       (only when it differs from the requested url)
    audit_confidence  confident | likely | uncertain | broken | gap
    audit_reason      why we think it is / isn't the right page
    flag_for_review   yes  (when a human should eyeball it)

Also writes a human-readable summary to logs/audit-report.md.

Usage:
    python scripts/audit_targets.py                # audit all
    python scripts/audit_targets.py --county harris
    python scripts/audit_targets.py --no-headless  # faster, plain only
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import logging
import sys
import threading
from pathlib import Path

import normalize
import snapshot

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifest" / "targets.csv"
REPORT = ROOT / "manifest" / "audit-report.md"

log = logging.getLogger("audit")

# Plain fetches parallelize freely, but Playwright's sync API is not safe to drive
# from several threads at once, so headless renders are serialized behind a lock.
_HEADLESS_LOCK = threading.Lock()
_LOG_LOCK = threading.Lock()

# County seat (adds a second identity signal beyond the county name).
# Batch 2 seats are imported from the discovery module so there is one source of truth.
SEATS = {
    "Harris": "Houston", "Dallas": "Dallas", "Tarrant": "Fort Worth",
    "Bexar": "San Antonio", "Travis": "Austin", "Collin": "McKinney",
    "El Paso": "El Paso", "Hidalgo": "Edinburg", "Williamson": "Georgetown",
    "Webb": "Laredo", "Lubbock": "Lubbock", "Bell": "Belton",
    "Galveston": "Galveston", "Kerr": "Kerrville", "Gillespie": "Fredericksburg",
    "Medina": "Hondo", "Llano": "Llano", "Brewster": "Alpine",
    "Presidio": "Marfa", "Hartley": "Channing", "Roberts": "Miami",
    "Loving": "Mentone", "King": "Guthrie", "Kenedy": "Sarita",
}
try:  # add the 100 Batch 2 county seats
    from discover_homepages import BATCH2 as _B2
    SEATS.update(dict(_B2))
except ImportError:  # pragma: no cover - discovery module always ships alongside
    pass

# Page-type keywords. First list = strong (specific) signals, second = weak.
TYPE_KEYWORDS = {
    "homepage": (["county"], ["commissioners", "district clerk", "tax", "sheriff", "county judge"]),
    "elections": (["election", "voter", "voting", "ballot"], ["registration", "vote"]),
    "polling": (["polling", "vote center", "voting center", "election day", "where to vote", "poll location"],
                ["location", "precinct"]),
    "early_voting": (["early voting", "early vote", "advance voting"], ["schedule", "hours"]),
    "results": (["election result", "results", "returns", "canvass", "election night", "list elections", "unofficial"],
                ["reporting", "precinct"]),
}

# Signals that a page is an error / wrong page even if HTTP 200.
BAD_SIGNALS = ["page not found", "404 error", "not be found", "no longer available",
               "access denied", "forbidden", "under construction", "account suspended",
               "domain is for sale", "this site can", "temporarily unavailable"]


def audit_content(county: str, page_type: str, text: str, title: str | None,
                  final_url: str, requested_url: str) -> tuple[str, str, bool]:
    """Return (confidence, reason, flag_for_review)."""
    hay = f"{title or ''}\n{text}".lower()
    url_hay = final_url.lower()
    county_l = county.lower()
    seat_l = SEATS.get(county, "").lower()

    # Identity: county name or seat, in text/title OR in the (final) domain.
    import re as _re
    county_in_text = county_l in hay
    # Normalize separators so "el paso" matches "/TX/El_Paso/" and "el-paso".
    county_squash = _re.sub(r"[\s_-]", "", county_l)
    url_squash = _re.sub(r"[\s_-]", "", url_hay)
    county_in_url = county_squash in url_squash
    seat_in_text = bool(seat_l) and seat_l in hay
    identity = county_in_text or county_in_url or (seat_in_text and page_type != "homepage")

    strong_kw, weak_kw = TYPE_KEYWORDS.get(page_type, ([], []))
    strong_hits = [k for k in strong_kw if k in hay]
    weak_hits = [k for k in weak_kw if k in hay]

    bad_hits = [b for b in BAD_SIGNALS if b in hay]

    # Deep page that redirected to the site root often means the page is gone.
    from urllib.parse import urlparse
    req_p, fin_p = urlparse(requested_url), urlparse(final_url)
    redirected_to_root = (
        req_p.path.rstrip("/") not in ("", fin_p.path.rstrip("/"))
        and fin_p.path.rstrip("/") in ("", "/")
        and len(req_p.path.rstrip("/")) > 1
    )

    idents = []
    if county_in_text:
        idents.append(f"county name '{county}' in page")
    elif county_in_url:
        idents.append(f"'{county}' in domain")
    if seat_in_text:
        idents.append(f"seat '{SEATS[county]}' in page")

    parts = []
    if idents:
        parts.append("; ".join(idents))
    if strong_hits:
        parts.append(f"{page_type} keywords: {', '.join(strong_hits[:4])}")
    elif weak_hits:
        parts.append(f"weak {page_type} keywords: {', '.join(weak_hits[:3])}")
    if title:
        parts.append(f"title=\"{title[:70]}\"")
    reason = " | ".join(parts) if parts else "no identity or topic keywords found"

    flag = False
    if bad_hits:
        confidence = "uncertain"
        reason = f"POSSIBLE ERROR PAGE ({', '.join(bad_hits[:2])}); " + reason
        flag = True
    elif redirected_to_root:
        confidence = "uncertain"
        reason = f"requested deep path redirected to site root ({final_url}); " + reason
        flag = True
    elif identity and strong_hits:
        confidence = "confident"
    elif identity and (weak_hits or page_type == "homepage"):
        confidence = "likely"
    elif identity or strong_hits:
        confidence = "uncertain"
        reason = "only partial match — " + reason
        flag = True
    else:
        confidence = "uncertain"
        flag = True

    # Very thin body (rendered app frame / mostly empty) — worth a look.
    if len(text.strip()) < 200 and not bad_hits:
        reason = f"thin content ({len(text.strip())} chars); " + reason
        if confidence == "confident":
            confidence = "likely"
        else:
            flag = True

    return confidence, reason, flag


def verify_row(row: dict, allow_headless: bool) -> dict:
    url = row["url"].strip()
    county, page_type = row["county"].strip(), row["page_type"].strip()
    if not url:
        return {"verify_status": "gap", "http_status": "", "final_url": "",
                "audit_confidence": "gap", "audit_reason": row.get("notes", ""),
                "flag_for_review": ""}

    result = snapshot.fetch_plain(url)
    render_mode = "plain"
    non_html = result["ok"] and not snapshot._is_html(result["content_type"])
    cleaned_html = (normalize.clean_html(result["html"])
                    if result["html"] and not non_html else "")
    cleaned_text = normalize.extract_text(cleaned_html) if cleaned_html else ""

    escalate = allow_headless and not non_html and (
        (not result["ok"]) or (result["ok"] and normalize.looks_like_js_shell(
            cleaned_text, cleaned_html)))
    if escalate:
        with _HEADLESS_LOCK:
            h = snapshot.fetch_headless(url)
        if h["ok"]:
            result, render_mode = h, "headless"
            cleaned_html = normalize.clean_html(result["html"])
            cleaned_text = normalize.extract_text(cleaned_html)

    status = result["http_status"]
    final_url = result["final_url"]
    title = normalize.extract_title(cleaned_html) if cleaned_html else None

    # Liveness.
    if result["error"] and not result["ok"]:
        vs = "broken"
        conf, reason, flag = "broken", f"fetch failed: {result['error'][:90]}", True
    elif non_html:
        vs = "broken"
        conf, reason, flag = "uncertain", f"non-HTML content ({result['content_type']}) — out of scope", True
    elif status is not None and status >= 400:
        vs = "broken"
        conf, reason, flag = "broken", f"HTTP {status}", True
    else:
        vs = "ok"
        conf, reason, flag = audit_content(county, page_type, cleaned_text, title,
                                            final_url, url)

    out = {
        "verify_status": vs,
        "http_status": "" if status is None else str(status),
        "final_url": final_url if final_url != url else "",
        "audit_confidence": conf,
        "audit_reason": f"[{render_mode}] {reason}",
        "flag_for_review": "yes" if flag else "",
    }
    with _LOG_LOCK:
        log.info("%-11s %-12s %-7s %-10s %s", county, page_type, vs, conf,
                 ("FLAG " if flag else "") + reason[:70])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--county", action="append", default=None)
    ap.add_argument("--no-headless", action="store_true")
    ap.add_argument("--workers", type=int, default=8,
                    help="concurrent plain fetches (headless is serialized)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    with MANIFEST.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    base_fields = ["county", "batch", "page_type", "url", "external", "notes"]
    audit_fields = ["verify_status", "http_status", "final_url",
                    "audit_confidence", "audit_reason", "flag_for_review"]

    counties = {c.lower() for c in args.county} if args.county else None
    todo = []
    for row in rows:
        for f in audit_fields:
            row.setdefault(f, "")
        if counties and row["county"].strip().lower() not in counties:
            continue  # keep any prior audit columns untouched
        todo.append(row)

    log.info("auditing %d rows with %d workers\n", len(todo), args.workers)
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(verify_row, r, not args.no_headless): r for r in todo}
        for f in cf.as_completed(futs):
            futs[f].update(f.result())

    with MANIFEST.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=base_fields + audit_fields)
        w.writeheader()
        w.writerows(rows)
    log.info("\nwrote audit columns -> %s", MANIFEST)

    _write_report(rows, audit_fields)


def _md(cell: str) -> str:
    """Escape a value for a markdown table cell."""
    return (cell or "").replace("|", "\\|").replace("\n", " ")


def _write_report(rows: list[dict], audit_fields: list[str]) -> None:
    live = [r for r in rows if r.get("verify_status") == "ok"]
    broken = [r for r in rows if r.get("verify_status") == "broken"]
    flagged = [r for r in rows if r.get("flag_for_review") == "yes"]
    gaps = [r for r in rows if r.get("verify_status") == "gap"]
    lines = ["# targets.csv audit report", "",
             f"- OK (live): {len(live)}",
             f"- Broken: {len(broken)}",
             f"- Flagged for review: {len(flagged)}",
             f"- Gaps (no URL): {len(gaps)}", ""]
    if broken:
        lines += ["## Broken", "", "| county | page_type | status | reason | url |",
                  "|---|---|---|---|---|"]
        for r in broken:
            lines.append(f"| {r['county']} | {r['page_type']} | {r['http_status']} | "
                         f"{_md(r['audit_reason'])} | {r['url']} |")
        lines.append("")
    if flagged:
        lines += ["## Flagged for review", "",
                  "| county | page_type | confidence | reason | url |",
                  "|---|---|---|---|---|"]
        for r in flagged:
            if r in broken:
                continue
            lines.append(f"| {r['county']} | {r['page_type']} | {r['audit_confidence']} | "
                         f"{_md(r['audit_reason'])} | {r['url']} |")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("wrote report -> %s", REPORT)


if __name__ == "__main__":
    main()
