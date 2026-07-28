#!/usr/bin/env python3
"""One-shot builder for manifest/targets.csv from Phase 1 discovery results.

Kept in the repo as a record of how the initial manifest was assembled. Editing
targets.csv by hand afterward is fine; this is not part of the pipeline.

Rule applied: capture a row with a URL only when a DISTINCT working HTML page
exists. PDF-only, generic non-county-specific state portals, or page types that
merely fold into another already-captured page are recorded as GAPS (empty url)
with an explanatory note — that is expected data, not an error.
external = true when the URL's registered domain differs from the county homepage.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "manifest" / "targets.csv"

# (county, homepage) — homepage rows. Tarrant uses www (bare host has a cert mismatch).
HOMEPAGES = [
    ("Harris", "https://www.harriscountytx.gov/", "false", "seed"),
    ("Dallas", "https://www.dallascounty.org/", "false", "seed"),
    ("Tarrant", "https://www.tarrantcountytx.gov/", "false", "seed; bare host tarrantcountytx.gov has TLS cert mismatch, use www"),
    ("Bexar", "https://www.bexar.org/", "false", "seed"),
    ("Travis", "https://www.traviscountytx.gov/", "false", "seed"),
    ("Collin", "https://www.collincountytx.gov/", "false", "seed"),
    ("El Paso", "https://www.epcounty.com/", "false", "seed"),
    ("Hidalgo", "https://www.hidalgocounty.us/", "false", "seed"),
    ("Williamson", "https://www.wilcotx.gov/", "false", "seed"),
    ("Webb", "https://www.webbcountytx.gov/", "false", "seed; blocks plain httpx (reset), served via headless"),
    ("Lubbock", "https://www.lubbockcounty.gov/", "false", "seed"),
    ("Bell", "https://www.bellcountytx.com/", "false", "seed"),
    ("Galveston", "https://www.galvestoncountytx.gov/", "false", "seed; Akamai Access-Denied to bots (403)"),
    ("Kerr", "https://kerrcountytx.gov/", "false", "seed"),
    ("Gillespie", "https://www.gillespiecounty.gov/", "false", "seed"),
    ("Medina", "https://www.medinatx.gov/", "false", "seed"),
    ("Llano", "https://www.co.llano.tx.us/", "false", "seed; redirects to llanocounty.gov"),
    ("Brewster", "https://www.brewstercounty.gov/", "false", "seed"),
    ("Presidio", "https://www.co.presidio.tx.us/", "false", "seed"),
    ("Hartley", "https://www.co.hartley.tx.us/", "false", "seed"),
    ("Roberts", "https://www.co.roberts.tx.us/", "false", "seed"),
    ("Loving", "https://www.co.loving.tx.us/", "false", "seed"),
    ("King", "https://www.co.king.tx.us/", "false", "seed"),
    ("Kenedy", "https://www.kenedycountytx.gov/", "false", "seed"),
]

# county -> {page_type: (url, external, notes)}. Empty url = flagged gap.
TARGETS = {
    "Harris": {
        "elections": ("https://www.harrisvotes.com/", "true", "Harris County Clerk elections portal"),
        "polling": ("https://www.harrisvotes.com/Vote-Centers", "true", "Election-day vote centers; JS-driven"),
        "early_voting": ("", "true", "GAP: EV published only as PDF (/EV-Poster redirects to PDF); no HTML page"),
        "results": ("https://www.harrisvotes.com/Election-Results", "true", "Results portal; JS shell"),
    },
    "Dallas": {
        "elections": ("https://www.dallascountyvotes.org/", "true", "Dallas County Elections portal"),
        "polling": ("https://www.dallascountyvotes.org/vote-centers/", "true", "Vote centers w/ interactive map"),
        "early_voting": ("https://www.dallascountyvotes.org/early-voting/", "true", "Early voting info page"),
        "results": ("https://www.dallascountyvotes.org/election-results/", "true", "Results w/ ENR tool; JS-rendered"),
    },
    "Tarrant": {
        "elections": ("https://www.tarrantcountytx.gov/en/elections.html", "false", "County elections landing"),
        "polling": ("https://gisit.tarrantcounty.com/tcvotingwaittime/", "true", "Polling/wait-time lookup; JS map; diff domain tarrantcounty.com"),
        "early_voting": ("https://www.tarrantcountytx.gov/en/elections/current-election-information.html", "false", "Current-election page; EV schedule/locations as linked PDFs"),
        "results": ("https://results.enr.clarityelections.com/TX/Tarrant/", "true", "Clarity ENR index (stable); per-election IDs live under it"),
    },
    "Bexar": {
        "elections": ("https://www.bexar.org/elections", "false", "Elections Dept landing (redirects to /1568)"),
        "polling": ("https://www.bexar.org/3184/Election-Day-Vote-Information", "false", "Election Day vote info + location search"),
        "early_voting": ("https://www.bexar.org/2237/Early-Vote-Information", "false", "Early Vote information page"),
        "results": ("https://results.enr.clarityelections.com/TX/Bexar/", "true", "Clarity ENR index (stable)"),
    },
    "Travis": {
        "elections": ("https://votetravis.gov/current-election-information/", "true", "Elections run on separate votetravis.gov domain"),
        "polling": ("https://votetravis.gov/current-election-information/current-election/", "true", "Countywide vote centers; ED sites PDF here"),
        "early_voting": ("", "true", "GAP: EV shares the current-election page; no distinct URL"),
        "results": ("https://results.enr.clarityelections.com/TX/Travis/", "true", "Clarity ENR index (stable)"),
    },
    "Collin": {
        "elections": ("https://www.collincountytx.gov/elections", "false", "Elections Admin landing (JS SPA)"),
        "polling": ("https://www.collincountytx.gov/Elections/polling-locations", "false", "Countywide vote centers (EV+ED); JS-rendered"),
        "early_voting": ("", "false", "GAP: vote centers cover EV; no distinct EV page"),
        "results": ("https://www.collincountytx.gov/elections/election-results", "false", "Self-hosted results (no Clarity portal)"),
    },
    "El Paso": {
        "elections": ("https://epcountyvotes.com/", "true", "Elections Dept on separate epcountyvotes.com domain"),
        "polling": ("https://epcountyvotes.com/voter-information/election-day-vote-centers", "true", "Countywide vote centers; JS elements"),
        "early_voting": ("https://epcountyvotes.com/voter-information/early-voting-locations", "true", "EV locations; JS elements"),
        "results": ("https://results.enr.clarityelections.com/TX/El_Paso/", "true", "Clarity ENR index (stable)"),
    },
    "Hidalgo": {
        "elections": ("https://www.hidalgocounty.us/105/Elections-Department", "false", "Elections Dept landing on county domain"),
        "polling": ("https://hidalgoelections.maps.arcgis.com/apps/instant/nearby/index.html?appid=f63ecf63fc2c4c898eb7f5e2a5b8a2ef", "true", "ArcGIS Election Day locator (JS map)"),
        "early_voting": ("https://hidalgoelections.maps.arcgis.com/apps/instant/nearby/index.html?appid=ca66194e256342bca592007a24e0c953", "true", "ArcGIS early voting locator (JS map)"),
        "results": ("https://results.enr.clarityelections.com/TX/Hidalgo/", "true", "Clarity ENR index (stable)"),
    },
    "Williamson": {
        "elections": ("https://www.wilcotx.gov/185/Elections", "false", "Official elections landing"),
        "polling": ("https://www.wilcotx.gov/VoterLookup", "false", "JS voter/ballot lookup finds polling place; no static list"),
        "early_voting": ("", "false", "GAP: same VoterLookup tool; EV per-election PDFs in DocumentCenter"),
        "results": ("https://www.wilcotx.gov/292/Results-Archive", "false", "Results hub; live returns on LiveVoterTurnout ENR (per-election URL)"),
    },
    "Webb": {
        "elections": ("https://www.webbcountytx.gov/electionsadministration/", "false", "Elections Administration landing"),
        "polling": ("https://www.webbcountytx.gov/ElectionsAdministration/ElectionDaySites/", "false", "Election Day sites, per-election"),
        "early_voting": ("https://www.webbcountytx.gov/ElectionsAdministration/EarlyVotingSites/", "false", "Early voting sites"),
        "results": ("https://www.webbcountytx.gov/ElectionsAdministration/UnofficialResults/default.aspx", "false", "County-hosted results (no third-party portal)"),
    },
    "Lubbock": {
        "elections": ("https://votelubbock.gov/", "true", "Elections office on separate votelubbock.gov domain"),
        "polling": ("https://votelubbock.gov/election-information/election-day-information/", "true", "Election Day vote center locations"),
        "early_voting": ("https://votelubbock.gov/election-information/early-voting-information/", "true", "Early voting dates/times/locations"),
        "results": ("https://votelubbock.gov/election-information/historical-election-results/", "true", "County-run results on votelubbock.gov"),
    },
    "Bell": {
        "elections": ("https://www.bellcountytx.com/departments/elections", "false", "Elections dept landing"),
        "polling": ("https://www.bellcountytx.com/departments/elections/election_day_locations.php", "false", "Election Day locations"),
        "early_voting": ("https://www.bellcountytx.com/departments/elections/early_voting_information.php", "false", "Early Voting information"),
        "results": ("https://results.enr.clarityelections.com/TX/Bell/", "true", "Clarity ENR index (stable)"),
    },
    "Galveston": {
        "elections": ("https://galvestonvotes.org/election-information/", "true", "Elections Division on galvestonvotes.org; JS-rendered"),
        "polling": ("https://galvestonvotes.org/polling-locations/", "true", "Open-voting county (vote anywhere); JS-rendered"),
        "early_voting": ("https://galvestonvotes.org/election-information/current-and-upcoming-elections/", "true", "EV locations/hours folded into current elections page"),
        "results": ("https://results.enr.clarityelections.com/TX/Galveston/", "true", "Clarity ENR index (stable)"),
    },
    "Kerr": {
        "elections": ("https://kerrcountytx.gov/voting-in-kerr-county", "false", "Main voting/elections landing"),
        "polling": ("https://kerrcountytx.gov/voting-in-kerr-county/kerr-county-elections", "false", "Elections detail; ED locations as per-election PDFs"),
        "early_voting": ("", "false", "GAP: same kerr-county-elections page; EV as per-election PDFs"),
        "results": ("", "true", "GAP: legacy co.kerr.tx.us/elections/results/ archive is HTTPS-unreachable (persistent timeout); also uses TX SOS ENR"),
    },
    "Gillespie": {
        "elections": ("https://www.gillespiecounty.gov/1237/Elections", "false", "Main elections page (CivicPlus)"),
        "polling": ("", "false", "GAP: 13 precinct polling locations listed on elections page"),
        "early_voting": ("", "false", "GAP: EV location listed on elections page"),
        "results": ("https://www.gillespiecounty.gov/1319/Election-Results-Past-Present", "false", "Hand-counted county; self-hosted results"),
    },
    "Medina": {
        "elections": ("https://www.medinatx.gov/page/Elections", "false", "Main elections landing; per-year subpages"),
        "polling": ("", "false", "GAP: dates/locations posted as image/PDF on year page (Elections-<year>)"),
        "early_voting": ("", "false", "GAP: EV schedule as image/PDF on year page"),
        "results": ("", "false", "GAP: results posted as PDFs on year page medinatx.gov/page/Elections-<year>"),
    },
    "Llano": {
        "elections": ("https://www.llanocounty.gov/page/Elections", "false", "Main elections/voter-info page (llanocounty.gov is the live site)"),
        "polling": ("", "false", "GAP: precinct polling locations on elections page"),
        "early_voting": ("", "false", "GAP: EV dates/locations on elections page"),
        "results": ("https://www.llanocounty.gov/page/Elections-Archived.Elections", "false", "County-hosted results/canvass archive"),
    },
    "Brewster": {
        "elections": ("https://www.brewstercounty.gov/page/elections.information", "false", "Elections info page (the .administrator page is contact-only)"),
        "polling": ("", "false", "GAP: polling-location doc on elections info page"),
        "early_voting": ("", "false", "GAP: EV via state portal/notices; no distinct county page"),
        "results": ("", "false", "GAP: unofficial results + canvass as PDFs on elections info page"),
    },
    "Presidio": {
        "elections": ("https://www.co.presidio.tx.us/page/presidio.Election.Information", "false", "Main election info page"),
        "polling": ("", "false", "GAP: polling places in election-notice PDFs on elections page"),
        "early_voting": ("", "false", "GAP: EV locations in notice PDFs on elections page"),
        "results": ("", "false", "GAP: results/hand-count audit as PDFs on elections page"),
    },
    "Hartley": {
        "elections": ("https://www.co.hartley.tx.us/page/hartley.Voter.Information", "false", "Voter-info/elections page; JS-CMS"),
        "polling": ("", "true", "GAP: uses generic state EV/polling portal; no distinct county page"),
        "early_voting": ("", "true", "GAP: uses generic state EV portal; no distinct county page"),
        "results": ("", "true", "GAP: no reachable distinct results page (results.texas-elections.com does not resolve); results via TX SOS / PDFs"),
    },
    "Roberts": {
        "elections": ("https://www.co.roberts.tx.us/page/roberts.elections", "false", "Elections page w/ EV/polling/results sections inline"),
        "polling": ("", "false", "GAP: polling section on elections page"),
        "early_voting": ("", "false", "GAP: EV section on elections page"),
        "results": ("", "false", "GAP: results only as PDFs on elections page"),
    },
    "Loving": {
        "elections": ("https://lovingcountyanddistrictclerk.com/elections-1", "true", "County .gov has no elections link; clerk site is the elections hub"),
        "polling": ("", "true", "GAP: polling/EV location folded into clerk elections page"),
        "early_voting": ("", "true", "GAP: EV dates/hours folded into clerk elections page"),
        "results": ("", "false", "GAP: no official online results page (~60 residents)"),
    },
    "King": {
        "elections": ("", "false", "GAP: no HTML election pages; only PDFs under /upload/page/ linked from homepage"),
        "polling": ("", "false", "GAP: polling info only as PDF"),
        "early_voting": ("", "false", "GAP: early voting info only as PDF"),
        "results": ("", "false", "GAP: results only as PDF (/upload/page/9613/...)"),
    },
    "Kenedy": {
        "elections": ("https://www.kenedycountytx.gov/page/kenedy.Elections", "false", "County .gov elections landing; links to kenedycountyelections.com"),
        "polling": ("https://kenedycountyelections.com/polling-places/", "true", "Vote centers + EV location"),
        "early_voting": ("https://kenedycountyelections.com/current-election/", "true", "EV schedule w/ dates/times/location"),
        "results": ("https://kenedycountyelections.com/results/", "true", "Results by election w/ PDF reports"),
    },
}

PAGE_ORDER = ["homepage", "elections", "polling", "early_voting", "results"]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    home_by_county = {c: (u, e, n) for c, u, e, n in HOMEPAGES}
    for county, _url, _e, _n in HOMEPAGES:
        for ptype in PAGE_ORDER:
            if ptype == "homepage":
                url, ext, note = home_by_county[county]
            else:
                url, ext, note = TARGETS[county][ptype]
            # batch 1 = the original 24 counties with pre-verified homepages.
            rows.append({"county": county, "batch": "1", "page_type": ptype,
                         "url": url, "external": ext, "notes": note})
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["county", "batch", "page_type", "url",
                                           "external", "notes"])
        w.writeheader()
        w.writerows(rows)
    gaps = sum(1 for r in rows if not r["url"])
    print(f"wrote {OUT} — {len(rows)} rows ({len(rows)-gaps} with URLs, {gaps} gaps)")


if __name__ == "__main__":
    main()
