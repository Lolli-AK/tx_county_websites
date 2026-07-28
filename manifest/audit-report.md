# targets.csv audit report

- OK (live): 378
- Broken: 4
- Flagged for review: 11
- Gaps (no URL): 238

## Broken

| county | page_type | status | reason | url |
|---|---|---|---|---|
| Galveston | homepage | 403 | [headless] HTTP 403 | https://www.galvestoncountytx.gov/ |
| Brazoria | homepage | 403 | [headless] HTTP 403 | https://www.brazoriacountytx.gov/ |
| Childress | homepage | 500 | [headless] HTTP 500 | https://www.childresstx.us/ |
| Henderson | homepage | 403 | [headless] HTTP 403 | https://www.henderson-county.com/ |

## Flagged for review

| county | page_type | confidence | reason | url |
|---|---|---|---|---|
| Hidalgo | early_voting | uncertain | [headless] only partial match — 'Hidalgo' in domain \| title="EV LOCATIONS" | https://hidalgoelections.maps.arcgis.com/apps/instant/nearby/index.html?appid=ca66194e256342bca592007a24e0c953 |
| Williamson | polling | uncertain | [headless] only partial match — county name 'Williamson' in page | https://www.wilcotx.gov/VoterLookup |
| Aransas | elections | uncertain | [headless] thin content (0 chars); only partial match — 'Aransas' in domain | https://www.aransascountytx.gov/electionadmin/ |
| Calhoun | polling | uncertain | [plain] only partial match — county name 'Calhoun' in page \| title="March 5, 2026 Primary Election Information - Calhoun County Texas" | https://www.calhouncotx.org/march-5-2026-primary-election-information/ |
| Culberson | polling | uncertain | [plain] only partial match — county name 'Culberson' in page; seat 'Van Horn' in page \| title="Culberson County, Texas" | https://www.co.culberson.tx.us/page/Elections.information |
| Culberson | early_voting | uncertain | [plain] only partial match — county name 'Culberson' in page; seat 'Van Horn' in page \| title="Culberson County, Texas" | https://www.co.culberson.tx.us/page/Elections.information |
| Hays | early_voting | uncertain | [plain] only partial match — county name 'Hays' in page; seat 'San Marcos' in page \| title="Current Elections \| Hays County, TX" | https://www.hayscountytx.gov/255/Current-Elections |
