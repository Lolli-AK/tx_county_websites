"""What the voter-registration crawl must and must not accept.

Every case here is a page the crawl actually assigned to a county in the first
254-county sweep. That sweep found 139 pages and 48 of them were wrong, which is
the reason this file exists: link text and URLs are enough to *find* a candidate
and never enough to *accept* one. The four gates below are what separates them.

Run:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import discover_pages as P  # noqa: E402
import discover_registration as R  # noqa: E402


def _score(text: str, url: str) -> int:
    return P.score(text, url, P.PATTERNS["voter_registration"])


# --------------------------------------------------------------------------- #
# Gate 1: scoring must not reward the county's accounting department
# --------------------------------------------------------------------------- #
# A Texas county auditor publishes a monthly "check register" -- the list of
# cheques the county wrote. It shares one word with voter registration, and on
# that one word alone the crawl assigned an accounting page to 25 counties.
ACCOUNTING = [
    ("Check Registers", "https://www.co.cass.tx.us/page/cass.CheckRegisters"),
    ("Check Register", "https://www.co.bailey.tx.us/page/bailey.CheckRegister"),
    ("Check Registers", "https://www.co.fayette.tx.us/page/fayette.Check.Registers"),
    ("EFT Registers", "https://www.co.hill.tx.us/page/hill.EFT.Register"),
    ("Payroll Summary Register", "https://www.harrisoncountytexas.gov/page/Payroll"),
    ("Vendor Registration", "https://www.fishercounty.org/page/Vendor%20Registration"),
    ("Accounts Payable Check Registers",
     "https://www.co.tyler.tx.us/page/tyler.AccountsPayableReports.CheckRegisters"),
]
# Sign-up forms for things that are not voting, matching on "register" only.
NOT_VOTING = [
    ("Register for Emergency Alerts", "https://www.co.kimble.tx.us/page/EMS"),
    ("Register Your Storm Shelter Location",
     "https://www.co.limestone.tx.us/page/limestone.EMC.stormshelter"),
    ("Register for Code Red - Reverse 9-1-1 Notifications",
     "https://www.bellcountytx.com/publicnotice_detail_T3_R122.php"),
    ("Register for Emergency Notifications", "https://parmercounty.texas.gov/?p=6373"),
]


@pytest.mark.parametrize("text,url", ACCOUNTING + NOT_VOTING)
def test_non_voter_registers_score_below_the_threshold(text, url):
    assert _score(text, url) < P.MIN_STRONG["voter_registration"], \
        f"{text!r} should not reach the registration threshold"


@pytest.mark.parametrize("text,url", [
    ("Voter Registration", "https://www.co.andrews.tx.us/196/Register-to-Vote"),
    ("Register to Vote", "https://elections.bexar.gov/180/Register-to-Vote"),
    ("Voter Registration Information", "https://www.wilcotx.gov/294/Voter-Registration"),
])
def test_real_registration_links_clear_the_threshold(text, url):
    assert _score(text, url) >= P.MIN_STRONG["voter_registration"]


def test_an_awareness_day_outranks_nothing():
    """Hidalgo was assigned a "National Voter Registration Month" news item."""
    news = _score("National Voter Registration Month",
                  "https://www.hidalgocounty.us/2957/National-Voter-Registration-Month")
    real = _score("Voter Registration", "https://www.hidalgocounty.us/voter-registration")
    assert news < real


# --------------------------------------------------------------------------- #
# Gate 2: statewide, national and commercial destinations are gaps, not targets
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("url", [
    "https://txapps.texas.gov/tolapp/sos/SOSACManager",
    "https://www.texas.gov/living-in-texas/texas-voter-registration/",
    "https://nationalvoterregistrationday.org/",
    "https://www.bestcolleges.com/resources/voting-by-state/",
    "https://www.smart911.com/smart911/ref/reg.action?pa=campcountytexas",
    "https://portal.laserfiche.com/Portal/DocView.aspx?id=2977&repo=r-927d42fb",
    "https://acrobat.adobe.com/id/urn:aaid:sc:VA6C2:364e7529-9477",
    "https://form.jotform.us/form/43065940748158",
    "https://rts.texasonline.state.tx.us/NASApp/txdotrts/RegistrationRenewalServlet",
])
def test_non_county_destinations_are_rejected(url):
    assert P.is_generic_portal(url)


@pytest.mark.parametrize("url", [
    # The state's own domain hosts real county sites. A bare "texas.gov" hint
    # would reject all of these, which is why the statewide entries carry the
    # "www." and "txapps." prefixes.
    "https://hoodcounty.texas.gov/departments/elections_administration/",
    "https://www.wheelercounty.texas.gov/page/CheckRegister",
    "https://parmercounty.texas.gov/",
    "https://taylorcounty.texas.gov/213/Registering-to-Vote",
])
def test_counties_hosted_on_texas_gov_are_not_rejected(url):
    assert not P.is_generic_portal(url)


# --------------------------------------------------------------------------- #
# Gate 3: the page's own prose, with the site nav removed
# --------------------------------------------------------------------------- #
def test_nav_links_do_not_make_a_page_about_registration():
    """The reason the prose check strips anchors.

    A Texas county CMS repeats "Voter Registration" in the sidebar of every page
    on the site, so a check-register page mentions it exactly as often as the
    real registration page does.
    """
    html = ("<nav><a href='/vr'>Voter Registration</a>"
            "<a href='/e'>Elections</a></nav>"
            "<h1>Check Registers</h1><p>Monthly cheque listings by fund.</p>")
    prose = R._prose(html)
    assert "Check Registers" in prose
    assert not R._REG_LANGUAGE.search(prose)


def test_a_real_registration_page_reads_as_one():
    html = ("<nav><a href='/'>Home</a></nav><h1>Voter Registration</h1>"
            "<p>To register to vote in this county you must be a United States "
            "citizen and a resident. Applications are available at the Tax "
            "Assessor-Collector's office.</p>")
    assert R._REG_LANGUAGE.search(R._prose(html))


@pytest.mark.parametrize("prose", [
    "Payroll Summary Register for the period ending September 30.",
    "Register your storm shelter location with the Emergency Management Coordinator.",
    "Vendor Registration: submit a W-9 to be added to the approved vendor list.",
])
def test_prose_that_is_not_about_voting_is_rejected(prose):
    assert not R._REG_LANGUAGE.search(prose)


# --------------------------------------------------------------------------- #
# Gate 4: whose page is it
# --------------------------------------------------------------------------- #
HARRIS_TAX = ("Harris County Tax Office. Voter registration applications may be "
              "submitted to the Harris County Tax Assessor-Collector.")


def test_an_off_site_registrar_is_kept_when_the_page_names_the_county():
    """hctax.net is Harris County's tax office and names neither county nor seat.

    A URL test cannot accept this and reject Starr, because Starr County linked
    this very page. The prose can.
    """
    assert not P._plausible_target("https://www.hctax.net/Voter/Registration",
                                   "Harris", "https://www.harriscountytx.gov/", "")
    assert R._names_county(HARRIS_TAX, "Harris")


def test_the_same_page_is_rejected_for_the_county_that_merely_linked_it():
    assert not R._names_county(HARRIS_TAX, "Starr")


def test_another_countys_page_is_rejected():
    """Van Zandt was assigned Henderson County's registration page."""
    prose = ("Henderson County Elections. Voter registration in Henderson County "
             "is handled by the Tax Assessor-Collector in Athens.")
    assert R._names_county(prose, "Henderson")
    assert not R._names_county(prose, "Van Zandt")


def test_possessive_and_county_of_forms_both_count():
    assert R._names_county("Welcome to Bexar County's elections site", "Bexar")
    assert R._names_county("the County of El Paso", "El Paso")


# --------------------------------------------------------------------------- #
# The escape hatch for pages whose body is nothing but links
# --------------------------------------------------------------------------- #
WALLER_HOME = "https://www.co.waller.tx.us/"


def test_a_link_list_page_is_carried_by_its_own_url():
    """Waller's registration page is a CivicPlus "Quicklinks" list.

    Its entire body is anchors, so stripping the nav leaves a street address and
    a copyright line — 183 characters, none of them about voting. The path the
    county chose is the only evidence there is.
    """
    url = "https://www.co.waller.tx.us/page/Elections.VoterRegistration"
    assert R._named_by_its_url(url, WALLER_HOME)


@pytest.mark.parametrize("url", [
    # The whole point of requiring "voter registration" and not "register":
    # these are the paths of the pages this escape hatch must never readmit.
    "https://www.co.waller.tx.us/page/waller.CheckRegister",
    "https://www.co.waller.tx.us/page/waller.Financial.CheckRegisters",
    "https://www.co.waller.tx.us/page/Payroll",
    "https://www.co.waller.tx.us/page/Vendor%20Registration",
])
def test_the_escape_hatch_does_not_readmit_the_accounting_pages(url):
    assert not R._named_by_its_url(url, WALLER_HOME)


def test_the_escape_hatch_is_county_hosted_only():
    """Off-site is exactly where another county's page comes from."""
    assert not R._named_by_its_url("https://www.hctax.net/Voter/Registration",
                                   WALLER_HOME)
