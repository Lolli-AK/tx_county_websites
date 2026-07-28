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
HEADERS = {"User-Agent": USER_AGENT,
           "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "en-US,en;q=0.9"}
TIMEOUT = 12.0

# (county, seat) for the 100 Batch 2 counties.
BATCH2 = [
    ("Anderson", "Palestine"), ("Andrews", "Andrews"), ("Angelina", "Lufkin"),
    ("Aransas", "Rockport"), ("Archer", "Archer City"), ("Armstrong", "Claude"),
    ("Atascosa", "Jourdanton"), ("Austin", "Bellville"), ("Bailey", "Muleshoe"),
    ("Bandera", "Bandera"), ("Bastrop", "Bastrop"), ("Baylor", "Seymour"),
    ("Bee", "Beeville"), ("Blanco", "Johnson City"), ("Borden", "Gail"),
    ("Bosque", "Meridian"), ("Bowie", "Boston"), ("Brazoria", "Angleton"),
    ("Brazos", "Bryan"), ("Briscoe", "Silverton"), ("Brooks", "Falfurrias"),
    ("Brown", "Brownwood"), ("Burleson", "Caldwell"), ("Burnet", "Burnet"),
    ("Caldwell", "Lockhart"), ("Calhoun", "Port Lavaca"), ("Callahan", "Baird"),
    ("Cameron", "Brownsville"), ("Camp", "Pittsburg"), ("Carson", "Panhandle"),
    ("Cass", "Linden"), ("Castro", "Dimmitt"), ("Chambers", "Anahuac"),
    ("Cherokee", "Rusk"), ("Childress", "Childress"), ("Clay", "Henrietta"),
    ("Cochran", "Morton"), ("Coke", "Robert Lee"), ("Coleman", "Coleman"),
    ("Collingsworth", "Wellington"), ("Colorado", "Columbus"),
    ("Comal", "New Braunfels"), ("Comanche", "Comanche"), ("Concho", "Paint Rock"),
    ("Cooke", "Gainesville"), ("Coryell", "Gatesville"), ("Cottle", "Paducah"),
    ("Crane", "Crane"), ("Crockett", "Ozona"), ("Crosby", "Crosbyton"),
    ("Culberson", "Van Horn"), ("Dallam", "Dalhart"), ("Dawson", "Lamesa"),
    ("Deaf Smith", "Hereford"), ("Delta", "Cooper"), ("Denton", "Denton"),
    ("DeWitt", "Cuero"), ("Dickens", "Dickens"), ("Dimmit", "Carrizo Springs"),
    ("Donley", "Clarendon"), ("Duval", "San Diego"), ("Eastland", "Eastland"),
    ("Ector", "Odessa"), ("Edwards", "Rocksprings"), ("Ellis", "Waxahachie"),
    ("Erath", "Stephenville"), ("Falls", "Marlin"), ("Fannin", "Bonham"),
    ("Fayette", "La Grange"), ("Fisher", "Roby"), ("Floyd", "Floydada"),
    ("Foard", "Crowell"), ("Fort Bend", "Richmond"), ("Franklin", "Mount Vernon"),
    ("Freestone", "Fairfield"), ("Frio", "Pearsall"), ("Gaines", "Seminole"),
    ("Garza", "Post"), ("Glasscock", "Garden City"), ("Goliad", "Goliad"),
    ("Gonzales", "Gonzales"), ("Gray", "Pampa"), ("Grayson", "Sherman"),
    ("Gregg", "Longview"), ("Grimes", "Anderson"), ("Guadalupe", "Seguin"),
    ("Hale", "Plainview"), ("Hall", "Memphis"), ("Hamilton", "Hamilton"),
    ("Hansford", "Spearman"), ("Hardeman", "Quanah"), ("Hardin", "Kountze"),
    ("Harrison", "Marshall"), ("Haskell", "Haskell"), ("Hays", "San Marcos"),
    ("Hemphill", "Canadian"), ("Henderson", "Athens"), ("Hill", "Hillsboro"),
    ("Hockley", "Levelland"), ("Hood", "Granbury"),
]

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

PARKED_SIGNALS = ("domain is for sale", "buy this domain", "parked",
                  "this domain may be for sale", "godaddy", "sedo",
                  "account suspended", "coming soon", "under construction",
                  "default web site page", "index of /")
ERROR_SIGNALS = ("page not found", "404 not found", "403 forbidden",
                 "access denied", "not be found", "site can't be reached")

log = logging.getLogger("discover_homepages")


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
    """Return (confidence, evidence). confidence: confident|likely|reject."""
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

    has_county_name = county_l in hay
    has_word_county = "county" in hay
    has_state = ("texas" in hay) or bool(re.search(r"\btx\b", hay))
    has_seat = seat_l in hay
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
    # Must look like a county government page at all.
    if not (has_county_name and has_word_county):
        return "reject", f"not a county-name match — {evidence}"
    # Must be locatable in Texas (guards Anderson County SC/TN style collisions).
    if not (has_state or has_seat):
        return "reject", f"no Texas/seat signal (possible wrong-state county) — {evidence}"

    # Must actually look like a GOVERNMENT site. Restricted TLDs (.gov/.tx.us)
    # can't be registered commercially, so one signal is enough there; open TLDs
    # (.com/.org/.net) must show at least two.
    need = 1 if official_tld else 2
    if len(gov_hits) < need:
        return "reject", (f"insufficient county-government signals "
                          f"({len(gov_hits)}<{need}) — {evidence}")

    if official_tld and (has_seat or has_state):
        return "confident", evidence
    if has_seat and has_state and len(gov_hits) >= 2:
        return "confident", evidence
    return "likely", evidence


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
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    counties = BATCH2
    if args.county:
        want = {c.lower() for c in args.county}
        counties = [(c, s) for c, s in BATCH2 if c.lower() in want]

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
