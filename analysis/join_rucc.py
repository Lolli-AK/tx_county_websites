#!/usr/bin/env python3
"""Join detected website platform to USDA ERS Rural-Urban Continuum Codes 2023.

Two documented gotchas in the ERS file, both handled here:
  * It is LATIN-1, not UTF-8. It contains "Dona Ana County, NM" with an n-tilde,
    and a UTF-8 read raises UnicodeDecodeError mid-file (byte 0xf1).
  * It is LONG format - one row per (FIPS, Attribute) with Attribute in
    {RUCC_2023, Population_2020, Description} - so it must be pivoted before use.

The join is asserted: every one of the 254 counties must match, or this exits
non-zero rather than silently dropping counties from the figure.

Output: analysis/output/tx_platform_rucc.csv  (adds fips, rucc, rucc_band, pop2020)
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analysis" / "output"

# EXACT five bands, matching the Florida version of this chart so the two are
# directly comparable. Do not re-cut these without re-cutting Florida.
BANDS = {
    1: "Large metro (1M+)",
    2: "Medium metro (250k-1M)",
    3: "Small metro (<250k)",
    4: "Nonmetro, has an urban core",
    5: "Nonmetro, has an urban core",
    6: "Nonmetro, has an urban core",
    7: "Nonmetro, has an urban core",
    8: "Nonmetro, rural",
    9: "Nonmetro, rural",
}
BAND_ORDER = ["Large metro (1M+)", "Medium metro (250k-1M)", "Small metro (<250k)",
              "Nonmetro, has an urban core", "Nonmetro, rural"]


def key(name: str) -> str:
    """Comparison key: drop the ' County' suffix and all non-alphanumerics.

    Handles DeWitt/De Witt and the snapshot slugs' underscores in one step.
    """
    n = re.sub(r"\s+county\s*$", "", name.strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]", "", n.lower())


def main() -> None:
    # --- ERS, latin-1, long -> wide
    src = ROOT / "analysis" / "data" / "rucc2023.csv"
    wide: dict[str, dict] = {}
    with src.open(encoding="latin-1", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("State") != "TX":
                continue
            f = r["FIPS"].strip()
            rec = wide.setdefault(f, {"fips": f, "county_name": r["County_Name"].strip()})
            rec[r["Attribute"].strip()] = r["Value"].strip()
    print(f"ERS TX counties pivoted: {len(wide)}")

    ers_by_key = {}
    for f, rec in wide.items():
        k = key(rec["county_name"])
        if k in ers_by_key:
            sys.exit(f"duplicate ERS key {k!r}")
        ers_by_key[k] = rec

    # --- canonical county names from the manifest, so we join on names rather
    # --- than on directory slugs
    slug_to_name = {}
    with (ROOT / "manifest" / "counties.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            nm = r["county"].strip()
            slug_to_name[nm.lower().replace(" ", "_")] = nm

    rows = list(csv.DictReader((OUT / "tx_platform.csv").open(encoding="utf-8")))
    print(f"platform rows: {len(rows)}")

    unmatched, out = [], []
    for r in rows:
        nm = slug_to_name.get(r["county"], r["county"].replace("_", " ").title())
        k = key(nm)
        rec = ers_by_key.get(k)
        if rec is None:
            unmatched.append((r["county"], nm, k))
            continue
        try:
            rucc = int(float(rec.get("RUCC_2023", "")))
        except ValueError:
            unmatched.append((r["county"], nm, "no RUCC value"))
            continue
        out.append({**r,
                    "county_name": nm,
                    "fips": rec["fips"],
                    "pop2020": rec.get("Population_2020", ""),
                    "rucc": rucc,
                    "rucc_band": BANDS[rucc]})

    if unmatched:
        print("\nUNMATCHED:")
        for u in unmatched:
            print("   ", u)
        sys.exit(f"{len(unmatched)} counties failed to join - fix before plotting")

    assert len(out) == 254, f"expected 254 joined rows, got {len(out)}"
    assert len({r['fips'] for r in out}) == 254, "duplicate FIPS after join"

    dest = OUT / "tx_platform_rucc.csv"
    with dest.open("w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        wr.writeheader()
        wr.writerows(out)

    import collections
    print(f"\nall {len(out)} counties matched -> {dest.relative_to(ROOT)}")
    print("\nRUCC band x county count:")
    for b in BAND_ORDER:
        n = sum(1 for r in out if r["rucc_band"] == b)
        print(f"  {n:>4}  {b}")
    print("\nplatform x band (counts):")
    tab = collections.Counter((r["rucc_band"], r["platform"]) for r in out)
    for b in BAND_ORDER:
        parts = [f"{p}={n}" for (bb, p), n in tab.most_common() if bb == b]
        print(f"  {b}: {', '.join(parts)}")


if __name__ == "__main__":
    main()
