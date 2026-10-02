# The CIRA migration: a live natural experiment inside our study window

**Date:** 2026-09-11 · **Status:** preliminary — one county's quote verified, fleet-wide
policy confirmed from CIRA's own documentation

---

## 1. What CIRA is

Texas county websites are not bought on an open market. They are provisioned through
**TAC CIRA — the County Information Resources Agency** — which is not a vendor but a
**government entity**:

> "CIRA is an interlocal entity as authorized by the Texas Interlocal Cooperation Act,
> Texas Government Code Chapter 791, to provide certain technology services to its
> members."
> — CIRA Services Agreement, Findings ¶1

Operating since 2001. Each member county's **governing body must approve execution of an
Interlocal Participation Agreement** (Findings ¶3), so the decision to join is a recorded
commissioners court vote with a paper trail.

**This corrects an earlier working assumption.** It is not true that counties "never ran a
procurement." They did — collectively, once, through a cooperative purchasing entity they
jointly created. The finding is not an absence of governance. It is a question of
**altitude**: a county decides *whether to join CIRA and which service tier*; **CIRA decides
the platform**. The body legally accountable for publishing election information sits one
level below the body that determines how it gets published.

165 of 254 counties in our corpus run ezTask Titanium, distributed this way.

## 2. A fleet-wide migration is underway right now

CIRA is retiring its **Standard** and **Standard Plus** website packages:

| fact | value | source |
|---|---|---|
| migration deadline | **Dec 31, 2027** | CIRA migration FAQ |
| Standard/Standard Plus replaced by Essential | **Jan 1, 2028** | CIRA migration FAQ |
| platform after migration | **still ezTask** (Essential and Ultimate both) | CIRA website services |
| design templates offered | **three** — Lone Star, Rancher, Bluebonnet | CIRA website services |
| counties on Ultimate | no migration, price increase only | CIRA migration FAQ |

**ezTask is not being replaced.** This is a package and template restructure on the same
platform — which matters, because it means `detect_platform.py` will keep resolving these
counties to ezTask and will *not* flag the change. Our instrument is blind to this event
unless we instrument for it deliberately.

Verified county-level instance — **Hardin County** (packet dated 2025-12-03, commissioners
court agenda 2026-01-27):

- current package Standard, population 58,670, **page count 34**
- one-time migration fee **$8,950**; new annual hosting **$9,550** from Jan 1, 2027
- county chooses to migrate in **2026 or 2027** (two pricing options)
- stated driver: ADA / accessibility compliance

## 3. The finding that matters: pricing creates an incentive to delete pages

The migration fee is **tiered on page count** — Tier 1 (<50 pages), Tier 2 (50–100),
Tier 3 (>100). CIRA therefore advises counties, in writing, to shrink their sites before
migrating:

> "Some counties may be able to reduce their page count before migration, lowering their
> cost."

The named consolidation targets include:

1. **Public notices** — "meeting notices, agendas and minutes; foreclosure notices; court
   dockets; holiday and closure notices" folded into calendar entries
2. **Financial documents** — "budgets, tax rate, utility reports, treasurer's reports,
   check registers" onto one page
3. **Sparse precinct pages** — "all precinct details on a single page" rather than one per
   commissioner and JP precinct
4. **District courts** — individual court pages combined into "one comprehensive page"

CIRA does warn against over-consolidation that harms usability, and states that
"all website content will be retained when the site is migrated." Both things are true at
once: content survives *the migration*, while the fee structure rewards removing content
*before* it. That is not deception — it is a pricing model with a predictable behavioral
consequence, and the consequence is measurable.

On URLs, CIRA is explicit: the main county URL is stable, but **"certain page URLs or
bookmarks might experience some structural changes."** For a longitudinal scraper, that
sentence is the whole risk.

## 4. How this relates to our project

**It is a natural experiment we are already instrumented for.** ~165 counties, staggered
adoption on timing each county chooses, inside our capture window. Page disappearance and
URL drift are what our pipeline already records (`verify_status`, HTTP status,
`redirect_chain`, `final_url`).

**It gives us a second event, so November is no longer the only shot.** The migration and
the general election are independent shocks to the same corpus.

**The election-information risk is specific and testable.** Sparse pages are the stated
consolidation target, and county election pages in small counties are often sparse. A county
maintaining separate `polling` and `early_voting` pages has a direct financial reason to
merge them. Four of our six page types are exactly the kind of thin, single-purpose page the
guidance names.

**Two practical warnings for the pipeline:**

- *Check registers are on the consolidation list.* That is the precise document class that
  produced 25 false positives in `discover_registration.py`. If they get consolidated, our
  discovery false-positive profile shifts mid-study, and re-running discovery before and
  after the migration will not be comparing like with like.
- *CIRA's page count is not our URL count.* Their tiering counts CMS pages; we count fetched
  URLs. Do not treat the two as the same variable.

**A note on the record itself.** Many counties publish commissioners court minutes on CIRA
infrastructure (e.g. `newtools.cira.state.tx.us/page/potter.Court.Minutes`) — and "meeting
notices, agendas and minutes" is item 1 on the consolidation list. The public record of the
migration decision is itself named as content to consolidate.

## 5. Threats to the design

- **One verified quote.** Hardin only. Fleet-wide policy is confirmed from CIRA's own
  documentation, but per-county cost and timing are not.
- **Treatment is not universal.** Ultimate-package counties do not migrate. We have no
  package/tier covariate, and without one the treated group is misspecified.
- **Timing is endogenous.** Counties self-select into 2026 vs 2027, almost certainly on IT
  capacity and budget cycle — the same factors that plausibly drive site quality. This is
  the central identification threat to any diff-in-diff and must be addressed, not assumed
  away.
- **No baseline yet.** Page inventories should be frozen now, before migrations land.

## 6. Next steps

1. **Freeze a baseline page inventory** for all 254 counties. Highest priority; it expires.
2. **Build a court-minutes corpus** — search county sites for "CIRA" in agendas and minutes
   to recover per-county decisions, dates and fees. Confirmed present in Hardin, Hunt,
   Upshur and Austin records.
3. **Add a package/tier covariate** (Standard / Standard Plus / Ultimate) to the manifest.
4. **File a Public Information Act request** (Tex. Gov't Code Ch. 552) for CIRA board
   minutes and the original ezTask vendor selection — still unknown whether an RFP was ever
   run.

## Sources

- CIRA Services Agreement + Hardin County quote — https://newtools.cira.state.tx.us/upload/page/10643/Agenda%20Documents/01-27-2026/Website%20Hosting%20Update.pdf
- CIRA web migration FAQ — https://www.county.org/resources/resource-library/tac-cira/cira-web-migration-faqs
- Consolidating web content — https://www.county.org/resources/resource-library/tac-cira/county-website-migration/cira-consolidating-web-content
- CIRA website services — https://www.county.org/resources/resource-library/tac-cira/website-services
- Interlocal Participation Agreement (Hunt County) — https://apps.huntcounty.net/minutes/LinkedDir/2024/Links%202024-10-22-Regular/19146.pdf
- Resource Service Agreement (Upshur County) — http://records.countyofupshur.com/countyclerk/minutes/LinkedDir/2017/Links%202017-01-13-Regular/262-Resource%20Service%20Agreement.pdf
