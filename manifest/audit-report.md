# targets.csv audit report

**254 counties | 1270 rows | 756 live | 0 broken | 514 gaps | 23 flagged**

## Coverage by page type

| page type | batch 1 | batch 2 | batch 3 | total |
|---|---|---|---|---|
| `homepage` | 24/24 | 100/100 | 130/130 | 254/254 |
| `elections` | 23/24 | 98/100 | 129/130 | 250/254 |
| `polling` | 15/24 | 33/100 | 36/130 | 84/254 |
| `early_voting` | 10/24 | 32/100 | 33/130 | 75/254 |
| `results` | 16/24 | 30/100 | 47/130 | 93/254 |

## Health by batch

| batch | counties | live | broken | gaps | flagged |
|---|---|---|---|---|---|
| 1 | 24 | 88 | 0 | 32 | 2 |
| 2 | 100 | 293 | 0 | 207 | 8 |
| 3 | 130 | 375 | 0 | 275 | 13 |

## Why rows are gaps

| reason | rows |
|---|---|
| no distinct page found | 350 |
| candidate is non-HTML | 94 |
| candidate unreachable | 15 |
| could not crawl — homepage blocked/unreachable | 8 |
| no county-specific page found | 7 |
| EV published only as PDF | 1 |
| EV shares the current-election page; no distinct URL | 1 |
| vote centers cover EV; no distinct EV page | 1 |
| same VoterLookup tool; EV per-election PDFs in Docum | 1 |
| same kerr-county-elections page; EV as per-election  | 1 |

## Flagged for review (23)

Grouped by page type — a whole type flagging together usually means one systematic discovery problem rather than many unrelated ones.

### `homepage` (2)

| batch | county | confidence | reason | url |
|---|---|---|---|---|
| 3 | Newton | uncertain | [plain] POSSIBLE ERROR PAGE (temporarily unavailable); county name 'Newton' in page; seat 'Newton' in page \| homepage keywords: county \| title="Newton County, Texas" | https://www.co.newton.tx.us/ |
| 3 | Shackelford | uncertain | [plain] POSSIBLE ERROR PAGE (under construction); county name 'Shackelford' in page; seat 'Albany' in page \| homepage keywords: county \| title="Shackelford County, Texas" | https://www.shackelfordcounty.org/ |

### `elections` (3)

| batch | county | confidence | reason | url |
|---|---|---|---|---|
| 2 | Aransas | uncertain | [headless] thin content (0 chars); only partial match — 'Aransas' in domain | https://www.aransascountytx.gov/electionadmin/ |
| 3 | Refugio | uncertain | [plain] POSSIBLE ERROR PAGE (under construction); county name 'Refugio' in page; seat 'Refugio' in page \| elections keywords: election, voter, voting, ballot \| title="Refugio County, Texas" | https://www.co.refugio.tx.us/page/refugio.Elections |
| 3 | Starr | uncertain | [plain] only partial match — elections keywords: election, voter, voting, ballot \| title="Voter ID Information" | https://www.harrisvotes.com/Voter/ID |

### `polling` (6)

| batch | county | confidence | reason | url |
|---|---|---|---|---|
| 1 | Williamson | uncertain | [headless] only partial match — county name 'Williamson' in page | https://www.wilcotx.gov/VoterLookup |
| 2 | Aransas | uncertain | [headless] thin content (0 chars); only partial match — 'Aransas' in domain | https://www.aransascountytx.gov/electionadmin/precinctmap.php |
| 2 | Calhoun | uncertain | [plain] only partial match — county name 'Calhoun' in page \| title="March 5, 2026 Primary Election Information - Calhoun County Texas" | https://www.calhouncotx.org/march-5-2026-primary-election-information/ |
| 2 | Culberson | uncertain | [plain] only partial match — county name 'Culberson' in page; seat 'Van Horn' in page \| title="Culberson County, Texas" | https://www.co.culberson.tx.us/page/Elections.information |
| 3 | Refugio | uncertain | [plain] only partial match — county name 'Refugio' in page; seat 'Refugio' in page \| title="Refugio County, Texas" | https://www.co.refugio.tx.us/page/refugio.Elections.CurrentElections |
| 3 | Starr | uncertain | [headless] thin content (76 chars); only partial match — polling keywords: vote center \| title="Vote Centers" | https://www.harrisvotes.com/Vote-Centers |

### `early_voting` (10)

| batch | county | confidence | reason | url |
|---|---|---|---|---|
| 1 | Hidalgo | uncertain | [headless] only partial match — 'Hidalgo' in domain \| title="EV LOCATIONS" | https://hidalgoelections.maps.arcgis.com/apps/instant/nearby/index.html?appid=ca66194e256342bca592007a24e0c953 |
| 2 | Aransas | uncertain | [headless] thin content (0 chars); only partial match — 'Aransas' in domain | https://www.aransascountytx.gov/electionadmin/voteelectinfo.php |
| 2 | Culberson | uncertain | [plain] only partial match — county name 'Culberson' in page; seat 'Van Horn' in page \| title="Culberson County, Texas" | https://www.co.culberson.tx.us/page/Elections.information |
| 2 | Hays | uncertain | [plain] only partial match — county name 'Hays' in page; seat 'San Marcos' in page \| title="Current Elections \| Hays County, TX" | https://www.hayscountytx.gov/255/Current-Elections |
| 3 | McLennan | uncertain | [plain] only partial match — county name 'McLennan' in page; seat 'Waco' in page \| title="Current Election Results \| McLennan County, TX" | https://www.mclennan.gov/546/Current-Election-Results |
| 3 | Pecos | uncertain | [plain] only partial match — county name 'Pecos' in page; seat 'Fort Stockton' in page \| title="General Voter & Election Information – Pecos County" | https://www.co.pecos.tx.us/general-voter-election-information/ |
| 3 | Refugio | uncertain | [plain] only partial match — county name 'Refugio' in page; seat 'Refugio' in page \| title="Refugio County, Texas" | https://www.co.refugio.tx.us/page/refugio.Elections.CurrentElections |
| 3 | Rockwall | uncertain | [plain] only partial match — county name 'Rockwall' in page; seat 'Rockwall' in page \| title="Election Information - Rockwall County, TX Elections" | https://www.rockwallvotes.com/election-information/ |
| 3 | Starr | uncertain | [plain] only partial match — early_voting keywords: early voting, early vote \| title="View information for upcoming Elections" | https://www.harrisvotes.com/Voter/View-information-for-upcoming-Elections |
| 3 | Uvalde | uncertain | [plain] only partial match — county name 'Uvalde' in page; seat 'Uvalde' in page \| title="Election Information \| Uvalde County Elections" | https://www.uvaldecountyelections.com/election-information |

### `results` (2)

| batch | county | confidence | reason | url |
|---|---|---|---|---|
| 2 | Aransas | uncertain | [headless] thin content (0 chars); only partial match — 'Aransas' in domain | https://www.aransascountytx.gov/main/elecres.php |
| 3 | Starr | uncertain | [plain] only partial match — results keywords: election result, results \| title="Election Results" | https://www.harrisvotes.com/Election-Results |

