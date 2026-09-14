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

# A date RANGE elides the repeated parts: the year, and often the month, appear
# only on the LAST endpoint ("October 19 - 30, 2026"). DATE_RE requires
# month+day+year adjacent, so it saw ONE endpoint or none, and this check needs a
# PAIR -- which is how a page literally reading "Early voting October 19 - 30,
# 2026" was recorded as "no date pair near early-voting language".
#
# Deliberately ONE regex, so the whole range must be contiguous. Letting a year
# reach backwards across a sentence would invent windows out of unrelated dates
# ("Register by October 5. Early voting ends October 30, 2026").
_RANGE_SEP = r"(?:-|–|—|\bto\b|\bthrough\b|\bthru\b|\buntil\b|\btill\b)"
DATE_RANGE_RE = re.compile(
    rf"\b({MON_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*{_RANGE_SEP}\s*"
    rf"(?:({MON_RE})\.?\s+)?(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)
NUMRANGE_RE = re.compile(
    rf"\b(\d{{1,2}})/(\d{{1,2}})\s*{_RANGE_SEP}\s*(\d{{1,2}})/(\d{{1,2}})/(\d{{4}})\b")

# A BARE date omits the year entirely ("Register by October 5", "Early voting
# October 19-30"). To a reader that is a complete claim, because the year is
# established elsewhere on the page; to a month+day+year regex it is invisible.
# This was a larger recall hole than the range elision it sits next to.
#
# The year is RESOLVED, never guessed: a bare date is emitted only when the
# surrounding text pins exactly ONE year, or the caller supplies a hint. Text
# carrying two years is ambiguous and yields nothing, so a 2024 archive link
# cannot drag an undated deadline into the current cycle.
BARE_RANGE_RE = re.compile(
    rf"\b({MON_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*{_RANGE_SEP}\s*"
    rf"(?:({MON_RE})\.?\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\b", re.I)
BARE_DATE_RE = re.compile(rf"\b({MON_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.I)
YEAR_RE = re.compile(r"\b(20\d{2})\b")
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

# A line that NAMES election day (or the general-election date) is unambiguous
# on its face. The vetoes below exist to stop AMBIGUOUS hours being read as
# election-day hours; applied to a self-identifying line they only destroy
# recall. A census of all 202 "never states polling hours" counties found 10
# that state the statutory 7-7 in so many words: 6 lost to the early_voting
# page-type skip (counties routinely put an "Election Day" block on that page),
# 3 to an EV_CTX veto firing on an adjacent nav label ("Early Voting Reports"),
# and 1 to POLL_CTX not recognising "General Election Tuesday 11/03/2026".
ELECTION_DAY_LINE = re.compile(
    r"\belection\s*day\b|\bnovember\s+3(?:rd)?,?\s*2026\b|\b11/0?3/2026\b", re.I)

REG_CTX = re.compile(
    r"(?:last day|deadline|final day|must (?:be )?register|register(?:ed)? by|"
    r"registration deadline|last day to register)", re.I)
REG_TOPIC = re.compile(r"regist", re.I)
ELECTION_DAY_CTX = re.compile(
    r"election day|general election|next election|uniform election|"
    r"upcoming election|november \d{1,2},? 2026", re.I)


def _mon_num(tok: str) -> int | None:
    mon = tok.lower().rstrip(".")
    return MONTHS.get(mon) or ABBR.get(mon)


def _mask(text: str, regexes) -> str:
    """Blank out spans already consumed, preserving offsets."""
    chars = list(text)
    for rx in regexes:
        for m in rx.finditer(text):
            for i in range(m.start(), m.end()):
                chars[i] = " "
    return "".join(chars)


def _resolve_year(text: str, year_hint: int | None) -> int | None:
    years = {int(y) for y in YEAR_RE.findall(text)}
    if len(years) == 1:
        return years.pop()
    return year_hint            # ambiguous or absent: only an explicit hint


def parse_dates(text: str, year_hint: int | None = None) -> list[tuple[int, int, int]]:
    out = []
    # Ranges first: their endpoints are invisible to DATE_RE. The trailing
    # endpoint is usually a complete date and so is found twice -- hence the
    # de-duplication below, which matters because callers test len(dates) >= 2
    # and a double-counted single date would read as a pair.
    for m in DATE_RANGE_RE.finditer(text):
        m1, d1, m2, d2, y = m.groups()
        mm1 = _mon_num(m1)
        mm2 = _mon_num(m2) if m2 else mm1
        if mm1 and mm2:
            out.append((int(y), mm1, int(d1)))
            out.append((int(y), mm2, int(d2)))
    for m in NUMRANGE_RE.finditer(text):
        a1, b1, a2, b2, y = (int(g) for g in m.groups())
        if 1 <= a1 <= 12 and 1 <= b1 <= 31 and 1 <= a2 <= 12 and 1 <= b2 <= 31:
            out.append((y, a1, b1))
            out.append((y, a2, b2))
    for m in DATE_RE.finditer(text):
        mm = _mon_num(m.group(1))
        if mm:
            out.append((int(m.group(3)), mm, int(m.group(2))))
    for m in NUMDATE_RE.finditer(text):
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= a <= 12 and 1 <= b <= 31:
            out.append((y, a, b))

    # Bare dates last, over the text with every year-bearing match blanked out,
    # so a complete date is never re-read as a yearless one.
    year = _resolve_year(text, year_hint)
    if year:
        masked = _mask(text, (DATE_RANGE_RE, NUMRANGE_RE, DATE_RE, NUMDATE_RE))
        for m in BARE_RANGE_RE.finditer(masked):
            m1, d1, m2, d2 = m.groups()
            mm1 = _mon_num(m1)
            mm2 = _mon_num(m2) if m2 else mm1
            if mm1 and mm2:
                out.append((year, mm1, int(d1)))
                out.append((year, mm2, int(d2)))
        masked = _mask(masked, (BARE_RANGE_RE,))
        for m in BARE_DATE_RE.finditer(masked):
            mm = _mon_num(m.group(1))
            if mm:
                out.append((year, mm, int(m.group(2))))

    seen, uniq = set(), []
    for d in out:
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


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


def evidence(lines: list[str], i: int, want, before: int = 2, after: int = 2) -> str:
    """The line that actually states `want`, not merely the line we were on.

    Dates are parsed from a context WINDOW, so the line under the cursor is
    often a fragment of markup - snapshots recorded "**********", "rd" and a
    bare "\u25b2" as the evidence for real, correct date matches. Auditing the
    output by hand was impossible until this looked for the right line.
    """
    lo, hi = max(0, i - before), min(len(lines), i + after + 1)
    for j in list(range(i, hi)) + list(range(lo, i)):
        ln = lines[j].strip()
        if ln and want in parse_dates(ln, want[0]):
            return ln
    return lines[i].strip()


def window(lines: list[str], i: int, before: int = 2, after: int = 2) -> str:
    return " ".join(lines[max(0, i - before): i + after + 1])


# ---------------------------------------------------------------- checks
OPEN_CLOSE_RE = re.compile(
    r"open\w*[^.]{0,40}?(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?[^.]{0,40}?"
    r"clos\w+[^.]{0,30}?(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?", re.I)


def _open_close(line: str) -> list[tuple[int, int, str]]:
    """"Polls will open at 7 am and close at 7 pm" states a range without ever
    writing one; TIME_RANGE_RE needs a dash or a "to" and so saw nothing."""
    out = []
    for m in OPEN_CLOSE_RE.finditer(line):
        h1, ap1, h2, ap2 = int(m.group(1)), m.group(3).lower(), int(m.group(4)), m.group(6).lower()
        out.append(((h1 % 12) + (12 if ap1 == "p" else 0),
                    (h2 % 12) + (12 if ap2 == "p" else 0), m.group(0)))
    return out


def check_polling_hours(pages):
    """Election-day poll hours only. Returns (verdict, evidence, why)."""
    judged = []
    exp = EXPECTED["polling_hours"]
    for ptype, lines in pages:
        for i, ln in enumerate(lines):
            ranges = parse_time_ranges(ln) or _open_close(ln)
            if not ranges:
                continue
            # The vetoes are bypassed ONLY for the statutory value on a line
            # that names election day. A DIFFERING value still has to earn its
            # way past every defence, so an 8-5 early-voting row cannot slip in.
            # +/-1 line, because markup splits these constantly: Cherokee's
            # "7AM to 7PM" sits alone under "Tuesday 11/03/2026". The EV test
            # stays LINE-scoped, so a 7-7 row in an early-voting day table
            # cannot borrow an "Election Day" heading from its neighbour.
            # Naming election day ON THE LINE settles it: Brazos writes "On
            # election day, polls are open 7 a.m. - 7 p.m." in a sentence that
            # also mentions the early voting period. Borrowing the name from a
            # NEIGHBOUR is weaker, so that path additionally requires the whole
            # +/-1 window to be free of early-voting talk - otherwise Freestone's
            # early-voting 7-7 row is captured by the "ELECTION DAY HOURS:"
            # heading sitting on the next line.
            win = window(lines, i, 1, 1)
            named = bool(ELECTION_DAY_LINE.search(ln)) or bool(
                ELECTION_DAY_LINE.search(win)
                and not EV_CTX.search(win) and not EV_CTX.search(ln))
            plain = (named
                     and any((o, c) == (exp["open"], exp["close"])
                             for o, c, _ in ranges))
            if ptype == "early_voting" and not plain:
                continue                 # defence 2: wrong voting mode entirely
            ctx = window(lines, i)
            if not plain:
                if BUSINESS_CTX.search(ctx):             # defence 1
                    continue
                if EV_CTX.search(ctx):                   # defence 2
                    continue
                if LOCAL_ELECTION_CTX.search(ctx):       # defence 3
                    continue
                if not POLL_CTX.search(ctx):
                    continue             # no poll-open context: not a claim
            for o, c, raw in ranges:
                # A sub-4-hour window is a meeting, a lunch closure or a single
                # site's slot - never a statewide poll day. Coke's "12:00pm-1:00pm".
                if c - o < 4:
                    continue
                judged.append((o, c, raw, ptype, ln, ctx))
    if not judged:
        return "Never states it", "", "no line with poll-open context and a time range"

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
            ctx = window(lines, i)
            if not ELECTION_DAY_CTX.search(ctx):
                continue
            # The line may carry a bare "November 3"; the year is on a neighbour.
            ds = parse_dates(ln, _resolve_year(ctx, None))
            if not ds:
                continue
            for d in ds:
                if d == exp:
                    return ("Matches expected",
                            f"[{ptype}] {evidence(lines, i, d)[:110]}", f"{d}")
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
            yh = _resolve_year(ctx, None)
            for d in parse_dates(ln, yh) or parse_dates(ctx, yh):
                if d == exp:
                    return ("Matches expected",
                            f"[{ptype}] {evidence(lines, i, d)[:110]}", f"{d}")
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
    seen, partial = [], False
    for ptype, lines in pages:
        for i, ln in enumerate(lines):
            ctx = window(lines, i, 1, 3)
            if not EV_CTX.search(ctx):
                continue
            ds = [d for d in parse_dates(ctx) if d[0] >= 2026]
            if len(ds) < 2:
                continue
            if start_exp in ds and end_exp in ds:
                return ("Matches expected",
                        f"[{ptype}] {evidence(lines, i, start_exp, 1, 3)[:110]}",
                        f"{start_exp}..{end_exp}")
            # Only a claim ABOUT THE NOVEMBER WINDOW counts as a competing
            # value. Texas ran a March primary, a May uniform election, a May
            # runoff and June runoffs in 2026, and every one of those publishes
            # its own early-voting dates; treating those as a wrong November
            # window produced 82 spurious flags on the first pass.
            # A county that lists early-voting days ONE PER LINE states no
            # window at all; the window's endpoints never share a context
            # window. Every date being inside Oct 19-30 is agreement with the
            # expected window, not a competing claim about it - reporting
            # "states Oct 19..Oct 23" as a conflict was wrong on 11 counties.
            if all(start_exp <= d <= end_exp for d in ds):
                partial = True
                continue
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
    if partial:
        return ("Never states it", "",
                "lists days inside the expected window but never states it")
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
