# targets.csv audit report

**124 counties | 620 rows | 377 live | 4 broken | 239 gaps | 11 flagged**

## Coverage by page type

| page type | batch 1 | batch 2 | total |
|---|---|---|---|
| `homepage` | 24/24 | 100/100 | 124/124 |
| `elections` | 23/24 | 98/100 | 121/124 |
| `polling` | 15/24 | 33/100 | 48/124 |
| `early_voting` | 10/24 | 32/100 | 42/124 |
| `results` | 16/24 | 30/100 | 46/124 |

## Health by batch

| batch | counties | live | broken | gaps | flagged |
|---|---|---|---|---|---|
| 1 | 24 | 87 | 1 | 32 | 3 |
| 2 | 100 | 290 | 3 | 207 | 8 |

## Why rows are gaps

| reason | rows |
|---|---|
| no distinct page found | 140 |
| candidate is non-HTML | 45 |
| candidate unreachable | 10 |
| could not crawl — homepage blocked/unreachable | 8 |
| no county-specific page found | 3 |
| EV published only as PDF | 1 |
| EV shares the current-election page; no distinct URL | 1 |
| vote centers cover EV; no distinct EV page | 1 |
| same VoterLookup tool; EV per-election PDFs in Docum | 1 |
| same kerr-county-elections page; EV as per-election  | 1 |

## Broken (needs a new URL)

| batch | county | page_type | status | reason | url |
|---|---|---|---|---|---|
| 1 | Galveston | homepage | 403 | [headless] HTTP 403 | https://www.galvestoncountytx.gov/ |
| 2 | Brazoria | homepage | 403 | [headless] HTTP 403 | https://www.brazoriacountytx.gov/ |
| 2 | Childress | homepage | 500 | [headless] HTTP 500 | https://www.childresstx.us/ |
| 2 | Henderson | homepage | 403 | [headless] HTTP 403 | https://www.henderson-county.com/ |

## Flagged for review (7)

Grouped by page type — a whole type flagging together usually means a systematic discovery problem rather than {n} unrelated ones.

### `elections` (1)

| batch | county | confidence | reason | url |
|---|---|---|---|---|
| 2 | Aransas | uncertain | [headless] thin content (0 chars); only partial match — 'Aransas' in domain | https://www.aransascountytx.gov/electionadmin/ |

### `polling` (3)

| batch | county | confidence | reason | url |
|---|---|---|---|---|
| 1 | Williamson | uncertain | [headless] only partial match — county name 'Williamson' in page | https://www.wilcotx.gov/VoterLookup |
| 2 | Calhoun | uncertain | [plain] only partial match — county name 'Calhoun' in page \| title="March 5, 2026 Primary Election Information - Calhoun County Texas" | https://www.calhouncotx.org/march-5-2026-primary-election-information/ |
| 2 | Culberson | uncertain | [plain] only partial match — county name 'Culberson' in page; seat 'Van Horn' in page \| title="Culberson County, Texas" | https://www.co.culberson.tx.us/page/Elections.information |

### `early_voting` (3)

| batch | county | confidence | reason | url |
|---|---|---|---|---|
| 1 | Hidalgo | uncertain | [headless] only partial match — 'Hidalgo' in domain \| title="EV LOCATIONS" | https://hidalgoelections.maps.arcgis.com/apps/instant/nearby/index.html?appid=ca66194e256342bca592007a24e0c953 |
| 2 | Culberson | uncertain | [plain] only partial match — county name 'Culberson' in page; seat 'Van Horn' in page \| title="Culberson County, Texas" | https://www.co.culberson.tx.us/page/Elections.information |
| 2 | Hays | uncertain | [plain] only partial match — county name 'Hays' in page; seat 'San Marcos' in page \| title="Current Elections \| Hays County, TX" | https://www.hayscountytx.gov/255/Current-Elections |

