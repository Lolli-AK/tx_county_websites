#!/usr/bin/env python3
"""Phase 1 (Batch 2) — discover the four election page types per county.

Runs a TWO-LEVEL crawl, because on real county sites the homepage usually links
only to an "Elections" landing page, and the polling / early-voting / results
links live one level deeper on that landing page:

    homepage  --score-->  elections landing
    elections landing (+ homepage)  --score-->  polling / early_voting / results

Candidates are keyword-scored, PDF links are skipped (out of scope), and each
pick is confirmed with a real fetch before being written.

Consistent with how Batch 1 was curated, a page type whose best candidate is just
the elections page again is recorded as a GAP ("folded into elections page")
rather than duplicating the same URL across rows — a missing distinct page is
expected data, not an error.

Input:  manifest/batch2_homepages.csv   (from discover_homepages.py)
Output: manifest/batch2_targets_draft.csv  county,batch,page_type,url,external,notes

Usage:
    python scripts/discover_pages.py
    python scripts/discover_pages.py --county Hays --workers 6
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import logging
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
IN_CSV = ROOT / "manifest" / "batch2_homepages.csv"
OUT_CSV = ROOT / "manifest" / "batch2_targets_draft.csv"

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
TIMEOUT = 15.0

# Scoring patterns. (keyword, weight) — negative weights push candidates away.
PATTERNS: dict[str, list[tuple[str, int]]] = {
    "elections": [
        ("election", 6), ("elections", 6), ("voter", 5), ("voting", 5),
        ("ballot", 3), ("vote", 3), ("elections administrator", 8),
        ("elections office", 8), ("voter registration", 5),
        ("candidate", -3), ("archive", -4), ("result", -3), ("history", -3),
        # A registration *form/application* is not the elections landing page.
        ("application", -9), ("registration application", -6), ("form", -5),
    ],
    "polling": [
        ("polling location", 12), ("polling place", 12), ("vote center", 10),
        ("voting center", 10), ("polling", 9), ("election day location", 11),
        ("election day vote", 10), ("where to vote", 9), ("precinct map", 5),
        ("early", -6), ("result", -6),
    ],
    "early_voting": [
        ("early voting location", 13), ("early voting schedule", 12),
        ("early voting", 11), ("early vote", 10), ("advance voting", 8),
        ("result", -6), ("election day", -4),
    ],
    "results": [
        ("election result", 13), ("election returns", 11),
        ("unofficial result", 12), ("results", 8), ("returns", 6),
        ("canvass", 6), ("election night", 10),
        ("search result", -12), ("polling", -6), ("early", -5),
    ],
}

# Link text/urls that are navigation chrome, never a target page.
SKIP_LINK_HINTS = ("javascript:", "mailto:", "tel:", "#", "/search", "search.results",
                   "/login", "/rss", "facebook.com", "twitter.com", "youtube.com",
                   "instagram.com", "linkedin.com", "x.com/", "t.co/", "nextdoor.com",
                   "civicplus.com", "governmentjobs.com", "/myaccount", "/sitemap",
                   "/privacy", "/copyright", "/accessibility", "quicklinks.aspx")

# "Hub" pages that hold the current election's details. On CivicPlus-style county
# sites (very common in Texas) there is no standing "Polling Locations" page —
# election-day sites and early-voting schedules live inside a per-election page
# such as "Current Elections" or "November 3, 2026 General Election". We crawl
# these as a third level so those targets are actually found.
# Intermediate nav pages to fall back through when a homepage doesn't link
# elections directly (e.g. Erath County buries it under "Departments").
DEPT_PATTERNS = [
    ("county offices", 9), ("department", 8), ("government", 7),
    ("elected official", 6), ("directory", 5), ("services", 4),
    ("county clerk", 5), ("offices", 5),
]

HUB_PATTERNS = [
    ("current election", 12), ("upcoming election", 11), ("election information", 9),
    ("general election", 8), ("primary election", 7), ("joint election", 7),
    ("election day information", 10), ("next election", 8),
    ("archive", -8), ("past", -8), ("result", -4), ("financial", -10),
]

# Generic statewide portals. These are real sites, but they are STATE-level and
# identical for every county — capturing them 100 times would add no per-county
# signal and would misrepresent a county as having a results/EV page when it does
# not. They are rejected as candidates outright; if a page type has nothing but
# these, it is recorded as a gap instead.
# (County-specific external domains like votedenton.gov / harrisvotes.com are NOT
# in here and remain valid picks.)
GENERIC_PORTAL_HINTS = (
    # Statewide (Texas SOS and friends)
    "texas-election.com", "texas-elections.com", "votetexas.gov",
    "sos.state.tx.us", "sos.texas.gov", "wrm.capitol.texas.gov",
    "webservices.sos.state.tx.us", "votetexas.org", "dps.texas.gov",
    # National third-party voter-info sites. These are especially important to
    # exclude because several have "vote" in the domain and would otherwise be
    # promoted as a county's "dedicated elections portal" (vote411.org is the
    # League of Women Voters, not a county).
    "vote411.org", "lwv.org", "vote.org", "ballotpedia.org", "rockthevote",
    "usa.gov", "eac.gov", "votesmart.org", "nass.org", "turbovote",
    "headcount.org", "when-we-all-vote", "voteamerica",
    "usvotefoundation.org", "overseasvotefoundation.org", "fairelectionscenter.org",
    "fvap.gov",
    # Voting-system VENDOR marketing sites. County elections pages routinely link
    # to "how to use this machine" videos, and those pages are stuffed with
    # election vocabulary, so they outscore the real county page.
    "essvote.com", "hartintercivic.com", "dominionvoting.com", "clearballot.com",
    "unisynvoting.com", "verifiedvoting.org", "esands.com",
    # Shared statewide vendor apps whose URL carries no county identifier, so the
    # exact same page would be captured for dozens of counties (Texas IVIS).
    "civixapps.com", "txelections.civixapps.com",
    # Session-ID mapping viewer: the URL embeds a volatile SessID, so it could
    # never produce a stable, diffable snapshot.
    "logis-us.net",
    # Translation proxies. Never a valid target in themselves, AND they launder
    # every other entry in this list: Live Oak's elections link pointed at
    # "www-vote411-org.translate.goog", i.e. vote411.org with dots swapped for
    # dashes, which slipped straight past a plain substring check.
    "translate.goog", "translate.google.com",
)

log = logging.getLogger("discover_pages")

# Set from --batch so emitted rows carry the right label.
BATCH_LABEL = "2"


def is_generic_portal(url: str) -> bool:
    """True if the URL is a statewide/national/vendor portal, not a county page.

    Also catches translation-proxy laundering: Google Translate rewrites a host's
    dots to dashes ("www-vote411-org.translate.goog"), so we test the de-dashed
    form of the host as well.
    """
    low = url.lower()
    if any(g in low for g in GENERIC_PORTAL_HINTS):
        return True
    host = urlparse(low).netloc
    dedashed = host.replace("-", ".")
    return any(g in dedashed for g in GENERIC_PORTAL_HINTS)


def _fetch_plain(url: str) -> dict:
    """Plain fetch, trying HTTP/2 then HTTP/1.1 (neither works everywhere)."""
    last = None
    for http2 in (True, False):
        try:
            with httpx.Client(headers=HEADERS, follow_redirects=True,
                              timeout=TIMEOUT, http2=http2) as c:
                r = c.get(url)
            last = {"ok": True, "status": r.status_code, "html": r.text,
                    "final_url": str(r.url),
                    "ctype": r.headers.get("content-type", ""), "error": None}
            if r.status_code < 400:
                return last
        except Exception as exc:  # noqa: BLE001
            last = {"ok": False, "status": None, "html": "", "final_url": url,
                    "ctype": "", "error": type(exc).__name__}
    return last


# Discovery has to clear the same two hurdles the snapshot pipeline does: some
# county sites 403 non-browser clients (Brazoria/Delta/Henderson sit behind
# Akamai/Cloudflare), and others build their whole nav menu in JavaScript, so a
# plain fetch yields a page with no links to score. Escalate to Chromium in both
# cases, otherwise those counties silently look like they have no election pages.
_ANCHOR_RE = re.compile(r"<a\s[^>]*href=", re.I)


def fetch(url: str, allow_headless: bool = True) -> dict:
    r = _fetch_plain(url)
    needs_headless = (
        not r["ok"]
        or (r["status"] or 0) >= 400
        or ("html" in r["ctype"].lower() and len(_ANCHOR_RE.findall(r["html"])) < 5)
    )
    if allow_headless and needs_headless:
        try:
            import snapshot  # local module; imports playwright lazily
            h = snapshot.fetch_headless(url)
            status = h.get("http_status")
            if h["ok"] and (status or 200) < 400 and h["html"]:
                return {"ok": True, "status": status or 200, "html": h["html"],
                        "final_url": h["final_url"],
                        "ctype": h.get("content_type") or "text/html",
                        "error": None, "headless": True}
        except Exception:  # noqa: BLE001 - keep the plain result on any failure
            pass
    return r


def links_of(html: str, base: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html or "", "lxml")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        low = href.lower()
        if not href or any(h in low for h in SKIP_LINK_HINTS):
            continue
        if low.endswith(".pdf"):  # PDFs are out of scope
            continue
        absu = urljoin(base, href)
        if not absu.startswith("http"):
            continue
        # Statewide portals are never a valid per-county target.
        if any(g in absu.lower() for g in GENERIC_PORTAL_HINTS):
            continue
        text = " ".join(a.get_text(separator=" ").split())
        out.append((text, absu))
    return out


# Link labels that are unambiguously the elections landing page. An exact label
# match beats a longer, noisier link that happens to stack keywords (e.g.
# "Voter Registration Application" outscoring a plain "Elections" link).
EXACT_ELECTION_LABELS = {
    "elections", "election", "elections & voting", "voting & elections",
    "elections and voting", "voting and elections", "election information",
    "elections department", "elections administration", "elections office",
    "voter information", "elections & voter registration", "voting information",
    "elections/voter registration", "vote", "voting",
}


def score(text: str, url: str, pats: list[tuple[str, int]]) -> int:
    # Weight anchor text higher than the URL path; URLs often contain generic words.
    t, u = text.lower(), url.lower()
    s = 0
    for kw, w in pats:
        if kw in t:
            s += w
        elif kw in u.replace("-", " ").replace("_", " ").replace("/", " "):
            s += max(1, w // 2) if w > 0 else w
    if pats is PATTERNS["elections"]:
        if t.strip() in EXACT_ELECTION_LABELS:
            s += 8
        # A dedicated elections portal domain is the strongest signal there is.
        # Many Texas counties run elections on their own host, and the link text
        # can be as weak as "Vote Denton": votedenton.gov, harrisvotes.com,
        # dallascountyvotes.org, elections.brazoscountytx.gov, votetravis.gov.
        # (Statewide portals like votetexas.gov are already filtered out.)
        host = urlparse(url).netloc.lower().removeprefix("www.")
        label = host.split(".")[0]
        if "vote" in label or label == "elections":
            s += 12
    return s


def rank_links(links: list[tuple[str, str]], pats: list[tuple[str, int]],
               exclude: set[str], home: str | None = None,
               prefer_internal: bool = False) -> list[tuple[int, str, str]]:
    """Score and rank links. Dedups by URL keeping the best score."""
    best: dict[str, tuple[int, str, str]] = {}
    for text, url in links:
        if url.rstrip("/") in exclude:
            continue
        s = score(text, url, pats)
        if s <= 0:
            continue
        # Mild tie-break toward county-hosted pages. Kept small on purpose: many
        # counties legitimately run elections on their own separate domain
        # (votedenton.gov, harrisvotes.com), so external must not be disqualifying.
        if prefer_internal and home and is_external(url, home):
            s -= 2
        if s <= 0:
            continue
        prev = best.get(url.rstrip("/"))
        if prev is None or s > prev[0]:
            best[url.rstrip("/")] = (s, url, text)
    return sorted(best.values(), key=lambda x: (-x[0], len(x[1])))


def best_link(links: list[tuple[str, str]], ptype: str, exclude: set[str],
              home: str | None = None) -> tuple[str, int, str] | None:
    prefer_internal = ptype in ("elections", "polling", "early_voting")
    ranked = rank_links(links, PATTERNS[ptype], exclude, home, prefer_internal)
    if not ranked:
        return None
    s, url, text = ranked[0]
    return url, s, text


def is_external(url: str, home: str) -> bool:
    def reg(h: str) -> str:
        parts = urlparse(h).netloc.lower().split(".")
        return ".".join(parts[-3:]) if h.endswith(".tx.us") else ".".join(parts[-2:])
    return reg(url) != reg(home)


# Minimum score to accept a pick without flagging it as weak.
MIN_STRONG = {"elections": 6, "polling": 9, "early_voting": 10, "results": 8}


def _try_candidates(links: list[tuple[str, str]], exclude: set[str], home: str
                    ) -> tuple[str, str, list[str]]:
    """Walk the ranked elections candidates until one actually validates.

    Returns (url, note, tried). Trying several instead of only the best one
    matters because county sites carry stale links — Guadalupe's own homepage
    points at a 404 — and stopping at the first failure loses the whole county.
    """
    tried: list[str] = []
    for s, url, text in rank_links(links, PATTERNS["elections"], exclude,
                                   home, prefer_internal=True)[:4]:
        r = fetch(url)
        if not r["ok"] or (r["status"] or 0) >= 400 or "html" not in r["ctype"].lower():
            tried.append(f"{url.rstrip('/').split('/')[-1] or url} -> "
                         f"{r['status'] or r['error']}")
            continue
        if is_generic_portal(r["final_url"]):
            tried.append(f"{url.rstrip('/').split('/')[-1]} -> statewide portal")
            continue
        weak = "" if s >= MIN_STRONG["elections"] else " (weak match — review)"
        return r["final_url"], f'found via link "{text[:40]}" score={s}{weak}', tried
    return "", "", tried


def _find_elections(home: str, home_links: list[tuple[str, str]], exclude: set[str]
                    ) -> tuple[str, str, list[tuple[str, str]]]:
    """Locate the elections landing page, escalating through three strategies."""
    all_tried: list[str] = []

    # 1. Straight from the homepage links.
    url, note, tried = _try_candidates(home_links, exclude, home)
    all_tried += tried
    if url:
        return url, note, home_links

    # 2. Force a headless render — some homepages build their nav entirely in JS,
    #    so the plain HTML has links but not the elections one.
    try:
        import snapshot
        h = snapshot.fetch_headless(home)
        if h["ok"] and h["html"]:
            rendered = links_of(h["html"], h["final_url"])
            if rendered:
                url, note, tried = _try_candidates(rendered, exclude, home)
                all_tried += tried
                if url:
                    return url, note + " [via headless render]", rendered + home_links
                home_links = rendered + home_links
    except Exception:  # noqa: BLE001
        pass

    # 3. Walk one level through a "Departments"/"Government"/"County Offices" nav
    #    page, which is where some counties file the elections office.
    for _s, durl, _t in rank_links(home_links, DEPT_PATTERNS, exclude,
                                   home, prefer_internal=True)[:2]:
        dr = fetch(durl)
        if not dr["ok"] or "html" not in dr["ctype"].lower():
            continue
        dept_links = links_of(dr["html"], dr["final_url"])
        url, note, tried = _try_candidates(dept_links, exclude, home)
        all_tried += tried
        if url:
            return (url, note + f" [via {durl.rstrip('/').split('/')[-1]} page]",
                    dept_links + home_links)

    detail = f" (tried: {'; '.join(all_tried[:3])})" if all_tried else ""
    return "", f"GAP: no working elections page found{detail}", home_links


# Clarity ENR deep links embed a per-election id (…/TX/Denton/124476/web.307579/…)
# that goes stale every cycle. The county index page lists all elections and is
# stable, so prefer it.
_CLARITY_RE = re.compile(r"^(https?://results\.enr\.clarityelections\.com/[A-Z]{2}/[^/]+/)")


def unlaunder_translate_proxy(url: str) -> str:
    """Recover the real URL behind a Google Translate proxy host.

    County sites sometimes link their own elections portal through Translate, e.g.
    "www-pottercountytexasvotes-gov.translate.goog/early-voting-locations". The
    underlying site is the genuine target, so rewrite rather than discard — the
    proxy adds a language layer and its own churn (rotating sponsor logos).
    """
    p = urlparse(url)
    if not p.netloc.endswith(".translate.goog"):
        return url
    host = p.netloc[: -len(".translate.goog")].replace("-", ".")
    query = "&".join(kv for kv in p.query.split("&")
                     if kv and not kv.startswith("_x_tr_"))
    return urlunparse(("https", host, p.path, p.params, query, ""))


def stabilize_url(url: str) -> str:
    url = unlaunder_translate_proxy(url)
    m = _CLARITY_RE.match(url)
    return m.group(1) if m else url


def _plausible_target(url: str, county: str, home: str, elections_url: str) -> bool:
    """Is this URL plausibly THIS county's page?

    Accept anything on the county's own site or its elections portal. Off-site
    URLs are accepted only when they name the county, which keeps legitimate
    per-county vendor portals (results.enr.clarityelections.com/TX/Clay/,
    votedenton.gov) while rejecting unrelated third-party pages that merely
    scored well on election vocabulary.
    """
    if not is_external(url, home):
        return True
    if elections_url and not is_external(url, elections_url):
        return True
    squash = re.sub(r"[^a-z0-9]", "", county.lower())
    return squash in re.sub(r"[^a-z0-9]", "", url.lower())


def discover_county(county: str, seat: str, home: str) -> list[dict]:
    rows: list[dict] = []

    def row(ptype, url, note):
        rows.append({"county": county, "batch": BATCH_LABEL, "page_type": ptype,
                     "url": url,
                     "external": str(is_external(url, home)).lower() if url else "false",
                     "notes": note})

    home_res = fetch(home)
    if not home_res["ok"] or (home_res["status"] or 0) >= 400:
        # Hard-blocked (Akamai/Cloudflare 403 even to headless Chromium from a
        # datacenter IP) or genuinely down. The homepage row still carries the
        # verified URL so the pipeline captures the block state as a stable,
        # diffable artifact — if the block ever lifts, that shows up as a real
        # change. The four election pages can't be crawled, so they're gaps.
        why = home_res["error"] or f"HTTP {home_res['status']}"
        for pt in ("elections", "polling", "early_voting", "results"):
            row(pt, "", f"GAP: could not crawl — homepage blocked/unreachable "
                        f"({why}); needs manual URL discovery")
        log.info("%-14s homepage unreachable (%s)", county, why)
        return rows

    home_links = links_of(home_res["html"], home_res["final_url"])
    exclude = {home_res["final_url"].rstrip("/"), home.rstrip("/")}

    # --- level 1: elections landing -------------------------------------------
    elections_url, elections_note, home_links = _find_elections(
        home, home_links, exclude)
    row("elections", elections_url, elections_note)

    # --- level 2 + 3: polling / early_voting / results ---------------------------
    # Level 2 = links on the elections landing page. Level 3 = links on the
    # "Current Elections" / per-election hub pages found there, which is where
    # CivicPlus-style county sites actually publish polling & early-voting detail.
    deep_links = list(home_links)
    hub_urls: list[str] = []
    if elections_url:
        exclude.add(elections_url.rstrip("/"))
        er = fetch(elections_url)
        if er["ok"]:
            elections_links = links_of(er["html"], er["final_url"])

            # The page the homepage points at is sometimes just a stub that hands
            # off to the county's real elections portal (Denton's /1021/Elections
            # -> votedenton.gov). Promote that portal to be the elections target:
            # it holds the substantive content, and its links are what we need to
            # crawl for polling / early voting / results.
            portal = None
            for _t, u in elections_links:
                label = urlparse(u).netloc.lower().removeprefix("www.").split(".")[0]
                if ("vote" in label or label == "elections") and not is_generic_portal(u):
                    if not is_external(u, elections_url):
                        continue  # same site, not a separate portal
                    portal = u
                    break
            if portal:
                pr = fetch(portal)
                # Re-check the FINAL url: a link that looks county-specific can
                # redirect onto a national/statewide site (Burleson's landed on
                # fairelectionscenter.org).
                if (pr["ok"] and (pr["status"] or 0) < 400
                        and "html" in pr["ctype"].lower()
                        and not is_generic_portal(pr["final_url"])):
                    stub = elections_url
                    elections_url = pr["final_url"]
                    elections_links = links_of(pr["html"], pr["final_url"])
                    rows[0]["url"] = elections_url
                    rows[0]["external"] = str(is_external(elections_url, home)).lower()
                    rows[0]["notes"] = (f"dedicated elections portal, reached via "
                                        f"{stub.rstrip('/').split('/')[-1] or 'elections page'}")
                    exclude.add(elections_url.rstrip("/"))

            deep_links = elections_links + home_links
            # Hub pages must live on the county's own site (or its elections
            # portal). Without this, a "board election information" link to a
            # school district (Austin -> bellvilleisd.org) or a countdown-timer
            # widget (Hamilton -> logwork.com) can become a polling/EV target.
            for _s, hurl, _t in rank_links(elections_links, HUB_PATTERNS, exclude,
                                           home, prefer_internal=True)[:4]:
                if is_external(hurl, home) and is_external(hurl, elections_url):
                    continue
                hub_urls.append(hurl)
                if len(hub_urls) == 2:
                    break
    # Only keep hubs that are real, reachable HTML — some "Current Elections"
    # links point straight at a DocumentCenter PDF, which is out of scope and must
    # never become a fallback target.
    verified_hubs: list[str] = []
    for hurl in hub_urls:
        hr = fetch(hurl)
        if hr["ok"] and (hr["status"] or 0) < 400 and "html" in hr["ctype"].lower():
            verified_hubs.append(hr["final_url"])
            deep_links = links_of(hr["html"], hr["final_url"]) + deep_links
    hub_urls = verified_hubs

    for ptype in ("polling", "early_voting", "results"):
        pick = best_link(deep_links, ptype, exclude, home)
        chosen_url, note = "", ""
        if pick and not _plausible_target(pick[0], county, home, elections_url):
            pick = None
            note = ("GAP: no county-specific page found (best candidate was an "
                    "unrelated third-party site)")
        if pick:
            url, s, text = pick
            if elections_url and url.rstrip("/") == elections_url.rstrip("/"):
                note = "GAP: folded into elections page"
            else:
                r = fetch(url)
                if not r["ok"] or (r["status"] or 0) >= 400:
                    note = f"GAP: candidate unreachable ({url})"
                elif "html" not in r["ctype"].lower():
                    note = f"GAP: candidate is non-HTML ({r['ctype'][:25]}) — out of scope"
                elif is_generic_portal(r["final_url"]):
                    note = "GAP: candidate redirects to a statewide portal (not county-specific)"
                else:
                    chosen_url = stabilize_url(r["final_url"])
                    weak = "" if s >= MIN_STRONG[ptype] else " (weak match — review)"
                    stab = (" [normalized to stable Clarity index]"
                            if chosen_url != r["final_url"] else "")
                    note = f'found via "{text[:40]}" score={s}{weak}{stab}'
        # Fall back to the per-election hub page: for many counties that IS where
        # polling/early-voting content lives, and it is the highest-value page to
        # diff around an election. Better to capture it than to record nothing.
        if not chosen_url and ptype in ("polling", "early_voting") and hub_urls:
            hub = hub_urls[0]
            if hub.rstrip("/") != (elections_url or "").rstrip("/"):
                chosen_url = hub
                note = (f"no standing {ptype} page; using per-election hub page "
                        f"(shared with other types) — review")
        if not chosen_url and not note:
            note = "GAP: no distinct page found" + (
                " (likely folded into elections page)" if elections_url else "")
        row(ptype, chosen_url, note)

    got = sum(1 for r in rows if r["url"])
    log.info("%-14s %d/4 pages", county, got)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--county", action="append", default=None)
    ap.add_argument("--batch", default="2",
                    help="which batch's discovered homepages to crawl (default 2)")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])
    global BATCH_LABEL
    BATCH_LABEL = str(args.batch)

    global IN_CSV, OUT_CSV
    IN_CSV = ROOT / "manifest" / f"batch{args.batch}_homepages.csv"
    OUT_CSV = ROOT / "manifest" / f"batch{args.batch}_targets_draft.csv"
    if not IN_CSV.exists():
        sys.exit(f"missing {IN_CSV} — run discover_homepages.py --batch {args.batch} first")
    homes = list(csv.DictReader(IN_CSV.open(encoding="utf-8")))
    if args.county:
        want = {c.lower() for c in args.county}
        homes = [h for h in homes if h["county"].lower() in want]
    homes = [h for h in homes if h["homepage"].strip()]

    all_rows: list[dict] = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(discover_county, h["county"], h["seat"],
                            h["homepage"]): h["county"] for h in homes}
        for f in cf.as_completed(futs):
            all_rows.extend(f.result())

    order = {h["county"]: i for i, h in enumerate(homes)}
    ptorder = {"elections": 0, "polling": 1, "early_voting": 2, "results": 3}
    all_rows.sort(key=lambda r: (order[r["county"]], ptorder[r["page_type"]]))

    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["county", "batch", "page_type", "url",
                                           "external", "notes"])
        w.writeheader()
        w.writerows(all_rows)
    found = sum(1 for r in all_rows if r["url"])
    log.info("\nwrote %s — %d rows, %d with URLs, %d gaps",
             OUT_CSV, len(all_rows), found, len(all_rows) - found)


if __name__ == "__main__":
    main()
