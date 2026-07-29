#!/usr/bin/env python3
"""Phase 1 (Batch 2) — discover + verify official county HOMEPAGES.

Batch 2 counties arrive with only a name and a county seat; no URL is known. This
script finds the official homepage without burning a web search per county, by
exploiting the fact that Texas county sites follow a small number of domain
patterns:

    co.<county>.tx.us          (very common for rural counties)
    <county>countytx.gov
    <county>county.gov          (ambiguous — same name exists in other states)
    <county>countytx.com        (Bell County's real site is a .com)
    ...

Pipeline per county:
  1. Generate candidate URLs from those patterns.
  2. DNS-resolve first (cheap) and drop candidates whose host doesn't exist.
  3. HTTP-probe the survivors in priority order.
  4. VERIFY the content is really that county's government site in Texas:
     county name present AND (state signal OR county seat present) AND "county",
     with parked-domain / error-page / aggregator rejection.
  5. Stop at the first candidate that verifies `confident`; otherwise keep the
     best weaker match and flag it for review.

Counties that resolve nothing are reported as unresolved so they can be handled
with a targeted web search — the residual is small enough to do by hand.

Outputs:
    manifest/batch2_homepages.csv   county, seat, homepage, confidence, evidence, flag_for_review
    logs/batch2-homepage-probes.json  full probe record (every candidate tried)

Usage:
    python scripts/discover_homepages.py
    python scripts/discover_homepages.py --county Anderson --county Hays
    python scripts/discover_homepages.py --workers 8
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import json
import logging
import re
import socket
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
OUT_CSV = ROOT / "manifest" / "batch2_homepages.csv"
OUT_JSON = ROOT / "logs" / "batch2-homepage-probes.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
# A realistic, COMPLETE browser header set — not just a User-Agent. Bot protection
# fingerprints the whole request: with only UA+Accept, Imperva served Aransas
# County a 212-byte challenge stub and Cloudflare 403'd Delta County, while the
# full set below returns their real pages (33 KB and 104 KB respectively). The
# `br` encoding requires the `brotli` package (see requirements.txt), otherwise
# advertising it yields undecodable bodies.
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-Ch-Ua": '"Chromium";v="125", "Not.A/Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
}
TIMEOUT = 12.0

# (county, seat) for the 100 Batch 2 counties.
# County/seat data is NOT hardcoded here — it lives in manifest/counties.csv and is
# read via load_seed(). Use --batch to pick a batch, e.g. --batch 3.

# Domains that are never the official county government site.
BAD_HOST_SUBSTRINGS = ("facebook", "twitter", "linkedin", "yelp", "city-data",
                       "countyoffice.org", "usa.com", "areaconnect", "zillow",
                       "realtor", "netronline", "publicrecords", "wikipedia",
                       "cad.org", "appraisal")

# Signals that a page is an actual county GOVERNMENT site rather than a
# commercial page that merely mentions the county. Without this check, sites like
# "Burnet County, Texas Process Servers" pass a naive county-name + Texas test.
GOV_SIGNALS = ("commissioners court", "commissioner's court", "county judge",
               "county clerk", "district clerk", "tax assessor", "sheriff",
               "justice of the peace", "county auditor", "county treasurer",
               "courthouse", "elections administrator", "county attorney",
               "commissioners' court", "county commissioners", "precinct")

# Commercial/vendor tells that disqualify a page outright.
COMMERCIAL_SIGNALS = ("process server", "bail bond", "personal injury",
                      "attorney advertising", "real estate listings",
                      "for sale by owner", "insurance quotes", "add your business",
                      "advertise with us", "sponsored listings")

# Adjacent-but-not-government organisations that legitimately carry the county's
# name and rank well: tourism bureaus, economic development corporations, chambers,
# historical societies. libertycounty.org is Liberty County's *visitor* site and
# woodcountytx.com is the Wood County Economic Development Commission — neither is
# the county government. Weighted against GOV_SIGNALS so a real county site that
# merely links to its tourism page isn't rejected.
NON_GOV_ORG_SIGNALS = ("visitor center", "visitors bureau", "things to do",
                       "where to stay", "places to eat", "itineraries",
                       "economic development commission",
                       "economic development corporation",
                       "chamber of commerce", "convention and visitors",
                       "historical society", "genealogical society",
                       "plan your visit", "tourism")

# Non-government organisations that name themselves in the page TITLE. Seeing one
# of these there is disqualifying on its own.
NON_GOV_ORG_TITLE_MARKERS = ("economic development", "chamber of commerce",
                             "visitors bureau", "visitor center", "tourism",
                             "convention and visitors", "historical society",
                             "genealogical society", "appraisal district")

PARKED_SIGNALS = ("domain is for sale", "buy this domain", "parked",
                  "this domain may be for sale", "godaddy", "sedo",
                  "account suspended", "coming soon", "under construction",
                  "default web site page", "index of /")
ERROR_SIGNALS = ("page not found", "404 not found", "403 forbidden",
                 "access denied", "not be found", "site can't be reached")

log = logging.getLogger("discover_homepages")

SEED = ROOT / "manifest" / "counties.csv"


def load_seed(batch: str | None = None) -> list[tuple[str, str]]:
    """(county, seat) pairs from manifest/counties.csv — the single source of truth.

    Nothing in this module hardcodes a county list; adding or fixing a county is a
    manifest edit.
    """
    with SEED.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [(r["county"].strip(), r["seat"].strip()) for r in rows
            if batch is None or r["batch"].strip() == str(batch)]


def _all_county_names() -> set[str]:
    with SEED.open(newline="", encoding="utf-8") as fh:
        return {r["county"].strip().lower() for r in csv.DictReader(fh)}


_COUNTY_NAMES_CACHE: set[str] | None = None


def _other_county_names(county: str) -> set[str]:
    """Every Texas county name except this one, for cross-identification checks."""
    global _COUNTY_NAMES_CACHE
    if _COUNTY_NAMES_CACHE is None:
        _COUNTY_NAMES_CACHE = _all_county_names()
    return _COUNTY_NAMES_CACHE - {county.strip().lower()}


def slugs(county: str) -> tuple[str, str]:
    """('deafsmith', 'deaf-smith') for 'Deaf Smith'."""
    low = county.lower()
    squashed = re.sub(r"[^a-z0-9]", "", low)
    hyphen = re.sub(r"[^a-z0-9]+", "-", low).strip("-")
    return squashed, hyphen


def candidates(county: str) -> list[str]:
    s, h = slugs(county)
    urls = [
        f"https://www.co.{s}.tx.us/",
        f"https://co.{s}.tx.us/",
        f"https://www.{s}countytx.gov/",
        f"https://{s}countytx.gov/",
        f"https://www.{s}county.gov/",
        f"https://{s}county.gov/",
        f"https://www.{s}countytexas.gov/",
        # Short .gov form without "county" (Polk County uses polktx.gov)
        f"https://www.{s}tx.gov/",
        f"https://{s}tx.gov/",
        # Newer state-hosted pattern, e.g. hoodcounty.texas.gov, foardcounty.texas.gov
        f"https://{s}county.texas.gov/",
        f"https://www.{s}county.texas.gov/",
        f"https://www.{s}countytx.com/",
        f"https://www.{s}county.org/",
        f"https://www.{s}countytx.org/",
    ]
    if h != s:  # multi-word counties also use a hyphenated co.*.tx.us host
        urls.insert(2, f"https://www.co.{h}.tx.us/")
        urls.insert(3, f"https://co.{h}.tx.us/")
    return urls


def host_resolves(url: str) -> bool:
    host = httpx.URL(url).host
    if any(b in host for b in BAD_HOST_SUBSTRINGS):
        return False
    try:
        socket.getaddrinfo(host, None)
        return True
    except socket.gaierror:
        return False


def visible_text(html: str) -> tuple[str, str | None]:
    soup = BeautifulSoup(html or "", "lxml")
    for t in soup.find_all(["script", "style", "noscript", "svg"]):
        t.decompose()
    title = None
    if soup.title and soup.title.string:
        title = " ".join(soup.title.string.split())
    text = " ".join(soup.get_text(separator=" ").split())
    return text, title


def verify(county: str, seat: str, url: str, text: str, title: str | None
           ) -> tuple[str, str]:
    """Return (confidence, evidence). confidence: confident|likely|reject.

    Identity is established by the literal phrase "<county> county", NOT by the
    county name and the word "county" appearing separately. That distinction
    matters because 12 Texas counties share a name with a *different* county's
    seat, so loose matching produces confident-looking false positives:

        Houston County (seat Crockett)  vs  the City of Houston / Harris County
        Tyler County   (seat Woodville) vs  the City of Tyler / Smith County
        Jefferson County (seat Beaumont) vs the City of Jefferson / Marion County

    Harris County's site says "Harris County", never "Houston County", so
    requiring the exact phrase rejects it. We additionally reject pages that
    identify themselves as some *other* county.
    """
    hay = f"{title or ''} {text}".lower()
    county_l = county.lower()
    seat_l = seat.lower()
    host = httpx.URL(url).host

    if any(sig in hay[:4000] for sig in PARKED_SIGNALS):
        return "reject", "parked/placeholder domain"
    if any(sig in hay[:2000] for sig in ERROR_SIGNALS):
        return "reject", "error page"
    if len(text.strip()) < 120:
        return "reject", f"near-empty page ({len(text.strip())} chars)"

    # Self-identification: the page must say "<county> county" (or "county of
    # <county>"), not merely contain the name and the word separately.
    esc = re.escape(county_l)
    has_county_name = bool(re.search(rf"\b{esc}\b\s*'?s?\s+county\b", hay)) or \
        bool(re.search(rf"\bcounty\s+of\s+{esc}\b", hay))
    has_word_county = "county" in hay
    has_state = ("texas" in hay) or bool(re.search(r"\btx\b", hay))
    has_seat = bool(re.search(rf"\b{re.escape(seat_l)}\b", hay))

    # Does the TITLE identify a DIFFERENT county? Use same-line matching only
    # ([ \t]+ not \s+): across newlines a nav list would join "Brown" and
    # "County Clerk" into a phantom "Brown County".
    title_l = (title or "").lower()
    # Nested county names need care in BOTH directions, because "Deaf Smith
    # County" contains the literal string "Smith County":
    #   - looking for Deaf Smith, ignore "Smith" (it's part of our own name)
    #   - looking for Smith, a title saying "Deaf Smith County" is NOT us
    others_in_title = [
        o for o in _other_county_names(county)
        if o not in county_l                       # not a fragment of our own name
        and re.search(rf"\b{re.escape(o)}\b[ \t]+county\b", title_l)
    ]
    longer_match = [o for o in _other_county_names(county)
                    if county_l in o
                    and re.search(rf"\b{re.escape(o)}\b[ \t]+county\b", title_l)]
    if longer_match:
        others_in_title = longer_match
    # Domain itself is a strong signal for the official *.tx.us / *.gov patterns.
    official_tld = host.endswith(".tx.us") or host.endswith(".gov")

    gov_hits = [g for g in GOV_SIGNALS if g in hay]
    commercial_hits = [c for c in COMMERCIAL_SIGNALS if c in hay]

    ev = []
    if has_county_name:
        ev.append(f"'{county}' in page")
    if has_seat:
        ev.append(f"seat '{seat}' in page")
    if has_state:
        ev.append("Texas/TX present")
    if official_tld:
        ev.append(f"official TLD ({host.split('.')[-2]}.{host.split('.')[-1]})")
    if gov_hits:
        ev.append(f"gov signals: {', '.join(gov_hits[:3])}")
    evidence = "; ".join(ev) if ev else "no signals"

    # Commercial page that merely mentions the county (process servers, lead-gen
    # directories). Only reject when the government signals are ALSO weak: real
    # county sites legitimately mention e.g. bail bonds on sheriff/jail pages, so
    # a commercial phrase alone must not disqualify them.
    if commercial_hits and len(gov_hits) < 2:
        return "reject", f"commercial site ({commercial_hits[0]}) — {evidence}"
    # Tourism bureau / EDC / chamber carrying the county's name. Only reject when
    # the government vocabulary is weaker than the non-government vocabulary, so a
    # real county site that links to "things to do" survives.
    nongov_hits = [n for n in NON_GOV_ORG_SIGNALS if n in hay]
    # A non-government organisation names itself in its TITLE ("Wood County
    # Economic Development Commission"), so that alone is disqualifying.
    title_org = [n for n in NON_GOV_ORG_TITLE_MARKERS if n in title_l]
    # Otherwise require a genuine cluster of tourism vocabulary. A real county site
    # often carries a single "chamber of commerce" nav link — Martin County's
    # sparse CivicPlus homepage has exactly one and is legitimate.
    if title_org or (len(nongov_hits) >= 3 and len(nongov_hits) > len(gov_hits)):
        why = (title_org or nongov_hits)[:2]
        return "reject", (f"not the county government — looks like a tourism/EDC/chamber "
                          f"site ({', '.join(why)}) — {evidence}")
    # Must look like a county government page at all.
    if not (has_county_name and has_word_county):
        return "reject", f"page does not identify as '{county} County' — {evidence}"
    # The page's own TITLE naming a different county means we landed on the wrong
    # site. Scoped to the title on purpose: Texas counties are named after people
    # (Brown, Smith, Young, Houston), so surnames in body text — "Ann Brown,
    # County Clerk" — would otherwise trigger bogus rejections.
    if others_in_title:
        return "reject", (f"title identifies another county "
                          f"({', '.join(sorted(others_in_title)[:2])}) — {evidence}")
    # Must be locatable in Texas (guards Anderson County SC/TN style collisions).
    if not (has_state or has_seat):
        return "reject", f"no Texas/seat signal (possible wrong-state county) — {evidence}"

    # Government corroboration. A restricted TLD (.gov / .tx.us) cannot be
    # registered commercially, so the TLD itself is sufficient proof. Open TLDs
    # need at least one signal; with none we keep the county but flag it rather
    # than silently dropping a real site — El Paso's epcounty.com homepage is a
    # bare CMS shell whose text contains no government vocabulary at all.
    if official_tld:
        return "confident", evidence
    if len(gov_hits) >= 2 and has_state and has_seat:
        return "confident", evidence
    if gov_hits:
        return "likely", evidence
    return "likely", f"no government vocabulary on page — verify manually; {evidence}"


def probe(url: str) -> dict:
    try:
        with httpx.Client(headers=HEADERS, follow_redirects=True,
                          timeout=TIMEOUT, verify=True) as c:
            r = c.get(url)
        text, title = visible_text(r.text)
        return {"url": url, "ok": True, "status": r.status_code,
                "final_url": str(r.url), "title": title, "text": text,
                "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "ok": False, "status": None, "final_url": url,
                "title": None, "text": "", "error": f"{type(exc).__name__}"}


def resolve_county(county: str, seat: str) -> dict:
    attempts = []
    best = None
    for url in candidates(county):
        if not host_resolves(url):
            attempts.append({"url": url, "result": "dns_fail"})
            continue
        p = probe(url)
        if not p["ok"]:
            attempts.append({"url": url, "result": f"fetch_fail:{p['error']}"})
            continue
        if p["status"] >= 400:
            attempts.append({"url": url, "result": f"http_{p['status']}"})
            continue
        conf, ev = verify(county, seat, p["final_url"], p["text"], p["title"])
        attempts.append({"url": url, "result": conf, "status": p["status"],
                         "final_url": p["final_url"], "title": p["title"],
                         "evidence": ev})
        if conf == "confident":
            best = {"homepage": p["final_url"], "confidence": "confident",
                    "evidence": ev, "title": p["title"]}
            break
        if conf == "likely" and best is None:
            best = {"homepage": p["final_url"], "confidence": "likely",
                    "evidence": ev, "title": p["title"]}
    if best is None:
        best = {"homepage": "", "confidence": "unresolved",
                "evidence": "no candidate pattern verified — needs web search",
                "title": None}
    out = {"county": county, "seat": seat, **best, "attempts": attempts}
    log.info("%-14s %-10s %s", county, best["confidence"],
             best["homepage"] or best["evidence"][:60])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--county", action="append", default=None)
    ap.add_argument("--batch", default=None,
                    help="restrict to a batch from manifest/counties.csv (e.g. 3)")
    ap.add_argument("--out", default=None,
                    help="output CSV path (defaults to manifest/batch<N>_homepages.csv)")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    global OUT_CSV, OUT_JSON
    if args.out:
        OUT_CSV = Path(args.out)
        # Keep the probe log beside the chosen output so an ad-hoc run can't
        # clobber another batch's record.
        OUT_JSON = OUT_CSV.with_name(OUT_CSV.stem + "-probes.json")
    elif args.batch:
        OUT_CSV = ROOT / "manifest" / f"batch{args.batch}_homepages.csv"
        OUT_JSON = ROOT / "logs" / f"batch{args.batch}-homepage-probes.json"

    counties = load_seed(args.batch)
    if args.county:
        want = {c.lower() for c in args.county}
        counties = [(c, s) for c, s in counties if c.lower() in want]
    if not counties:
        sys.exit("no counties selected — check --batch / --county")

    results: list[dict] = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(resolve_county, c, s): c for c, s in counties}
        for f in cf.as_completed(futs):
            results.append(f.result())

    order = {c: i for i, (c, _s) in enumerate(counties)}
    results.sort(key=lambda r: order[r["county"]])

    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["county", "seat", "homepage",
                                           "confidence", "evidence",
                                           "flag_for_review"])
        w.writeheader()
        for r in results:
            w.writerow({"county": r["county"], "seat": r["seat"],
                        "homepage": r["homepage"],
                        "confidence": r["confidence"],
                        "evidence": r["evidence"],
                        "flag_for_review": "yes" if r["confidence"] != "confident" else ""})

    from collections import Counter
    tally = Counter(r["confidence"] for r in results)
    log.info("\n%s", dict(tally))
    log.info("wrote %s and %s", OUT_CSV, OUT_JSON)


if __name__ == "__main__":
    main()
