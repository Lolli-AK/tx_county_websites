# tx-county-watch

Snapshots a fixed set of **Texas county election web pages** on a schedule and
stores each run as a **git commit**, so their content can be **diffed over time** —
specifically to see how pages change **before and after an election**.

This is the ["git scraping"](https://simonwillison.net/2020/Oct/9/git-scraping/)
pattern: one commit per run, `git diff` / `git log` are the history UI.

Design priorities (in order):

1. **Lightweight, text-based, diff-friendly artifacts.** No PDFs, screenshots, or WARC.
2. **Deterministic output** — re-running against an unchanged site produces a **zero diff**.
3. **Git is the datastore.** History lives in commits, not dated folders.

Scope: **all 254 Texas counties** — the complete set. Counties carry a `batch`
label recording only how their homepage was obtained; the running code treats all
254 uniformly from `manifest/targets.csv`.

| batch | counties | Phase 1 starting point |
|---|---|---|
| **1** | 24 | homepages pre-verified; only the 4 election page types needed discovery |
| **2** | 100 | nothing verified — homepage *and* 4 election pages discovered |
| **3** | 130 | nothing verified — homepage *and* 4 election pages discovered |

Everything after Phase 1 — artifacts, normalization, rendering, storage, cadence —
is **identical for every batch**; they all run through the same pipeline.

**Nothing hardcodes a county list or count.** `manifest/counties.csv`
(`county, seat, batch, homepage`) is the seed of truth and `manifest/targets.csv`
is what the pipeline iterates; the count is always `len(manifest)`. Adding,
removing or correcting a county is a **manifest edit, not a code change** — see
[Editing the manifest](#editing-the-manifest). (The two `scripts/_build_*.py`
files are one-shot generators kept as provenance for how the seed was assembled;
they are not part of any run.)

---

## What it captures

Five target page types per county:

| type | what |
|---|---|
| `homepage` | county front page (alert banners, election countdowns) |
| `elections` | elections / voter-info landing page |
| `polling` | polling locations / vote centers |
| `early_voting` | early voting schedule & locations |
| `results` | election results / returns — **usually a third-party portal on another domain, JS-rendered** (tagged `external`) |

Not every county has a distinct page for every type. Small rural counties often
fold everything into one page or post PDFs (out of scope). **A missing target is
expected data, not an error** — it's recorded as a gap in the manifest.

## Coverage

**254 counties · 1,270 manifest rows · 747 pages captured · 523 recorded gaps.**

How many counties have each page type:

| page type | captured | b1 (24) | b2 (100) | b3 (130) | `external` | why the rest are gaps |
|---|---|---|---|---|---|---|
| `homepage` | **254 / 254** | 24 | 100 | 130 | 0 | — every county has one |
| `elections` | **247 / 254** | 23 | 98 | 126 | 23 | King publishes no HTML election pages; 6 others are bot-blocked so couldn't be crawled |
| `polling` | **82 / 254** | 15 | 33 | 34 | 23 | usually folded into the elections page, or published only as a per-election PDF |
| `early_voting` | **74 / 254** | 10 | 32 | 32 | 21 | same — vote-center counties often have no standalone EV page |
| `results` | **90 / 254** | 16 | 30 | 44 | 33 | small counties post PDFs; metros use Clarity ENR portals (hence the high `external` count) |

Per-county completeness — most counties are *not* 5/5, and that is the expected
shape of Texas, not under-discovery:

| pages captured | counties | typical profile |
|---|---|---|
| 5 / 5 | 49 | metros & large counties with a dedicated elections operation |
| 4 / 5 | 31 | usually missing a standalone `early_voting` page |
| 3 / 5 | 37 | mid-size counties |
| 2 / 5 | **130** | rural — homepage + one elections page, everything else in PDFs |
| 1 / 5 | 7 | homepage only (e.g. King County publishes nothing else as HTML) |

Texas is mostly rural, so **captured pages grow sublinearly with county count**:
going from 124 to 254 counties roughly doubled the counties but took captured pages
from 381 to 747, because the added counties are overwhelmingly 2/5.

The 523 gaps break down as: 353 "no distinct page found" (folded into another page),
94 "candidate is non-HTML" (PDF-only), 20 uncrawlable because the homepage is
bot-blocked, 15 unreachable, and a handful of one-offs. **Every gap row carries its
reason in `notes`** — a gap is recorded data, not a failure.

## What it stores (per captured page)

Three text artifacts per page, under `snapshots/<county>/<page_type>/`:

| file | what | typical size |
|---|---|---|
| **`page.html`** | cleaned, normalized HTML — the structural-diff artifact | ~45 KB |
| **`page.txt`** | visible text only — the primary, lowest-noise human-readable diff | ~4 KB |
| **`meta.json`** | metadata sidecar: requested/final URL, redirect chain, HTTP status, content type, render mode, `external` flag, `fetched_at`, `html_sha256`, `text_sha256`, byte size, title, error | ~0.6 KB |

`meta.json` is what catches "page moved / went down / changed vendor" — changes that
leave no trace in the body.

> The fetch timestamp lives **only** in `meta.json` (`fetched_at`), never in
> `page.html`/`page.txt` — otherwise every run would diff. `meta.json` therefore
> updates every run by design; the stable `html_sha256` / `text_sha256` fields let
> you tell a real content change from a mere re-fetch.

### How the data is laid out on disk

One directory per county, one subdirectory per page type, three files in each.
**A gap creates no directory** — so a county's tree shows at a glance what it
publishes. Current tree: **254 county dirs → 747 page dirs → 2,241 files**.

```
tx-county-watch/
├── manifest/
│   ├── counties.csv                 ← seed of truth: 254 counties (county, seat,
│   │                                   batch, homepage)
│   └── targets.csv                  ← what the pipeline reads: 1,270 rows
│                                      (county, batch, page_type, url, external,
│                                       notes + 6 audit columns)
└── snapshots/                       ← overwritten in place every run; history is in git
    │
    ├── harris/                      
    │   ├── homepage/
    │   │   ├── page.html            ← normalized HTML   (structural diff)
    │   │   ├── page.txt             ← visible text      (content diff)
    │   │   └── meta.json            ← status/URL/hashes (metadata diff)
    │   ├── elections/
    │   │   ├── page.html
    │   │   ├── page.txt
    │   │   └── meta.json
    │   ├── polling/                 ← page.html · page.txt · meta.json
    │   ├── results/                 ← page.html · page.txt · meta.json
    │   └── (no early_voting/)       ← GAP: Harris posts EV only as a PDF,
    │                                  so the directory is simply absent
    │
    ├── loving/                      
    │   ├── homepage/
    │   ├── elections/
    │   └── (no polling/, early_voting/ or results/)
    │
    ├── king/                        
    │   └── homepage/
    │
    └── … 251 more counties
```

Because each page type is its own directory, `git log -p -- 'snapshots/*/early_voting/page.txt'`
gives you every early-voting change across all 254 counties in one stream.

---

## Install

```bash
cd tx-county-watch
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```

Requires Python 3.11+ and `git`.

## Run

```bash
# Snapshot every target in the manifest, then make one git commit:
.venv/bin/python scripts/snapshot.py

# Useful flags:
.venv/bin/python scripts/snapshot.py --no-commit            # write artifacts, don't commit
.venv/bin/python scripts/snapshot.py --workers 12           # more concurrent PLAIN fetches
.venv/bin/python scripts/snapshot.py --batch 3              # one batch only
.venv/bin/python scripts/snapshot.py --resume               # continue an interrupted run
.venv/bin/python scripts/snapshot.py --county harris        # one county (repeatable)
.venv/bin/python scripts/snapshot.py --county harris --page-type results
.venv/bin/python scripts/snapshot.py --no-headless          # never escalate (offline/debug)
```

Each run overwrites the files under `snapshots/` and makes **one commit**. Logs
go to `logs/run-<timestamp>.log` (git-ignored).

---

## How it works

### Fetch strategy — plain-first, escalate-on-empty

1. Fetch with a plain HTTP client (`httpx`), realistic User-Agent, follow redirects.
2. Detect an **empty JS shell**: after cleaning, if visible text < ~500 chars, or
   an "enable JavaScript" marker is present → escalate.
3. Also escalate if the plain fetch **failed outright** — some county sites (e.g.
   Webb) reset non-browser clients via bot protection but serve a real browser fine.
4. **Escalate** to a headless Chromium render (Playwright) that waits for network
   idle, then capture the rendered DOM.
5. The path used is recorded in `meta.json.render_mode` (`plain` | `headless`). A
   page flipping plain↔headless between runs is itself a meaningful change.

Static rural `co.*.tx.us` sites stay on the plain path; big metros and all
`results` portals typically use headless.

### Normalization (why diffs stay clean)

`scripts/normalize.py` applies the **same deterministic transform every run**.
Every rule below was added because it was caught diffing an unchanged site:

- Removes `<script>`, `<style>`, `<noscript>`, `<svg>`, `<iframe>`, `<template>`,
  and HTML comments.
- Strips **ASP.NET WebForms** volatile hidden inputs (`__VIEWSTATE`,
  `__EVENTVALIDATION`, …) — huge and change every request.
- Strips **CSRF / token hidden inputs** (`authenticity_token`, …) and
  `<meta name="csrf-token">`; nulls the `value` of **all other hidden inputs**
  (form/session state, e.g. anti-bot `name="ht"` tokens with embedded timestamps).
- Drops per-request token attributes (`nonce`, `integrity`, `crossorigin`, and any
  attr whose name contains `csrf`/`token`/`nonce`/`session`/`viewstate`).
- Drops inline **`style`** attributes — JS carousels/sliders rewrite
  `left`/`z-index`/`display` as they animate, so the captured DOM would otherwise
  reflect a random animation frame.
- Neutralizes **Cloudflare email obfuscation** (`/cdn-cgi/l/email-protection#…`
  hrefs and `data-cfemail` attrs) and **Akamai edge Reference #** ids on "Access
  Denied" pages — both re-generated per request.
- Removes resource-hint `<link>`s (`preload`/`modulepreload`/`prefetch`/… of
  build-hashed assets) and normalizes **randomized widget ids**
  (`gt-wrapper-<n>` GTranslate, `ivs-gallery-<hex>`).
- Replaces **rotating image hero carousels** (class `slideshow`/`carousel` with an
  image/background-image) with a stable placeholder — some homepages (Lubbock)
  randomize the banner subset *server-side*, which no client stub can fix.
  Text-only alert/countdown banners are left intact.
- Canonicalizes **per-render opaque identifiers** in `id`/`class`/`aria-*`/`data-*`:
  GUIDs (CivicPlus `widgetFAQ(194)<guid>`), long hex (Drupal
  `js-view-dom-id-<hash>`, Travis's `tc-search-<hex>`), and embedded
  **server timestamps** (Elementor's `schedule_server_datetime`). Drops
  always-random `data-drupal-selector`.
- Strips **cache-busting query params** from asset/form URLs (`?ver=` on WordPress
  stylesheets, `?cdv=` on DotNetNuke) and per-session tokens — SharePoint's Office
  viewer packs ~6 session GUIDs plus an epoch stamp into one form `action`.
- Removes **asynchronously injected accessibility overlays** (AudioEye, accessiBe,
  UserWay), which appear or vanish depending on capture timing, and **JS load-state
  classes** on `<html>`/`<body>` (`js`, `fontawesome-i2svg-active`, `wf-active`).
- Drops CivicPlus widget **size classes** (`wide`/`narrow`), which are measured at
  runtime and flap between captures.
- Collapses whitespace and pretty-prints line-oriented HTML for readable `git diff`.

The headless path additionally **neutralizes `setInterval` and pins `Math.random`**
(via a Playwright init script) before page scripts run, so animation loops and
JS-shuffled galleries/ids never vary; **pins the viewport** to 1280x900 so
responsive class names can't flap; and waits `hydration_settle_ms` (default 1500)
after network idle so capture can't land mid-render — Cochran's homepage was
otherwise snapshotted with its literal `{{YEAR}}`/`{{COUNTY}}` template
placeholders still un-interpolated. Non-HTML responses (PDFs) are not parsed —
they're recorded in `meta.json` and left out of the body artifacts. `fetch_plain`
retries on 5xx, since a few county servers (Childress) return intermittent 500s.

> **Site flakiness vs. tool determinism.** A handful of county servers are
> genuinely unstable — Childress alternates 200/404/500 within seconds. When such a
> page diffs between runs, that's the site changing, not normalization leaking:
> check `meta.json.http_status` to tell the two apart.

`page.txt` is `get_text()` with blank-line runs collapsed.

### Determinism test (must pass)

Fetch a page, commit, fetch again immediately (site unchanged) → `git status` must
show **no change** to `page.html` / `page.txt`. Only `meta.json` (timestamp) changes.

```bash
.venv/bin/python scripts/snapshot.py --county loving --county harris --no-commit
git add -A && git commit -m baseline
.venv/bin/python scripts/snapshot.py --county loving --county harris --no-commit
git diff --stat -- '*page.html' '*page.txt'   # <- expect empty
```

**Status at 124 counties (382 fetched targets).** Systematic volatility is handled —
about twenty distinct classes of it were found and fixed by running this test
repeatedly and chasing every diff (see the normalization list above). On a
back-to-back full run, the artifacts that still differ fall into two buckets, and
neither is normalization leaking:

- **Genuine content changes.** Counties really do publish things between runs —
  Brazos posted a public-hearing notice, Hill an office-closure notice. Detecting
  these *is the point of the tool*.
- **Access variance on bot-protected sites.** Delta (Cloudflare) and Aransas
  (Imperva) sometimes serve a challenge or a 403 instead of the page; Childress
  returns intermittent 500s. `meta.json.http_status` tells you immediately when a
  diff is this rather than real content.

So expect a small number of changed files on any given re-run, and read
`meta.json` before concluding a page changed. If a diff is neither of the above,
something volatile survived normalization — find and strip it.

If `page.html`/`page.txt` diff on an unchanged site, something volatile survived
normalization — find and strip it in `normalize.py`.

---

## Reading the diffs

```bash
git log --oneline                      # one line per snapshot run
git show <commit>                      # everything that changed in a run
git log -p -- snapshots/harris/elections/page.txt   # content history of one page

# What changed across an election (pick commits before/after election day):
git diff <before> <after> -- 'snapshots/**/page.txt'

# Ignore the always-changing timestamp; focus on real content:
git diff <before> <after> -- 'snapshots/**/page.txt' 'snapshots/**/page.html'
```

`page.txt` is the best starting point (lowest noise). Drop to `page.html` for
structural changes (links, layout), and check `meta.json` for status/redirect/
render-mode/vendor changes when the body didn't move.

---

## Editing the manifest

Two CSVs, and **no code changes** are ever needed to add, remove or correct a county.

**`manifest/counties.csv`** — the seed of truth. One row per county:

| column | meaning |
|---|---|
| `county` | county name, exactly as it should appear everywhere |
| `seat` | county seat — used as a second identity signal when verifying a site |
| `batch` | `1`, `2` or `3` (provenance of the homepage only) |
| `homepage` | filled for batch 1; blank for batches 2/3, which discover it |

**`manifest/targets.csv`** — what the pipeline actually reads. One row per
(county × page type), so 5 rows per county. Columns are documented in
[Verifying / auditing the manifest](#verifying--auditing-the-manifest); the audit
columns (`verify_status` … `flag_for_review`) are written by `audit_targets.py`
and ignored by the pipeline.

Common edits:

```bash
# Fix one URL: edit that row's `url` in manifest/targets.csv, then re-verify it
.venv/bin/python scripts/audit_targets.py --county hays

# Record that a page type doesn't exist: blank the `url` and say why in `notes`
#   (a row with an empty url is a GAP; notes must explain it — a test enforces this)

# Re-discover a county from scratch
.venv/bin/python scripts/discover_homepages.py --county Hays --batch 2
.venv/bin/python scripts/discover_pages.py --county Hays --batch 2
.venv/bin/python scripts/merge_batch2.py --batch 2

# Then confirm the manifest is still internally consistent
.venv/bin/python -m pytest tests/ -q
```

To add a county beyond the current 254, add a row to `counties.csv`, run discovery
+ merge for its batch, and update `TEXAS_COUNTY_COUNT` in
`tests/test_manifest.py` (the only place a count is asserted — deliberately, so
the scope can't drift silently).

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

26 tests, no network required. They assert the invariants everything else relies on:

- **254 unique counties**, and the three batch labels **partition** them with no
  overlap and nothing left over
- `targets.csv` covers every seeded county with exactly one row per page type
- batch labels agree between the seed and the manifest
- every gap row explains itself in `notes`; `external` is boolean; URLs are http(s)
- artifacts on disk agree with the manifest (3 files per captured page, **no
  directory for a gap**), `meta.json` is well-formed and matches its row
- the fetch timestamp never leaks into `page.html`/`page.txt`
- identity-verification regressions: Harris County's site must not verify as
  "Houston County", Smith County's must not verify as "Tyler County", "Deaf Smith
  County" must not match "Smith County", a staff surname like "Brown" must not be
  read as "Brown County", and tourism/EDC/commercial sites must be rejected

## Phase 1: the manifest

`manifest/targets.csv` (`county, batch, page_type, url, external, notes` + audit
columns) is the foundation. Rows with an empty `url` are **recorded gaps** — the page
type doesn't exist as a distinct HTML page for that county (very common for rural
counties, which publish polling/early-voting as PDFs or fold them into one page).

### Batch 1 (24 counties, homepages known)

`scripts/discover.py` crawls each homepage and scores links to **suggest** candidate
URLs (output: `logs/discover-candidates.json`); a human then curates. The curated
result is reproduced by `scripts/_build_manifest.py`.

```bash
.venv/bin/python scripts/discover.py                # all counties
.venv/bin/python scripts/discover.py --county kerr
```

### Batches 2 and 3 (230 counties, nothing known)

Three steps, run in order:

```bash
# 1. Find + verify each county's official homepage (--batch selects from counties.csv)
.venv/bin/python scripts/discover_homepages.py --batch 3 --workers 10
# 2. Crawl each homepage for the 4 election page types
.venv/bin/python scripts/discover_pages.py --batch 3 --workers 8
# 3. Merge into manifest/targets.csv (idempotent — replaces that batch's rows)
.venv/bin/python scripts/merge_batch2.py --batch 3
```

Results: pattern-probing resolved **90/100** of batch 2 and **115/130** of batch 3;
the ~30 residual counties were finished with targeted web searches.

**`discover_homepages.py`** avoids a web search per county by probing the handful of
domain patterns Texas counties actually use (`co.<county>.tx.us`,
`<county>countytx.gov`, `<county>county.texas.gov`, …), then **verifying the content
is really that county's government site**: county name + Texas/seat signal + at least
one or two *county-government* signals (commissioners court, county judge/clerk,
sheriff, courthouse). That last check matters — without it,
`burnetcountytx.com` (a process-server site) and squatted domains pass a naive
name-match. Unresolved counties are reported for a targeted web search rather than
guessed at.

**`discover_pages.py`** escalates through six strategies, because a plain
homepage crawl alone finds barely half the pages:

1. score links on the homepage;
2. re-render the homepage **headless** (some sites build their whole nav in JS);
3. walk a "Departments"/"Government"/"County Offices" nav page;
4. try the top *four* candidates, not just the best (county sites carry stale 404 links);
5. **promote a dedicated elections portal** when the elections page hands off to one
   (`votedenton.gov`, `burnetcountyelections.com`, `elections.brazoscountytx.gov`);
6. crawl per-election **"Current Elections"** hub pages — on CivicPlus-style county
   sites that's where polling and early-voting detail actually lives.

Statewide and national portals (`sos.state.tx.us`, `votetexas.gov`, `vote411.org`,
`ballotpedia.org`, …) are **rejected** as candidates: they're identical for every
county, so capturing them 100× would add no per-county signal and would
misrepresent a county as having a page it doesn't have.

> **Batches 2 and 3 need a human pass** — ~230 auto-discovered homepages plus their
> election pages. Start from `manifest/audit-report.md`, which groups everything by
> batch and page type; then sort `targets.csv` by `flag_for_review` and skim
> `audit_confidence` / `audit_reason`. Treat notes containing `weak match — review`
> or `using per-election hub page` as the next tier to check.

**What the verifier already catches, so you don't have to.** Auto-discovery on this
scale attracts specific false positives, each of which produced a real wrong answer
before being guarded:

| trap | real example |
|---|---|
| Another county's site (12 counties share a name with a different county's *seat*) | Harris County's site matching **Houston County**; Smith County's matching **Tyler County** |
| Nested county names | "Deaf Smith County" contains the string "Smith County" |
| Staff surnames (counties are named after people) | "Brown" + "County Clerk" on adjacent nav lines read as "Brown County" |
| Tourism / economic-development / chamber sites | `libertycounty.org` is a **visitor** site; `woodcountytx.com` is an **EDC** |
| Private listing directories | `polkcountytx.com` is a listing service, not `polktx.gov` |
| Commercial sites carrying the county name | `burnetcountytx.com` is a **process server** |
| Squatted / expired domains | `childresscountytexas.us` redirects to a law-marketing page |
| Wrong-state counties | Anderson, Montgomery, Johnson, Hunt, Jack, Knox, Polk, Wood all exist in other states |

### Verifying / auditing the manifest

`scripts/audit_targets.py` re-fetches every URL fresh (plain→headless, same as the
pipeline) and audits whether the content actually belongs to the intended county +
page type, by checking for identity keywords (county name, county seat) and
page-type keywords. It writes the findings **back into `targets.csv`** as extra
columns (the pipeline ignores unknown columns):

| column | meaning |
|---|---|
| `county` / `batch` | county name; `1`, `2` or `3` (see the batch table at the top) |
| `page_type` | `homepage` · `elections` · `polling` · `early_voting` · `results` |
| `url` | the target; **empty = a recorded gap**, with the reason in `notes` |
| `external` | `true` when the URL's registered domain differs from the county homepage's |
| `notes` | provenance: how the URL was found, or why the row is a gap |
| `verify_status` | `ok` (live) · `broken` (4xx/5xx/error/PDF) · `gap` (no URL) |
| `http_status` | HTTP status of the (final) response |
| `final_url` | filled only when the request redirected elsewhere |
| `audit_confidence` | `confident` · `likely` · `uncertain` · `broken` · `gap` |
| `audit_reason` | why it looks right/wrong (which keywords matched, title, warnings) |
| `flag_for_review` | `yes` when a human should eyeball it |

```bash
.venv/bin/python scripts/audit_targets.py            # audit all, rewrite CSV
.venv/bin/python scripts/audit_targets.py --county hidalgo
```

A human-readable summary of broken + flagged rows is written to
`manifest/audit-report.md`. `confident`/`likely` rows matched both an identity and
a topic signal; `uncertain`+`flag_for_review=yes` rows need a look (typically JS
map/lookup apps that have no verifiable text, or blocked pages).

> **Per-election URL caveat:** some results portals (Clarity ENR, LiveVoterTurnout)
> use per-election numeric IDs that change each election. Where possible the manifest
> uses the stable portal *index* URL; check `notes` and refresh IDs each cycle.

---

## Running at 254-county scale

A full run touches **747 targets** and, counting retries and headless escalations,
makes well over a thousand requests against small county servers. Three things make
that sustainable:

**Bounded concurrency on the plain path only.** `--workers` (default 8) parallelizes
plain HTTP fetches — measured **3.6× faster** on a sample. Headless renders stay
**serialized behind a lock**, deliberately: Playwright's sync API isn't thread-safe,
and parallel Chromium renders contend for CPU, which shifts hydration timing. That
timing is exactly what the determinism work depends on, so speed does not get to
compromise it. Verified: two consecutive 8-worker runs produce a zero diff.

**Politeness.** Every fetch waits `request_delay_ms` (250) plus up to
`request_jitter_ms` (250) of jitter. The jitter matters with a worker pool —
without it, workers synchronize into bursts.

**Resumability.** Progress is written to `logs/checkpoint.json` as each target
completes. If a run dies part-way, `--resume` skips what already finished instead of
refetching everything; a clean finish deletes the checkpoint. The Actions workflow
retries once with `--resume` on failure.

| knob (`config.json` → `fetch`) | default | what it does |
|---|---|---|
| `workers` | 8 | concurrent plain fetches (headless always serial) |
| `request_delay_ms` / `request_jitter_ms` | 250 / 250 | politeness pause before each fetch |
| `plain_retries` | 2 | plain attempts; also retries 5xx |
| `hydration_settle_ms` / `hydration_max_wait_ms` | 2000 / 6000 | post-networkidle DOM-quiescence window |
| `interstitial_max_wait_ms` | 45000 | how long to wait out a bot challenge |
| `js_shell_min_chars` | 500 | below this, escalate to headless |

Timings and storage, measured:

| | 124 counties | 254 counties |
|---|---|---|
| targets captured | 381 | **747** |
| run time (Actions, serial) | ~10.5 min | ~22 min projected |
| run time (8 plain workers) | — | substantially lower; headless is the floor |
| growth per run | ~0.1 MB | ~0.2–0.9 MB |
| 1 year daily | ~45–167 MB | **~90–330 MB** |

GitHub recommends staying under 1 GB, so a year of daily snapshots is comfortable.
`.git` compresses aggressively because unchanged pages reuse the same blob — which
is precisely why the normalization work matters: volatile markup would mint a new
blob for every page on every run.

## Running on GitHub Actions vs. locally — a data-quality caveat

The pipeline is identical either way, but **where it runs changes what some sites
return**, because Actions runners use datacenter IPs that bot protection treats
more suspiciously than a residential connection. Measured by diffing a local run
against the first Actions run:

| effect | pages | what it means |
|---|---|---|
| `HTTP 202` on Clarity ENR results portals | 13 | **Benign.** Content is complete and byte-identical to the local run — Clarity just answers `202` instead of `200`. Don't read these as failures. |
| `HTTP 403` then challenge **cleared** | 3 (Cherokee) | **Content is fine.** The initial navigation was refused, the security check then passed, and the real page was captured. `http_status` stays `403` because that was the genuine first response. |
| `HTTP 403` and challenge **never cleared** | 4 (Delta) | **Real data loss.** Cloudflare blocks the runner IP outright; the captured body is the security-check page. |

> **Filter on `error`, not on `http_status`.** Because a challenge can clear *after*
> a 403, status alone can't tell good data from junk — Cherokee and Delta are both
> `403`, but only Delta's body is worthless. The reliable test is:
> `meta.json.error == "bot_challenge_not_cleared…"` → discard; `error == null` →
> the body is real content whatever the status says.

So a page appearing "broken" in the GitHub-run data may simply be blocked from that
IP range. Two things make this unambiguous rather than silently wrong:

- `meta.json.error` is set to **`bot_challenge_not_cleared`** whenever the captured
  body is a security-check page, so those rows can be filtered out rather than
  mistaken for "the county took the page down".
- `interstitial_max_wait_ms` (default 45s) is the budget for waiting a challenge
  out. It's deliberately much longer than the ~2s these take locally; raise it in
  `config.json` if runs keep coming back blocked.

If you need the handful of blocked counties, run `snapshot.py` locally for just
those and push — the artifacts and commits are the same shape either way:

```bash
.venv/bin/python scripts/snapshot.py --county delta --county cherokee && git push
```

## Phase 3: scheduling

Cadence is **not hardcoded** in the pipeline — the scheduler decides frequency.

**GitHub Actions** (`.github/workflows/snapshot.yml`): a daily baseline cron that
always runs, plus an every-3-hours cron gated on the repository variable
`ELECTION_WINDOW`. Set `ELECTION_WINDOW=true` (Settings → Secrets and variables →
Actions → Variables) to raise cadence for the election window; set it back to `false`
afterwards. No code change. `config.json` documents the crons and the fetch knobs.

**Local cron** alternative:

```cron
# daily baseline at 08:00
0 8 * * * cd /path/to/tx-county-watch && .venv/bin/python scripts/snapshot.py >> logs/cron.log 2>&1
# election window: every 3 hours (enable by uncommenting)
# 0 */3 * * * cd /path/to/tx-county-watch && .venv/bin/python scripts/snapshot.py >> logs/cron.log 2>&1
```

---

## Layout

```
tx-county-watch/
  manifest/
    counties.csv             # seed of truth: 254 counties (county, seat, batch, homepage)
    targets.csv              # THE manifest: 254 counties x 5 page types = 1,270 rows
    audit-report.md          # broken + flagged rows from the last audit
    batch2_homepages.csv     # Phase 1 (batch 2) intermediate: discovered homepages
    batch2_targets_draft.csv # Phase 1 (batch 2) intermediate: discovered election pages
  snapshots/<county>/<page_type>/{page.html,page.txt,meta.json}
                             # 254 county dirs -> 747 page dirs -> 2,241 files
                             # (see "How the data is laid out on disk" above)
  scripts/
    snapshot.py              # main: fetch -> normalize -> write -> commit
    normalize.py             # shared deterministic cleaning transform
    audit_targets.py         # verify + content-audit every manifest URL
    discover.py              # Phase 1 helper, batch 1 (link scoring)
    discover_homepages.py    # Phase 1, batch 2: find + verify county homepages
    discover_pages.py        # Phase 1, batch 2: find the 4 election pages
    merge_batch2.py          # merge batch 2 discovery into targets.csv
    _build_manifest.py       # one-shot: reproduces the curated batch 1 rows
  config.json                # cadence + fetch knobs
  logs/                      # run logs (git-ignored)
  .github/workflows/snapshot.yml
```

## Out of scope

PDF capture/parsing, screenshots/visual diffing, full-site crawling, counties
beyond the manifest, and alerting (diffs are reviewed via git).
