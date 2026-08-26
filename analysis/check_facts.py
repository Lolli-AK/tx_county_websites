#!/usr/bin/env python3
"""Does each Texas county STATE four operational election facts, and correctly?

Three outcomes per (county, fact):
    matches expected      - the county states it and the value is right
    states something else - the county states it and the value differs (INSPECT)
    never states it       - the fact appears nowhere in the captured pages.
                            This is a FINDING, not missing data.

WHY WE COMPARE TO AUTHORITY, NOT TO OTHER COUNTIES
Most counties state a given fact on exactly one page, so internal contradiction
is barely detectable. Everything is judged against the statewide value below.

FALSE POSITIVES ARE THE ACTUAL PROBLEM
Extraction is easy. Deciding WHICH ELECTION and WHICH VOTING MODE a sentence
refers to is the hard part. A naive version of this check on Florida flagged 64
of 67 counties as violating statutory polling hours and every single flag was
wrong, for three separate reasons. All three are defended against here:

  1. County BUSINESS hours ("8:30 a.m. - 5:00 p.m.", "Monday-Friday") are not
     poll hours.            -> BUSINESS_CTX veto on the line and its neighbours.
  2. EARLY VOTING site hours legitimately differ from election-day hours.
                            -> EV_CTX veto, plus early_voting/ pages are skipped
                               entirely when judging election-day hours.
  3. MUNICIPAL / SPECIAL election hours can lawfully differ from a statewide
     election.              -> a polling-hours line is only JUDGED when its
                               context names the statewide election date or
                               generic election-day language, and is discarded
                               when it names a city/school/special election.

Every row carries the matched text so each cell is auditable, and a sample of
both flags and "never states it" must be eyeballed before the totals are
believed. Recall is imperfect: phrasing varies wildly.

Output: analysis/output/tx_facts.csv
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "snapshots"
OUT = ROOT / "analysis" / "output"

# ==========================================================================
# EDITABLE CONFIG - THE AUTHORITATIVE TEXAS VALUES
# Verified 2026-08-20 against the Texas Secretary of State and the Election
# Code. RE-VERIFY EVERY CYCLE; these move.
#   election day             Tuesday, November 3, 2026
#     sos.state.tx.us/elections/voter/important-election-dates.shtml
#   registration deadline    Monday, October 5, 2026        (SoS, verbatim)
#   early voting             Mon Oct 19 - Fri Oct 30, 2026  (SoS, verbatim)
#   polling hours            7:00 a.m. - 7:00 p.m.
#     Tex. Elec. Code ch. 41; votetexas.gov/voting/voting-in-person
# NOTE Texas differs from Florida: the TX early-voting period runs the 17th
# through the 4th day before election day, so a Florida window is NOT reusable.
# ==========================================================================
EXPECTED = {
    "polling_hours":         {"open": 7, "close": 19},          # 24h clock
    "election_date":         (2026, 11, 3),
    "registration_deadline": (2026, 10, 5),
    "early_voting_window":   ((2026, 10, 19), (2026, 10, 30)),
}
FACTS = ["polling_hours", "election_date", "registration_deadline",
         "early_voting_window"]

# The snapshot date. A county whose only stated date is BEFORE this is showing a
# page for an election that already happened - that is STALENESS, not a wrong
# value, and conflating the two overstates inaccuracy. 35 of 36 "wrong" election
# dates and 15 of 16 "wrong" registration deadlines were past primaries/runoffs.
AS_OF = (2026, 8, 20)
STALE = "Shows only a past election"
FACT_LABEL = {
    "polling_hours": "Polling hours",
    "election_date": "Next election date",
    "registration_deadline": "Registration deadline",
    "early_voting_window": "Early voting window",
}

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
MON_RE = "|".join(MONTHS) + r"|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec"
ABBR = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
        "sept": 9, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

DATE_RE = re.compile(rf"\b({MON_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)
NUMDATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
TIME_RANGE_RE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?\s*(?:-|–|—|to|until|till|thru|through)\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?", re.I)

# --- context vetoes -------------------------------------------------------
BUSINESS_CTX = re.compile(
    r"office hours|business hours|courthouse hours|lobby|clerk'?s office is open|"
    r"monday\s*[-–—thru]+\s*friday|mon\s*[-–—]\s*fri|open to the public|"
    r"closed for lunch|by appointment|walk[- ]?in hours|administrative office", re.I)
EV_CTX = re.compile(
    r"early voting|early vote|vote early|advance voting|ev\s+location|"
    r"early[- ]voting site", re.I)
POLL_CTX = re.compile(
    r"polls?\s+(?:will\s+)?(?:are\s+)?open|polling (?:place|location|site)s?\s+"
    r"(?:are|will be|open)|election day|on election day|vote on election day|"
    r"polls? open|polls? close", re.I)
# A local contest whose hours may lawfully differ from a statewide election.
LOCAL_ELECTION_CTX = re.compile(
    r"\b(?:city of|municipal|school district|isd\b|utility district|mud\b|"
    r"water district|special election|bond election|runoff for|charter)\b", re.I)

REG_CTX = re.compile(
    r"(?:last day|deadline|final day|must (?:be )?register|register(?:ed)? by|"
    r"registration deadline|last day to register)", re.I)
REG_TOPIC = re.compile(r"regist", re.I)
ELECTION_DAY_CTX = re.compile(
    r"election day|general election|next election|uniform election|"
    r"upcoming election|november \d{1,2},? 2026", re.I)


def parse_dates(text: str) -> list[tuple[int, int, int]]:
    out = []
    for m in DATE_RE.finditer(text):
        mon = m.group(1).lower().rstrip(".")
        mm = MONTHS.get(mon) or ABBR.get(mon)
        if mm:
            out.append((int(m.group(3)), mm, int(m.group(2))))
    for m in NUMDATE_RE.finditer(text):
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= a <= 12 and 1 <= b <= 31:
            out.append((y, a, b))
    return out


def parse_time_ranges(text: str) -> list[tuple[int, int, str]]:
    out = []
    for m in TIME_RANGE_RE.finditer(text):
        h1, ap1, h2, ap2 = int(m.group(1)), m.group(3).lower(), int(m.group(4)), m.group(6).lower()
        o = (h1 % 12) + (12 if ap1 == "p" else 0)
        c = (h2 % 12) + (12 if ap2 == "p" else 0)
        out.append((o, c, m.group(0)))
    return out


def load_pages(county: str) -> list[tuple[str, list[str]]]:
    pages = []
    d = SNAP / county
    if not d.is_dir():
        return pages
    for sub in sorted(p for p in d.iterdir() if p.is_dir()):
        f = sub / "page.txt"
        if f.exists():
            txt = f.read_text(encoding="utf-8", errors="replace")
            pages.append((sub.name, [l.strip() for l in txt.split("\n")]))
    return pages


def window(lines: list[str], i: int, before: int = 2, after: int = 2) -> str:
    return " ".join(lines[max(0, i - before): i + after + 1])


# ---------------------------------------------------------------- checks
def check_polling_hours(pages):
    """Election-day poll hours only. Returns (verdict, evidence, why)."""
    judged = []
    for ptype, lines in pages:
        if ptype == "early_voting":
            continue                     # defence 2: wrong voting mode entirely
        for i, ln in enumerate(lines):
            ranges = parse_time_ranges(ln)
            if not ranges:
                continue
            ctx = window(lines, i)
            if BUSINESS_CTX.search(ctx):                 # defence 1
                continue
            if EV_CTX.search(ctx):                       # defence 2
                continue
            if LOCAL_ELECTION_CTX.search(ctx):           # defence 3
                continue
            if not POLL_CTX.search(ctx):
                continue                 # no poll-open context: not a claim
            for o, c, raw in ranges:
                # A sub-4-hour window is a meeting, a lunch closure or a single
                # site's slot - never a statewide poll day. Coke's "12:00pm-1:00pm".
                if c - o < 4:
                    continue
                judged.append((o, c, raw, ptype, ln, ctx))
    if not judged:
        return "Never states it", "", "no line with poll-open context and a time range"
    exp = EXPECTED["polling_hours"]

    # ASYMMETRIC BURDEN OF PROOF. A statement of the statutory hours is accepted
    # wherever it appears with poll context - it needs no disambiguation, since
    # 7-19 is right for the statewide election regardless of what else the page
    # mentions. Applying the other-election veto here instead cost real recall:
    # Brazos says "On election day, polls are open 7 a.m. - 7 p.m." and was
    # scored "never states it" because an unrelated date sat in the same window.
    for o, c, raw, ptype, ln, ctx in judged:
        if o == exp["open"] and c == exp["close"]:
            return "Matches expected", f"[{ptype}] {ln[:110]}", f"parsed {o}:00-{c}:00"

    # Only now, for a DIFFERING value, must we prove which election it describes.
    # Reject anything anchored to another date - including a month-day with no
    # year ("February 22nd & 23rd") and dash dates ("10-20-2025"), neither of
    # which parse_dates() sees.
    OTHER_DATE = re.compile(
        rf"\b(?:{MON_RE})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?\b|\b\d{{1,2}}-\d{{1,2}}-\d{{4}}\b", re.I)
    for o, c, raw, ptype, ln, ctx in judged:
        dates = parse_dates(ctx)
        if EXPECTED["election_date"] in dates:
            return ("States something else", f"[{ptype}] {ln[:110]}",
                    f"parsed {o}:00-{c}:00 on a Nov 3 2026 line, expected 7:00-19:00")
        if dates or OTHER_DATE.search(ctx):
            continue                     # about some other election - not judged
        return ("States something else", f"[{ptype}] {ln[:110]}",
                f"parsed {o}:00-{c}:00, expected 7:00-19:00")
    return ("Never states it", "",
            "time ranges found, but all anchored to a non-statewide election")


def check_election_date(pages):
    exp = EXPECTED["election_date"]
    seen = []
    for ptype, lines in pages:
        for i, ln in enumerate(lines):
            ds = parse_dates(ln)
            if not ds:
                continue
            ctx = window(lines, i)
            if not ELECTION_DAY_CTX.search(ctx):
                continue
            for d in ds:
                if d == exp:
                    return "Matches expected", f"[{ptype}] {ln[:110]}", f"{d}"
                # only future statewide-plausible dates count as a competing claim
                if d[0] >= 2026 and not LOCAL_ELECTION_CTX.search(ctx):
                    seen.append((d, ptype, ln))
    if seen:
        future = [x for x in seen if x[0] >= AS_OF]
        if future:
            d, ptype, ln = future[0]
            return "States something else", f"[{ptype}] {ln[:110]}", f"states {d}, expected {exp}"
        d, ptype, ln = max(seen, key=lambda x: x[0])
        return STALE, f"[{ptype}] {ln[:110]}", f"latest date stated is {d}, already past"
    return "Never states it", "", "no election-day date found in election context"


def check_registration_deadline(pages):
    exp = EXPECTED["registration_deadline"]
    seen = []
    for ptype, lines in pages:
        for i, ln in enumerate(lines):
            ctx = window(lines, i)
            if not (REG_TOPIC.search(ctx) and REG_CTX.search(ctx)):
                continue
            for d in parse_dates(ln) or parse_dates(ctx):
                if d == exp:
                    return "Matches expected", f"[{ptype}] {ln[:110]}", f"{d}"
                if d[0] >= 2026:
                    seen.append((d, ptype, ln))
    if seen:
        future = [x for x in seen if x[0] >= AS_OF]
        if future:
            d, ptype, ln = future[0]
            return "States something else", f"[{ptype}] {ln[:110]}", f"states {d}, expected {exp}"
        d, ptype, ln = max(seen, key=lambda x: x[0])
        return STALE, f"[{ptype}] {ln[:110]}", f"latest date stated is {d}, already past"
    return "Never states it", "", "no date near registration-deadline language"


def check_early_voting_window(pages):
    start_exp, end_exp = EXPECTED["early_voting_window"]
    seen = []
    for ptype, lines in pages:
        for i, ln in enumerate(lines):
            ctx = window(lines, i, 1, 3)
            if not EV_CTX.search(ctx):
                continue
            ds = [d for d in parse_dates(ctx) if d[0] >= 2026]
            if len(ds) < 2:
                continue
            if start_exp in ds and end_exp in ds:
                return "Matches expected", f"[{ptype}] {ln[:110]}", f"{start_exp}..{end_exp}"
            # Only a claim ABOUT THE NOVEMBER WINDOW counts as a competing
            # value. Texas ran a March primary, a May uniform election, a May
            # runoff and June runoffs in 2026, and every one of those publishes
            # its own early-voting dates; treating those as a wrong November
            # window produced 82 spurious flags on the first pass.
            in_oct = [d for d in ds if d[0] == 2026 and d[1] == 10]
            names_general = EXPECTED["election_date"] in ds or re.search(
                r"november\s+3,?\s+2026|general election", ctx, re.I)
            if in_oct or names_general:
                seen.append((ds[:2], ptype, ln))
    if seen:
        future = [x for x in seen if max(x[0]) >= AS_OF]
        if future:
            ds, ptype, ln = future[0]
            return "States something else", f"[{ptype}] {ln[:110]}", \
                   f"states {ds}, expected {start_exp}..{end_exp}"
        ds, ptype, ln = max(seen, key=lambda x: max(x[0]))
        return STALE, f"[{ptype}] {ln[:110]}", f"latest window stated is {ds}, already past"
    return "Never states it", "", "no date pair near early-voting language"


CHECKS = {
    "polling_hours": check_polling_hours,
    "election_date": check_election_date,
    "registration_deadline": check_registration_deadline,
    "early_voting_window": check_early_voting_window,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    counties = sorted(p.name for p in SNAP.iterdir() if p.is_dir())
    rows = []
    for c in counties:
        pages = load_pages(c)
        for fact in FACTS:
            verdict, ev, why = CHECKS[fact](pages)
            rows.append({"county": c, "fact": fact, "fact_label": FACT_LABEL[fact],
                         "verdict": verdict, "matched_text": ev, "why": why,
                         "pages_captured": len(pages)})
    dest = OUT / "tx_facts.csv"
    with dest.open("w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)

    import collections
    print(f"{len(counties)} counties x {len(FACTS)} facts = {len(rows)} rows -> "
          f"{dest.relative_to(ROOT)}\n")
    for fact in FACTS:
        t = collections.Counter(r["verdict"] for r in rows if r["fact"] == fact)
        print(f"  {FACT_LABEL[fact]:<24} "
              f"match={t['Matches expected']:>3}  "
              f"differs={t['States something else']:>3}  "
              f"stale={t[STALE]:>3}  "
              f"never={t['Never states it']:>3}")
    states = collections.Counter()
    for c in counties:
        # STALE does not count as stated: a page showing a past election does
        # not tell a voter the current value.
        n = sum(1 for r in rows if r["county"] == c
                and r["verdict"] in ("Matches expected", "States something else"))
        states[n] += 1
    print("\n  facts stated per county:",
          ", ".join(f"{k}:{states[k]}" for k in sorted(states, reverse=True)))


if __name__ == "__main__":
    main()
