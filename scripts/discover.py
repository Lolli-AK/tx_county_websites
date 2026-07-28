#!/usr/bin/env python3
"""tx-county-watch — Phase 1 discovery helper.

For each county homepage, fetch the page, collect every link, and score links
against per-page-type keyword patterns to SUGGEST candidate URLs for:
    elections, polling, early_voting, results

This does NOT write the final manifest. It emits a candidates report
(logs/discover-candidates.json) that a human reviews to hand-build
manifest/targets.csv. Discovery of real county sites is messy — vendor portals,
JS menus, inconsistent naming — so treat output as leads, not gospel.

Usage:
    python scripts/discover.py                 # all seed counties
    python scripts/discover.py --county harris # one county
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# Seed homepages (verified). Keep in sync with the build spec's county table.
SEED = {
    "Harris": "https://www.harriscountytx.gov/",
    "Dallas": "https://www.dallascounty.org/",
    "Tarrant": "https://tarrantcountytx.gov/",
    "Bexar": "https://www.bexar.org/",
    "Travis": "https://www.traviscountytx.gov/",
    "Collin": "https://www.collincountytx.gov/",
    "El Paso": "https://www.epcounty.com/",
    "Hidalgo": "https://www.hidalgocounty.us/",
    "Williamson": "https://www.wilcotx.gov/",
    "Webb": "https://www.webbcountytx.gov/",
    "Lubbock": "https://www.lubbockcounty.gov/",
    "Bell": "https://www.bellcountytx.com/",
    "Galveston": "https://www.galvestoncountytx.gov/",
    "Kerr": "https://kerrcountytx.gov/",
    "Gillespie": "https://www.gillespiecounty.gov/",
    "Medina": "https://www.medinatx.gov/",
    "Llano": "https://www.co.llano.tx.us/",
    "Brewster": "https://www.brewstercounty.gov/",
    "Presidio": "https://www.co.presidio.tx.us/",
    "Hartley": "https://www.co.hartley.tx.us/",
    "Roberts": "https://www.co.roberts.tx.us/",
    "Loving": "https://www.co.loving.tx.us/",
    "King": "https://www.co.king.tx.us/",
    "Kenedy": "https://www.kenedycountytx.gov/",
}

# Keyword patterns per page type. Higher-weight terms are more specific.
PATTERNS = {
    "early_voting": [("early voting", 5), ("early vote", 5), ("advance voting", 4)],
    "polling": [("polling", 5), ("vote center", 5), ("voting center", 5),
                ("polling location", 6), ("where to vote", 5), ("poll location", 5)],
    "results": [("election result", 6), ("results", 4), ("returns", 3),
                ("canvass", 3), ("enr", 2)],
    "elections": [("election", 4), ("elections", 4), ("voter", 4),
                  ("voting", 3), ("ballot", 3), ("register to vote", 4),
                  ("voter registration", 4)],
}

log = logging.getLogger("discover")


def fetch(url: str) -> tuple[str, str] | None:
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT},
                          follow_redirects=True, timeout=30.0) as client:
            resp = client.get(url)
        return resp.text, str(resp.url)
    except Exception as exc:  # noqa: BLE001
        log.warning("fetch failed for %s: %s", url, exc)
        return None


def collect_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """Return (anchor_text, absolute_url) for every link on the page."""
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        abs_url = urljoin(base_url, href)
        if not abs_url.startswith("http"):
            continue
        text = " ".join(a.get_text(separator=" ").split())
        out.append((text, abs_url))
    return out


def score_link(text: str, url: str, patterns: list[tuple[str, int]]) -> int:
    hay = f"{text} {url}".lower()
    return sum(weight for kw, weight in patterns if kw in hay)


def suggest(home_url: str, links: list[tuple[str, str]]) -> dict:
    home_host = urlparse(home_url).netloc
    suggestions = {}
    for ptype, patterns in PATTERNS.items():
        scored = []
        for text, url in links:
            s = score_link(text, url, patterns)
            if s > 0:
                external = urlparse(url).netloc != home_host
                scored.append({"score": s, "text": text[:80], "url": url,
                               "external": external})
        # Dedup by url, keep highest score, sort desc, keep top 6.
        best: dict[str, dict] = {}
        for item in scored:
            if item["url"] not in best or item["score"] > best[item["url"]]["score"]:
                best[item["url"]] = item
        ranked = sorted(best.values(), key=lambda x: (-x["score"], x["url"]))
        suggestions[ptype] = ranked[:6]
    return suggestions


def main() -> None:
    ap = argparse.ArgumentParser(description="Discover candidate election URLs.")
    ap.add_argument("--county", action="append", default=None,
                    help="limit to county (repeatable)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])
    LOGS.mkdir(exist_ok=True)

    counties = SEED
    if args.county:
        want = {c.lower() for c in args.county}
        counties = {k: v for k, v in SEED.items() if k.lower() in want}

    report = {}
    for county, home in counties.items():
        log.info("discovering %s -> %s", county, home)
        fetched = fetch(home)
        if not fetched:
            report[county] = {"homepage": home, "error": "fetch_failed"}
            continue
        html, final = fetched
        links = collect_links(html, final)
        report[county] = {
            "homepage": home,
            "final_url": final,
            "n_links": len(links),
            "suggestions": suggest(final, links),
        }

    out_path = LOGS / "discover-candidates.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    log.info("wrote %s", out_path)


if __name__ == "__main__":
    main()
