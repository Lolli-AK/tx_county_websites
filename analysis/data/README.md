# Reference data (not tracked)

The CSVs this directory expects are USDA ERS **County-Level Data Sets** and the
**Rural-Urban Continuum Codes**. They are public, large (~35 MB together), and
redownloadable, so they are gitignored rather than committed.

| file | source |
|---|---|
| `rucc2023.csv` | USDA ERS Rural-Urban Continuum Codes 2023 |
| `Education2023.csv` | USDA ERS County-Level Data Sets — Education |
| `PovertyEstimates.csv` | USDA ERS County-Level Data Sets — Poverty |
| `Unemployment2023.csv` | USDA ERS County-Level Data Sets — Unemployment |

Rural-Urban Continuum Codes direct link:

    https://ers.usda.gov/sites/default/files/_laserfiche/DataFiles/53251/Ruralurbancontinuumcodes2023.csv

The others are on the ERS County-Level Data Sets download page.

**Two gotchas, both handled in `analysis/join_rucc.py`:** the files are **Latin-1**,
not UTF-8 (they contain "Doña Ana County, NM", whose ñ is a bare 0xF1 byte that makes
a UTF-8 read raise part-way through), and the RUCC file is **long-format** —
`Attribute`/`Value` rows that need pivoting before use.
