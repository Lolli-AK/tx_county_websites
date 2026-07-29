"""Homepage-identity verification tests.

Twelve Texas counties share a name with a *different* county's seat, so a loose
"county name + the word county" check produces confident-looking false positives.
These tests pin the behaviour that stops them.

Run:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import discover_homepages as H  # noqa: E402

SEED = ROOT / "manifest" / "counties.csv"


def _seed() -> dict[str, str]:
    with SEED.open(newline="", encoding="utf-8") as fh:
        return {r["county"].strip(): r["seat"].strip() for r in csv.DictReader(fh)}


def _page(body: str) -> str:
    """Pad to clear the near-empty-page floor without changing the signals."""
    filler = (" The office is open Monday through Friday and serves residents "
              "throughout the area with records, permits and other services.")
    while len(body) < 200:
        body += filler
    return body


# --------------------------------------------------------------------------- #
# The collision set is real and must be derivable from the seed
# --------------------------------------------------------------------------- #
def test_name_seat_collisions_exist_and_are_known():
    """Guards against someone 'simplifying' the identity check later."""
    seed = _seed()
    names = set(seed)
    collisions = {seat: cty for cty, seat in seed.items()
                  if seat in names and seat != cty}
    # e.g. Crockett is a county AND the seat of Houston County
    assert len(collisions) >= 12, f"expected >=12 collisions, found {len(collisions)}"
    for expected in ("Crockett", "Henderson", "Rusk", "Tyler", "Jefferson", "Cameron"):
        assert expected in collisions, f"{expected} should be a name/seat collision"


# --------------------------------------------------------------------------- #
# Cross-county false positives must be rejected
# --------------------------------------------------------------------------- #
HARRIS_PAGE = _page(
    "Harris County, TX. Welcome to Harris County. Commissioners Court, county judge, "
    "county clerk and district clerk offices are located in Houston, Texas.")


def test_harris_site_is_not_accepted_as_houston_county():
    """Houston is Harris County's seat; the City of Houston is not Houston County."""
    conf, _ = H.verify("Houston", "Crockett",
                       "https://www.harriscountytx.gov/", HARRIS_PAGE,
                       "Harris County, TX")
    assert conf == "reject"


def test_harris_site_still_verifies_as_harris_county():
    conf, _ = H.verify("Harris", "Houston",
                       "https://www.harriscountytx.gov/", HARRIS_PAGE,
                       "Harris County, TX")
    assert conf == "confident"


SMITH_PAGE = _page(
    "Smith County, Texas - Official Website. Welcome to Smith County. Commissioners "
    "Court, county judge, county clerk. Tyler, Texas 75702.")


def test_smith_site_is_not_accepted_as_tyler_county():
    """Tyler is Smith County's seat; Tyler County's seat is Woodville."""
    conf, _ = H.verify("Tyler", "Woodville", "https://www.smith-county.com/",
                       SMITH_PAGE, "Smith County, Texas")
    assert conf == "reject"


def test_smith_site_still_verifies_as_smith_county():
    conf, _ = H.verify("Smith", "Tyler", "https://www.smith-county.com/",
                       SMITH_PAGE, "Smith County, Texas")
    assert conf in ("confident", "likely")


# --------------------------------------------------------------------------- #
# Nested county names: "Deaf Smith County" contains "Smith County"
# --------------------------------------------------------------------------- #
DEAF_SMITH_PAGE = _page(
    "Deaf Smith County, Texas. Welcome to the official website of Deaf Smith County. "
    "The commissioners court meets in Hereford, Texas. County clerk, county judge.")


def test_deaf_smith_verifies_as_itself():
    conf, _ = H.verify("Deaf Smith", "Hereford", "https://www.co.deaf-smith.tx.us/",
                       DEAF_SMITH_PAGE, "Deaf Smith County, Texas")
    assert conf == "confident"


def test_deaf_smith_page_is_not_accepted_as_smith_county():
    conf, _ = H.verify("Smith", "Tyler", "https://www.co.deaf-smith.tx.us/",
                       DEAF_SMITH_PAGE, "Deaf Smith County, Texas")
    assert conf == "reject"


# --------------------------------------------------------------------------- #
# Surnames that match county names must not cause rejections
# --------------------------------------------------------------------------- #
def test_surname_matching_a_county_name_does_not_reject():
    """Counties are named after people, so 'Brown' appears as a staff surname.

    A nav list rendering "Brown" and "County Clerk" on separate lines must not be
    read as "Brown County".
    """
    page = _page("Travis County, Texas\nOfficial Website\nStaff Directory\n"
                 "Brown\nCounty Clerk\nAustin, Texas\ncommissioners court")
    conf, ev = H.verify("Travis", "Austin", "https://www.traviscountytx.gov/",
                        page, "Travis County, Texas")
    assert conf in ("confident", "likely"), ev


# --------------------------------------------------------------------------- #
# Non-government and wrong-state pages
# --------------------------------------------------------------------------- #
def test_commercial_site_mentioning_the_county_is_rejected():
    """burnetcountytx.com was a process-server site, not Burnet County."""
    page = _page("Burnet County, Texas Process Servers | Guaranteed service. "
                 "We serve legal documents throughout Burnet County, Texas.")
    conf, _ = H.verify("Burnet", "Burnet", "https://burnetcountytx.com/", page,
                       "Burnet County, Texas Process Servers")
    assert conf == "reject"


def test_wrong_state_county_is_rejected():
    """Anderson County exists in SC and TN too; require a Texas signal."""
    page = _page("Anderson County, South Carolina. Welcome to Anderson County. "
                 "Commissioners, county clerk, sheriff. Anderson, SC 29621.")
    conf, _ = H.verify("Anderson", "Palestine",
                       "https://www.andersoncountysc.org/", page,
                       "Anderson County South Carolina")
    assert conf == "reject"


def test_parked_domain_is_rejected():
    page = _page("This domain is for sale. Buy this domain. Anderson County Texas.")
    conf, _ = H.verify("Anderson", "Palestine", "https://andersoncounty.com/",
                       page, "Domain for sale")
    assert conf == "reject"


# --------------------------------------------------------------------------- #
# Real captured homepages must keep verifying (regression guard)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not (ROOT / "snapshots").exists(),
                    reason="no snapshots captured yet")
def test_captured_homepages_still_verify():
    """Every successfully captured homepage should still pass identity checks.

    Bot-blocked pages (403 / challenge bodies) are excluded — they contain no
    county content to verify.
    """
    import json
    seed = _seed()
    failures = []
    for f in sorted((ROOT / "snapshots").glob("*/homepage/page.txt")):
        slug = f.parent.parent.name
        county = next((c for c in seed if c.lower().replace(" ", "_") == slug), None)
        if county is None:
            continue
        meta = json.loads((f.parent / "meta.json").read_text(encoding="utf-8"))
        if meta.get("http_status") != 200 or meta.get("error"):
            continue  # blocked/errored capture, nothing to identify
        conf, ev = H.verify(county, seed[county], meta["final_url"],
                            f.read_text(encoding="utf-8"), meta.get("title"))
        if conf == "reject":
            failures.append(f"{county}: {ev[:80]}")
    assert not failures, f"previously-verified homepages now rejected: {failures}"
