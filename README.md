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

Scope: the **124 counties** in `manifest/targets.csv`, tracked in two batches via a
`batch` column. The code is data-driven, so scaling toward 254 is a manifest
change, not a code change.

| batch | counties | Phase 1 starting point |
|---|---|---|
| **1** | 24 | homepages were pre-verified; only the 4 election page types needed discovery |
| **2** | 100 | nothing verified — the homepage *and* the 4 election pages were discovered and verified |

Everything after Phase 1 — artifacts, normalization, rendering, storage, cadence —
is **identical for both batches**; they run through the same pipeline.

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

**124 counties · 620 manifest rows · 381 pages actually captured · 239 recorded gaps.**

How many counties have each page type (as of the last audit):

| page type | captured | batch 1 (of 24) | batch 2 (of 100) | `external` | why the rest are gaps |
|---|---|---|---|---|---|
| `homepage` | **124 / 124** | 24 | 100 | 0 | — every county has one |
| `elections` | **121 / 124** | 23 | 98 | 14 | King has no HTML election pages at all; Brazoria + Henderson are bot-blocked so couldn't be crawled |
| `polling` | **48 / 124** | 15 | 33 | 16 | mostly folded into the elections page, or published only as a per-election PDF |
| `early_voting` | **42 / 124** | 10 | 32 | 14 | same — vote-center counties often have no standalone EV page |
| `results` | **46 / 124** | 16 | 30 | 21 | small counties post results as PDFs; metros use Clarity ENR portals (hence the high `external` count) |

Per-county completeness — most counties are *not* 5/5, and that's the expected shape:

| pages captured | counties | typical profile |
|---|---|---|
| 5 / 5 | 29 | metros & large counties with a dedicated elections operation |
| 4 / 5 | 17 | usually missing a standalone `early_voting` page |
| 3 / 5 | 15 | mid-size counties |
| 2 / 5 | 60 | rural — homepage + one elections page, everything else in PDFs |
| 1 / 5 | 3 | homepage only (e.g. King County publishes nothing else as HTML) |

The 239 gaps break down as: 140 "no distinct page found" (folded into another page),
45 "candidate is non-HTML" (PDF-only), 10 unreachable, 8 uncrawlable because the
homepage is bot-blocked, and a handful of one-offs. Every gap row carries its reason
in `notes`.

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
publishes. Current tree: 124 county dirs → 381 page dirs → 1,143 files (~34 MB).

```
tx-county-watch/
├── manifest/
│   └── targets.csv                  ← the one source of truth: 620 rows
│                                      (county, batch, page_type, url, external,
│                                       notes + 6 audit columns)
└── snapshots/                       ← overwritten in place every run; history is in git
    │
    ├── harris/                      ← 4 of 5 types exist
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
    ├── loving/                      ← 2 of 5 — typical rural county
    │   ├── homepage/
    │   ├── elections/
    │   └── (no polling/, early_voting/ or results/)
    │
    ├── king/                        ← 1 of 5 — publishes no election HTML at all
    │   └── homepage/
    │
    └── … 121 more counties
```

Because each page type is its own directory, `git log -p -- 'snapshots/*/early_voting/page.txt'`
gives you every early-voting change across all 124 counties in one stream.

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

### Batch 2 (100 counties, nothing known)

Three steps, run in order:

```bash
# 1. Find + verify each county's official homepage
.venv/bin/python scripts/discover_homepages.py
# 2. Crawl each homepage for the 4 election page types
.venv/bin/python scripts/discover_pages.py --workers 8
# 3. Merge the results into manifest/targets.csv (idempotent)
.venv/bin/python scripts/merge_batch2.py
```

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

> **Batch 2 needs a human pass.** Its URLs were auto-discovered. Sort
> `targets.csv` by `flag_for_review` and skim `audit_confidence` / `audit_reason`,
> and treat notes containing `weak match — review` or `using per-election hub page`
> as the first things to check.

### Verifying / auditing the manifest

`scripts/audit_targets.py` re-fetches every URL fresh (plain→headless, same as the
pipeline) and audits whether the content actually belongs to the intended county +
page type, by checking for identity keywords (county name, county seat) and
page-type keywords. It writes the findings **back into `targets.csv`** as extra
columns (the pipeline ignores unknown columns):

| column | meaning |
|---|---|
| `county` / `batch` | county name; `1` or `2` (see the batch table at the top) |
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
    targets.csv              # THE manifest: 124 counties x 5 page types = 620 rows
    audit-report.md          # broken + flagged rows from the last audit
    batch2_homepages.csv     # Phase 1 (batch 2) intermediate: discovered homepages
    batch2_targets_draft.csv # Phase 1 (batch 2) intermediate: discovered election pages
  snapshots/<county>/<page_type>/{page.html,page.txt,meta.json}
                             # 124 county dirs -> 381 page dirs -> 1,143 files
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
