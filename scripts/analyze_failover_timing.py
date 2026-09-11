#!/usr/bin/env python3
"""Reconstruct, from the commit series, when a page left its steady state and came back.

Ported from `fl-county-watch/scripts/analyze_failover_timing.py`. The detector is
unchanged: same size-band episode test, same median steady-state estimator, same
capture-failure classification, same onset/offset clustering. Only the plumbing
differs (see "What is different here"), so a Texas cluster and a Florida cluster
mean the same thing and can be put in the same table.

**Why this repo needs it.** Every synchronized cluster Florida found was confined
to one web platform, across counties that were not adjacent and spanned the whole
rurality range -- the thing they shared was a vendor, not a region. Texas is the
sharper test of that, because 167 of its 254 county sites run ezTask Titanium,
distributed through the Texas Association of Counties, and 113 say so in a footer
credit. A single push there moves two-thirds of a state.

### What is different from the Florida version

  * `--ref` reads the commit series from any ref (`origin/main`) without checking
    it out. This repo's snapshot runs land on `main` while analysis work sits on a
    branch, so the freshest captures are usually not in the working tree. Blob
    specs are `<sha>:<path>` and therefore commit-absolute; only `targets.csv` had
    to be read through git as well.
  * Cluster rows carry the counties' web platform, read from
    `analysis/output/tx_covariates.csv`. Florida leaves that to a later join; here
    the vendor is the question, so it is reported inline. It annotates and never
    gates -- a cluster is a cluster whether or not its platform is known.
  * Page types are the five captured for this repo's whole history. The sixth,
    `voter_registration`, was added recently enough that most of the series
    predates it, and a target whose window opens mid-history cannot supply the
    before/during/after an episode needs -- it would add gaps, not episodes.

Usage:
    python scripts/analyze_failover_timing.py
    python scripts/analyze_failover_timing.py --ref origin/main
    python scripts/analyze_failover_timing.py --since 2026-08-01 --band 0.4
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import statistics
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EPISODES_OUT = ROOT / "manifest" / "tx-failover-episodes.csv"
CLUSTERS_OUT = ROOT / "manifest" / "tx-failover-clusters.csv"
COVARIATES = ROOT / "analysis" / "output" / "tx_covariates.csv"

PAGE_TYPES = ("homepage", "elections", "polling", "early_voting", "results")


def slug(county: str) -> str:
    """Snapshot directory name for a county.

    Must stay identical to snapshot.py's rule (`lower()`, spaces to underscores) or
    every lookup silently misses and the run reports no episodes at all. Texas has
    twenty-odd two-word counties -- "El Paso" is `el_paso`, "Deaf Smith" is
    `deaf_smith`.
    """
    return county.strip().lower().replace(" ", "_")


def _git(*args: str) -> str:
    return subprocess.run(("git", *args), cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout


def snapshot_commits(ref: str, since: str | None,
                     until: str | None) -> list[tuple[str, datetime]]:
    """Commits on `ref` that touched snapshots/, oldest first.

    Restricted to commits touching snapshots/ so analysis-only commits (a figure, a
    README edit) don't enter the series as points: they carry no new capture, and
    counting them would stretch every reported bound.
    """
    cmd = ["log", "--format=%H\t%aI", ref]
    if since:
        cmd.append(f"--since={since}")
    if until:
        cmd.append(f"--until={until}")
    cmd += ["--", "snapshots"]
    out = []
    for line in _git(*cmd).splitlines():
        if not line.strip():
            continue
        sha, when = line.split("\t")
        out.append((sha, datetime.fromisoformat(when)))
    # git log is newest-first; sort explicitly so index arithmetic below means
    # "chronological neighbour".
    return sorted(out, key=lambda r: r[1])


def read_targets(ref: str) -> list[tuple[str, str]]:
    """(county, page_type) pairs from the manifest as it exists on `ref`.

    Read through git rather than off disk: the working tree may sit on a branch
    whose manifest has targets the captures on `ref` never covered, and every such
    target would be reported as a gap.
    """
    rows = csv.DictReader(io.StringIO(_git("show", f"{ref}:manifest/targets.csv")))
    return sorted({(r["county"].strip(), r["page_type"].strip()) for r in rows
                   if r["page_type"].strip() in PAGE_TYPES})


def read_platforms() -> dict[str, str]:
    """county slug -> web platform, for annotating clusters. Empty if unavailable."""
    if not COVARIATES.exists():
        return {}
    with COVARIATES.open(encoding="utf-8") as fh:
        return {slug(r["county"]): r["platform"].strip()
                for r in csv.DictReader(fh)}


def state_matrix(commits, targets):
    """(county, page_type) -> per-commit (blob sha, byte size), None where absent.

    One `git cat-file --batch-check` for the whole grid. Per-cell calls would be
    tens of thousands of processes; this is one, and `--batch-check` gives size
    without ever materializing a blob.
    """
    specs = [f"{sha}:snapshots/{slug(c)}/{pt}/page.txt"
             for sha, _ in commits for c, pt in targets]
    proc = subprocess.run(("git", "cat-file", "--batch-check"), cwd=ROOT,
                          input="\n".join(specs), capture_output=True, text=True)
    lines = proc.stdout.splitlines()
    if len(lines) != len(specs):
        raise SystemExit(f"cat-file returned {len(lines)} lines for {len(specs)} specs")

    matrix = {t: [] for t in targets}
    i = 0
    for _sha, _when in commits:
        for t in targets:
            parts = lines[i].split()
            i += 1
            matrix[t].append((parts[0], int(parts[2]))
                             if len(parts) == 3 and parts[1] == "blob" else None)
    return matrix


def classify_episodes(episodes, commits) -> None:
    """Tag each episode `county_change`, `page_removed` or `capture_failure`, in place.

    A size-band detector cannot tell "the county replaced its site" from "we failed
    to fetch the site" — both collapse the byte count. Left unclassified this script
    would report a blocked run as county behaviour, which is the single most
    misleading thing it could do. So every episode is checked against the
    `meta.json` captured alongside it.

    Status has to be read for WHOSE failure it is, and a 404 is not a capture
    failure — in Florida, 17 of one cluster's 44 episodes were `404 / 0 bytes`
    because deep URLs stopped resolving while a replacement page was up. That is
    the finding, not a fetch problem:

      * `error` set (timeout, reset)     -> capture_failure  (our side)
      * 403 / 429 / 5xx                  -> capture_failure  (blocked or server down)
      * 200 with a body under 200 bytes  -> capture_failure  (empty success)
      * 404 / 410                        -> page_removed     (the county's side)
      * 200 with a plausible body        -> county_change

    The 200-byte floor applies only to 200s: a real minimal election-night page runs
    800-1,000 characters, a stored error body runs 0-30, and nothing observed falls
    between.
    """
    specs = [f"{commits[ep['start_idx']][0]}:snapshots/{slug(ep['county'])}"
             f"/{ep['page_type']}/meta.json" for ep in episodes]
    if not specs:
        return
    proc = subprocess.run(("git", "cat-file", "--batch"), cwd=ROOT,
                          input="\n".join(specs), capture_output=True, text=True)
    # --batch emits "<sha> blob <size>\n<payload>\n" per spec; walk it by declared
    # length rather than by line, because JSON payloads contain newlines.
    out, pos, text = [], 0, proc.stdout
    for _ in specs:
        nl = text.find("\n", pos)
        if nl < 0:
            break
        header = text[pos:nl].split()
        if len(header) == 3 and header[1] == "blob":
            size = int(header[2])
            out.append(text[nl + 1:nl + 1 + size])
            pos = nl + 1 + size + 1
        else:
            out.append(None)
            pos = nl + 1

    for ep, payload in zip(episodes, out):
        status = err = None
        if payload:
            try:
                meta = json.loads(payload)
                status, err = meta.get("http_status"), meta.get("error")
            except json.JSONDecodeError:
                pass
        failures, notes = [], []
        if err:
            failures.append(f"error={err[:60]}")
        if status in (403, 429) or (status is not None and status >= 500):
            failures.append(f"http_status={status}")
        if status == 200 and ep["min_bytes"] < 200:
            failures.append(f"empty 200 body={ep['min_bytes']}B")
        removed = status in (404, 410)
        if removed:
            notes.append(f"http_status={status}; body={ep['min_bytes']}B")

        if failures:
            ep["episode_class"] = "capture_failure"
            ep["episode_evidence"] = "; ".join(failures)
        elif removed:
            ep["episode_class"] = "page_removed"
            ep["episode_evidence"] = "; ".join(notes)
        else:
            ep["episode_class"] = "county_change"
            ep["episode_evidence"] = "200, no error, plausible body"


def find_episodes(series, band: float) -> list[dict]:
    """Maximal runs where size is outside +/- `band` of the target's median size.

    Median over the whole window is the steady-state estimator: it is unmoved by an
    episode that occupies a minority of snapshots, which is precisely the shape being
    looked for. It does assume the page is in its normal state most of the time.

    A run needs an in-band observation before AND after it. An unterminated trailing
    run is a page that changed and has not come back — a different phenomenon, and
    one we cannot yet classify, so it is dropped rather than reported as an episode.
    """
    seen = [(i, cell[0], cell[1]) for i, cell in enumerate(series) if cell]
    if len(seen) < 3:
        return []
    steady = statistics.median(s for _, _, s in seen)
    if steady <= 0:
        return []

    def in_band(size: int) -> bool:
        return abs(size - steady) <= band * steady

    episodes, run = [], []
    prior_in_band = None          # last in-band observation before the current run
    for idx, blob, size in seen:
        if in_band(size):
            if run:
                episodes.append({
                    "start_idx": run[0][0], "end_idx": run[-1][0],
                    "n_commits": len(run),
                    "states": {b for _, b, _ in run},
                    "steady_bytes": int(steady),
                    "episode_bytes": run[0][2],
                    "min_bytes": min(s for _, _, s in run),
                    "prior_blob": prior_in_band[1] if prior_in_band else None,
                    "restored_blob": blob,
                })
                run = []
            prior_in_band = (idx, blob, size)
        elif prior_in_band is not None:
            # Only start a run once a steady state has been observed, so a target
            # whose window opens mid-episode isn't reported with a bogus onset.
            run.append((idx, blob, size))
    return episodes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="HEAD",
                    help="ref to read the commit series from (default HEAD; use "
                         "origin/main when snapshots land on a branch you are not on)")
    ap.add_argument("--since", help="only commits after this date")
    ap.add_argument("--until", help="only commits before this date")
    ap.add_argument("--band", type=float, default=0.4,
                    help="fractional size deviation from median that counts as "
                         "out of steady state (default 0.4 = +/-40%%)")
    ap.add_argument("--min-cluster", type=int, default=3,
                    help="counties sharing one onset/offset before it's a cluster")
    args = ap.parse_args()

    commits = snapshot_commits(args.ref, args.since, args.until)
    if len(commits) < 3:
        raise SystemExit(f"only {len(commits)} snapshot commits in range — "
                         "an episode needs a before, a during and an after")
    targets = read_targets(args.ref)
    platforms = read_platforms()

    print(f"ref {args.ref}: {len(commits)} snapshot commits, "
          f"{commits[0][1]:%Y-%m-%d %H:%M} .. {commits[-1][1]:%Y-%m-%d %H:%M}")
    print(f"{len(targets)} manifest targets, band +/-{args.band:.0%}\n")

    matrix = state_matrix(commits, targets)
    captured = sum(1 for s in matrix.values() if any(s))
    print(f"{captured} targets have captures in this window "
          f"({len(targets) - captured} gaps)\n")

    found = []
    for (county, page_type), series in matrix.items():
        for ep in find_episodes(series, args.band):
            ep["county"], ep["page_type"] = county, page_type
            found.append(ep)
    classify_episodes(found, commits)

    episode_rows = []
    for ep in sorted(found, key=lambda e: (e["start_idx"], e["county"])):
        si, ei = ep["start_idx"], ep["end_idx"]
        last_normal, first_changed = commits[si - 1][1], commits[si][1]
        last_changed = commits[ei][1]
        first_restored = commits[ei + 1][1] if ei + 1 < len(commits) else None
        steady = ep["steady_bytes"]
        episode_rows.append({
            "county": ep["county"], "page_type": ep["page_type"],
            "platform": platforms.get(slug(ep["county"]), ""),
            "steady_bytes": steady, "episode_bytes": ep["episode_bytes"],
            "min_bytes": ep["min_bytes"],
            "shrink_pct": round(100 * (1 - ep["min_bytes"] / steady), 1),
            "snapshots_in_episode": ep["n_commits"],
            "distinct_states_in_episode": len(ep["states"]),
            "changed_after": last_normal.isoformat(),
            "changed_by": first_changed.isoformat(),
            "restored_after": last_changed.isoformat(),
            "restored_by": first_restored.isoformat() if first_restored else "",
            "min_duration_hours": round(
                (last_changed - first_changed).total_seconds() / 3600, 1),
            "max_duration_hours": round(
                ((first_restored or last_changed) - last_normal).total_seconds() / 3600, 1),
            "episode_class": ep["episode_class"],
            "episode_evidence": ep["episode_evidence"],
            "returned_to_exact_prior_state":
                str(ep["prior_blob"] is not None
                    and ep["prior_blob"] == ep["restored_blob"]).lower(),
            "onset_idx": si, "offset_idx": ei,
        })

    _write(EPISODES_OUT, episode_rows, drop_idx=True)
    print(f"wrote {EPISODES_OUT} ({len(episode_rows)} episodes)\n")

    # --- synchronization -----------------------------------------------------
    # Same onset snapshot AND same offset snapshot = the same push. Keyed on commit
    # index, not wall-clock, so the grouping is exact.
    clusters = defaultdict(list)
    for r in episode_rows:
        clusters[(r["onset_idx"], r["offset_idx"])].append(r)

    cluster_rows = []
    for cid, (_key, members) in enumerate(
            sorted(clusters.items(),
                   key=lambda kv: -len({m["county"] for m in kv[1]})), 1):
        counties = sorted({m["county"] for m in members})
        if len(counties) < args.min_cluster:
            continue
        plats = sorted({m["platform"] for m in members if m["platform"]})
        cluster_rows.append({
            "cluster": cid, "n_counties": len(counties), "n_targets": len(members),
            "changed_after": members[0]["changed_after"],
            "changed_by": members[0]["changed_by"],
            "restored_after": members[0]["restored_after"],
            "restored_by": members[0]["restored_by"],
            "onset_window_hours": _hours(members[0]["changed_after"],
                                         members[0]["changed_by"]),
            "offset_window_hours": _hours(members[0]["restored_after"],
                                          members[0]["restored_by"]),
            # page_removed counts as county behaviour: a deep URL 404ing while a
            # replacement page is up is the phenomenon, not a fetch problem.
            "cluster_class": ("capture_failure"
                              if any(m["episode_class"] == "capture_failure"
                                     for m in members)
                              else "county_change"),
            "targets_200": sum(1 for m in members
                               if m["episode_class"] == "county_change"),
            "targets_404": sum(1 for m in members
                               if m["episode_class"] == "page_removed"),
            "page_types": ",".join(sorted({m["page_type"] for m in members})),
            "median_shrink_pct": statistics.median(m["shrink_pct"] for m in members),
            "n_platforms": len(plats),
            "platforms": ",".join(plats),
            "counties": ",".join(counties),
        })

    _write(CLUSTERS_OUT, cluster_rows)
    print(f"wrote {CLUSTERS_OUT} ({len(cluster_rows)} clusters of "
          f">= {args.min_cluster} counties)\n")

    for c in cluster_rows:
        tag = ("REAL county change" if c["cluster_class"] == "county_change"
               else "CAPTURE FAILURE — not county behaviour")
        print(f"  cluster {c['cluster']} [{tag}]: {c['n_counties']} counties, "
              f"{c['n_targets']} targets ({c['page_types']})")
        print(f"    changed  between {_fmt(c['changed_after'])} and "
              f"{_fmt(c['changed_by'])}   ({c['onset_window_hours']}h window)")
        if c["restored_by"]:
            print(f"    restored between {_fmt(c['restored_after'])} and "
                  f"{_fmt(c['restored_by'])}   ({c['offset_window_hours']}h window)")
        print(f"    median shrink {c['median_shrink_pct']}%   "
              f"({c['targets_200']} targets served a replacement, "
              f"{c['targets_404']} went 404)")
        print(f"    platforms ({c['n_platforms']}): {c['platforms'] or 'unidentified'}")
        print(f"    {c['counties']}\n")

    if not cluster_rows:
        print("  no synchronized episode reached the cluster threshold.")

    # Episodes that are NOT part of any cluster are ordinary single-county activity;
    # naming the count keeps the cluster figure honest about its denominator.
    clustered = {c for r in cluster_rows for c in r["counties"].split(",")}
    solo = [r for r in episode_rows if r["county"] not in clustered]
    print(f"{len(solo)} episodes in counties outside any cluster "
          f"(ordinary single-county changes)")

    # Episode incidence by platform. Denominator is captured targets, so a platform
    # with many counties cannot look fragile just for being common. Two figures,
    # because they disagree sharply and answer different questions: the SHARE of
    # targets that ever had an episode is how widespread instability is, episodes
    # PER TARGET is how often it recurs. A platform with a few chronically flapping
    # sites scores low on the first and high on the second.
    if platforms:
        per_plat = defaultdict(lambda: [0, 0, set()])
        for t, series in matrix.items():
            if not any(series):
                continue
            per_plat[platforms.get(slug(t[0]), "") or "unidentified"][0] += 1
        for r in episode_rows:
            slot = per_plat[r["platform"] or "unidentified"]
            slot[1] += 1
            slot[2].add((r["county"], r["page_type"]))
        print("\nepisode incidence by platform")
        print(f"  {'platform':26s} {'targets':>7s} {'episodes':>8s} "
              f"{'targets w/ any':>14s} {'eps/target':>10s}")
        for plat, (n_t, n_e, hit) in sorted(per_plat.items(), key=lambda kv: -kv[1][1]):
            print(f"  {plat:26s} {n_t:7d} {n_e:8d} "
                  f"{len(hit):9d} ({100 * len(hit) / n_t:4.1f}%) {n_e / n_t:10.2f}")


def _hours(a: str, b: str) -> float | str:
    if not a or not b:
        return ""
    return round((datetime.fromisoformat(b)
                  - datetime.fromisoformat(a)).total_seconds() / 3600, 1)


def _fmt(iso: str) -> str:
    return f"{datetime.fromisoformat(iso):%m-%d %H:%M}" if iso else "-"


def _write(path: Path, rows: list[dict], drop_idx: bool = False) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = [k for k in rows[0] if not (drop_idx and k.endswith("_idx"))]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
