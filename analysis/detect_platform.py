#!/usr/bin/env python3
"""Detect the CMS/website platform behind each Texas county's election site.

SAME-HOST EVIDENCE ONLY. The platform is who BUILT the site, so the only
admissible evidence is:

  * a <meta name="generator"> tag                      (definitive, same-host)
  * a same-host asset path (wp-content/, /desktopmodules/, /sites/default/files)
  * a builder's own attribution credit in the page      ("CivicPlus(R)", "Site by
    Revize", "Powered by GovOffice") - an outbound link, but it is the BUILDER
    naming itself, which is what we are trying to measure

Explicitly INADMISSIBLE: outbound links to election-services or records vendors.
Tyler Technologies is the trap here - 24 of 254 counties link to a
`portal-tx<county>.tylertech.cloud` court-records portal, which says nothing
about who built the county's website. Those are recorded in a separate
`services` column and never touch the platform verdict.

KNOWN CEILING ON RECALL: normalize.py strips every <link rel="stylesheet">
(normalize.py, "_DROP_TAGS" / stylesheet handling), and a stylesheet href is
where `wp-content/themes/<theme>/style.css` would normally name the builder. So
a WordPress site whose only tell was its theme stylesheet is UNIDENTIFIABLE from
the normalized artifact. The "Other / unknown" bucket is therefore a floor on
ignorance, not a measurement of custom-built sites. Reported honestly.

Output: analysis/output/tx_platform.csv
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "snapshots"
OUTDIR = ROOT / "analysis" / "output"


def registered_domain(host: str) -> str:
    """Last two labels of a hostname; good enough to compare same-site."""
    host = (host or "").lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    parts = [p for p in host.split(".") if p]
    if len(parts) <= 2:
        return ".".join(parts)
    # co.harris.tx.us / *.tx.us style: keep the last three labels
    if parts[-1] == "us" and parts[-2] in ("tx", "state"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def same_host(url: str, own: str) -> bool:
    """True for a relative path, or an absolute URL on the county's own domain."""
    if not url:
        return False
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", url) and not url.startswith("//"):
        return True                      # relative -> same host by definition
    p = urlparse(url if "//" in url else "//" + url)
    return registered_domain(p.netloc) == own


# --- platform rules -------------------------------------------------------
# (label, generator regex, same-host path regex, builder-credit regex)
RULES = [
    ("WordPress",
     r"\bwordpress\b",
     r"/?wp-(?:content|includes|json)/",
     r"powered by wordpress"),
    ("CivicPlus",
     r"civic(?:plus|engage)",
     r"/(?:civicplus|civicengage)/",
     r"(?:powered|designed|built)\s+by\s+civicplus|civicplus\s*(?:®|\(r\)|&reg;)"
     r"\s*(?!\s*nextrequest)|connect\.civicplus\.com/referral|civicengage"),
    ("Revize",
     r"\brevize\b",
     r"/revize/",
     r"revize\s*(?:government websites|software|llc)?|site by revize|powered by revize"),
    ("Drupal",
     r"\bdrupal\b",
     r"/sites/default/files/|data-drupal-",
     r"powered by drupal"),
    ("Joomla",
     r"\bjoomla\b",
     r"/components/com_|option=com_",
     r"powered by joomla"),
    ("DotNetNuke",
     r"dotnetnuke|\bdnn\b",
     r"/desktopmodules/|/portals/_default/",
     r"dotnetnuke|powered by dnn"),
    ("Wix",
     r"\bwix\b",
     r"/_partials/wix-|static\.wixstatic\.com",
     r"wix\.com website builder|created with wix"),
    ("Squarespace",
     r"squarespace",
     r"/universal/scripts-compressed/",
     r"powered by squarespace"),
    ("Granicus / Vision",
     r"granicus|vision internet",
     r"/vision/|/granicus/",
     r"granicus|vision internet"),
    ("GovOffice",
     r"govoffice",
     r"/govoffice/|/vertical/sites/",
     r"govoffice|powered by govoffice"),
    ("EvoGov",
     r"evo\s*cloud|evogov",
     r"/evogov/",
     r"site by evogov|evogov|evo cloud"),
    ("Weebly",
     r"weebly",
     r"/files/theme/",
     r"powered by weebly"),
    # ezTask Titanium, distributed to member counties through the Texas
    # Association of Counties. THE dominant Texas county platform - 170 of 254
    # sites carry its footer credit. Its structural fingerprints
    # (/runtime/styles/, /common/scripts/ezutilities.js, Telerik WebResource.axd)
    # are all inside <script> and <link> and are therefore destroyed by
    # normalize.py; only the visible "powered by ezTask Titanium" credit and the
    # TAC attribution survive into page.txt/page.html, so the credit is the only
    # usable signal.
    ("ezTask Titanium (TAC)",
     r"eztask",
     r"/runtime/(?:styles|scripts)/|/common/scripts/ezutilities",
     # The credit is markup, not prose: <span class="eztask"> with "powered by"
     # in a SEPARATE element, so the phrase is never contiguous. Match the bare
     # vendor token - distinctive enough not to collide with anything else.
     r"\beztask\b|provided by the texas association of counties"),
]

# The builder's own CDN serving this site's assets. Distinct from a service
# vendor: static.wixstatic.com hosting a county's images means Wix BUILT it.
BUILDER_CDN = [
    ("Wix", r"static\.wixstatic\.com"),
    ("Squarespace", r"images\.squarespace-cdn\.com"),
    ("Weebly", r"cdn\d*\.editmysite\.com"),
    ("Duda", r"irp-cdn\.multiscreensite\.com|lirp\.cdn-website\.com"),
]


def _finish(row, low):
    """Attach the services column and return."""
    found = [name for name, pat in SERVICES if re.search(pat, low, re.I)]
    row["services"] = "; ".join(found)
    return row


# Outbound service vendors. NEVER platform evidence - recorded separately so the
# dependence is visible without contaminating the builder question.
SERVICES = [
    ("Tyler Technologies", r"tylertech\.(?:cloud|com)|tylerhost\.net"),
    ("Clarity / Scytl", r"clarityelections|scytl"),
    ("ENR / results portal", r"enr\.|electionresults|livevoterturnout|votetexas\.gov"),
    ("Google Translate", r"translate\.google"),
    ("Granicus services", r"granicus\.com"),
]


def detect(county: str) -> dict:
    d = SNAP / county / "homepage"
    html_p, meta_p = d / "page.html", d / "meta.json"
    row = {"county": county, "platform": "Other / unknown", "evidence": "",
            "evidence_kind": "", "services": "", "note": "",
            "has_generator": "no", "html_bytes": 0}
    if not html_p.exists() or not meta_p.exists():
        row["note"] = "no homepage capture"
        return row
    try:
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        meta = {}
    html = html_p.read_text(encoding="utf-8", errors="replace")
    row["html_bytes"] = len(html.encode("utf-8"))
    own = registered_domain(urlparse(meta.get("final_url") or
                                     meta.get("requested_url") or "").netloc)

    # A blocked / error capture cannot be classified - say so rather than
    # calling a Cloudflare page "custom built".
    status = meta.get("http_status")
    title = (meta.get("title") or "")
    if (status and status >= 400) or re.search(
            r"error page|not found|web server is down|robot challenge|just a moment",
            title, re.I):
        row["platform"] = "Not classifiable (bad capture)"
        row["note"] = f"HTTP {status}; title={title[:40]!r}"
        return row
    if row["html_bytes"] < 2000:
        row["platform"] = "Not classifiable (bad capture)"
        row["note"] = f"only {row['html_bytes']} bytes captured"
        return row

    soup = BeautifulSoup(html, "lxml")
    low = html.lower()

    # 1) generator meta - definitive
    gen = soup.find("meta", attrs={"name": re.compile(r"^generator$", re.I)})
    gen_val = (gen.get("content") or "").strip() if gen else ""
    if gen_val:
        row["has_generator"] = "yes"

    # 2) same-host asset paths, collected from href/src/action attributes
    hosted = []
    for tag in soup.find_all(["a", "img", "script", "form", "source"]):
        for attr in ("href", "src", "action", "data-src"):
            v = tag.get(attr)
            if v and same_host(v, own):
                hosted.append(v.lower())
    hosted_blob = " ".join(hosted)

    # Evidence hierarchy, strongest first. This MUST be three separate passes
    # over all rules, not one pass testing all three kinds per rule: Delta
    # declares `Drupal 11` in its generator AND links to civicplus.com, and a
    # per-rule loop labelled it CivicPlus purely because CivicPlus is listed
    # earlier. A generator tag is the site telling you what built it; a credit
    # elsewhere on the page is much weaker and must never outrank it.

    # Pass 1 - meta generator (definitive)
    if gen_val:
        for label, gen_re, _, _ in RULES:
            if re.search(gen_re, gen_val, re.I):
                row.update(platform=label, evidence=gen_val[:70],
                           evidence_kind="meta generator")
                return _finish(row, low)

    # Pass 2 - same-host asset path
    for label, _, path_re, _ in RULES:
        if re.search(path_re, hosted_blob, re.I):
            m = re.search(r"\S*" + path_re + r"\S*", hosted_blob, re.I)
            row.update(platform=label, evidence=(m.group(0)[:70] if m else path_re),
                       evidence_kind="same-host path")
            return _finish(row, low)

    # Pass 3 - builder CDN (the builder's own infrastructure serving this site's
    # assets: static.wixstatic.com media on a Wix build). Weaker than a path on
    # the county's own domain, stronger than a text credit.
    for label, cdn_re in BUILDER_CDN:
        if re.search(cdn_re, low, re.I):
            row.update(platform=label, evidence=cdn_re, evidence_kind="builder CDN")
            return _finish(row, low)

    # Pass 4 - textual builder credit (weakest; product mentions live here too)
    for label, _, _, credit_re in RULES:
        if re.search(credit_re, low, re.I):
            m = re.search(r".{0,28}(?:" + credit_re + r").{0,28}", low, re.I)
            row.update(platform=label,
                       evidence=" ".join((m.group(0) if m else "").split())[:70],
                       evidence_kind="builder credit")
            return _finish(row, low)

    if row["platform"] == "Other / unknown" and gen_val:
        row["evidence"] = gen_val[:70]
        row["evidence_kind"] = "generator (unrecognised)"

    return _finish(row, low)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    counties = sorted(p.name for p in SNAP.iterdir() if p.is_dir())
    rows = [detect(c) for c in counties]
    out = OUTDIR / "tx_platform.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)

    import collections
    tally = collections.Counter(r["platform"] for r in rows)
    kinds = collections.Counter(r["evidence_kind"] for r in rows if r["evidence_kind"])
    print(f"counties: {len(rows)}  ->  {out.relative_to(ROOT)}")
    print("\nplatform:")
    for k, v in tally.most_common():
        print(f"  {v:>4}  {k}")
    print("\nevidence kind:")
    for k, v in kinds.most_common():
        print(f"  {v:>4}  {k}")
    svc = collections.Counter()
    for r in rows:
        for s in filter(None, r["services"].split("; ")):
            svc[s] += 1
    print("\nservices (NOT used for platform):")
    for k, v in svc.most_common():
        print(f"  {v:>4}  {k}")


if __name__ == "__main__":
    main()
