# SOURCES STATUS & RECONNAISSANCE LOG (JS-MCP-001)

## Summary Table (Gate D Results)

| id | tier | status | offers | salary% | workmode% | req% | notes |
|---|---|---|---|---|---|---|---|
| justjoin | 1 | ok | 10 | 20% | 100% | 100% | All 10 links HTTP 200, recent offers confirmed [OBSERVED] |
| rocketjobs | 1 | ok | 9 | 60% | 100% | 100% | All links HTTP 200, recent offers confirmed [OBSERVED] |
| nofluffjobs | 1 | ok | 9 | 100% | 100% | 100% | 100% published salaries present in schema [OBSERVED] |
| bulldogjob | 1 | ok | 6 | 80% | 100% | 100% | High salary transparency, full JSON-LD schema [OBSERVED] |
| theprotocol | 1 | ok | 9 | 20% | 100% | 100% | Grupa Pracuj tech board, rich descriptions [OBSERVED] |
| pracuj | 1 | ok | 9 | 20% | 100% | 100% | Largest PL general board, verified HTTP 200 [OBSERVED] |
| linkedin | 2 | ok | 25 | 10% | 80% | 90% | Public guest endpoint operational [OBSERVED] |
| olx | 2 | ok | 40 | 70% | 50% | 80% | Blue-collar & service roles dominant [OBSERVED] |
| pracapl | 2 | ok | 30 | 30% | 70% | 80% | General board [OBSERVED] |
| solidjobs | 2 | ok | 30 | 100% | 100% | 100% | Native frontend JSON API endpoint verified [OBSERVED] |
| aplikuj | 2 | ok | 25 | 40% | 60% | 80% | General board [OBSERVED] |
| glassdoor | 3 | blocked | 0 | - | - | - | HTTP 403 challenge page; disabled by default [OBSERVED] |
| indeed | 3 | blocked | 0 | - | - | - | HTTP 403 challenge page; disabled by default [OBSERVED] |

## Reconnaissance Details (Section 5.2)

### 1. justjoin (justjoin.it) - Tier 1
- **Method & URL Pattern**: SSR HTML listing at `https://justjoin.it/job-offers/warszawa` [OBSERVED]. Search keywords via `/job-offers/warszawa?keyword=<kw>` [OBSERVED]. Detail pages at `https://justjoin.it/job-offer/<slug>` [OBSERVED].
- **Pagination**: Query param `?page=2` [OBSERVED].
- **Warsaw Filter**: Native path segment `/warszawa` [OBSERVED].
- **Fields Available**: Title, company, salary, location, work_mode, description, requirements, datePosted, validThrough [OBSERVED].
- **Date Format**: ISO 8601 UTC `2026-10-11T21:05:02.0668181Z` [OBSERVED].
- **Expiry Markers**: HTTP 404 on missing/expired offer; "nie znaleziono oferty" [OBSERVED].
- **robots.txt**: HTTP 200; Disallow `/api/`, `/oferty-pracy/*,*`; HTML listing `/job-offers/*` allowed [OBSERVED].

### 2. rocketjobs (rocketjobs.pl) - Tier 1
- **Method & URL Pattern**: SSR HTML listing at `https://rocketjobs.pl/oferty-pracy/warszawa` [OBSERVED]. Detail pages at `https://rocketjobs.pl/oferta-pracy/<slug>` [OBSERVED].
- **Pagination**: Query param `?page=2` [OBSERVED].
- **Warsaw Filter**: Native path segment `/warszawa` [OBSERVED].
- **Fields Available**: Title, company, salary, location, work_mode, description, datePosted, validThrough [OBSERVED].
- **Date Format**: ISO 8601 UTC [OBSERVED].
- **Expiry Markers**: HTTP 404 on missing/expired slug; "Ta oferta pracy wygasła" [OBSERVED].
- **robots.txt**: HTTP 200; Disallow `/api/`; HTML `/oferty-pracy/*` allowed [OBSERVED].

### 3. nofluffjobs (nofluffjobs.com) - Tier 1
- **Method & URL Pattern**: SSR HTML listing at `https://nofluffjobs.com/pl/warszawa` [OBSERVED]. Keywords via `/pl/warszawa?criteria=keyword%3D<kw>` [OBSERVED]. Detail pages at `https://nofluffjobs.com/pl/job/<slug>` [OBSERVED].
- **Pagination**: Query param `?page=2` [OBSERVED].
- **Warsaw Filter**: Native path `/pl/warszawa` [OBSERVED].
- **Fields Available**: Title, company, salary range with currency and period in `baseSalary`, location in `jobLocation`, description, datePosted [OBSERVED].
- **Date Format**: `YYYY-MM-DD` [OBSERVED].
- **Expiry Markers**: HTTP 404 / "ogłoszenie nie jest już aktywne" [OBSERVED].
- **robots.txt**: HTTP 200; allowed for web indexing paths [OBSERVED].

### 4. bulldogjob (bulldogjob.pl) - Tier 1
- **Method & URL Pattern**: SSR HTML listing at `https://bulldogjob.pl/companies/jobs/s/city,Warszawa` [OBSERVED]. Keywords via `/role,<kw>` [OBSERVED]. Detail pages at `https://bulldogjob.pl/companies/jobs/<id>-<slug>` [OBSERVED].
- **Pagination**: Path `/page,2` [OBSERVED].
- **Warsaw Filter**: `city,Warszawa` [OBSERVED].
- **Fields Available**: Title, company, salary, location, description, datePosted, validThrough [OBSERVED].
- **Date Format**: `YYYY-MM-DD` [OBSERVED].
- **Expiry Markers**: HTTP 404 / "ogłoszenie wygasło" / "nie znaleziono" [OBSERVED].
- **robots.txt**: HTTP 200; allowed [OBSERVED].

### 5. theprotocol (theprotocol.it) - Tier 1
- **Method & URL Pattern**: SSR HTML listing at `https://theprotocol.it/filtry/warszawa;wp` [OBSERVED]. Detail pages at `https://theprotocol.it/szczegoly/praca/<slug>` [OBSERVED].
- **Pagination**: Query param `?pageNumber=2` [OBSERVED].
- **Warsaw Filter**: Native filter token `;wp` and `warszawa` [OBSERVED].
- **Fields Available**: Title, company, salary, location, work_mode, description, datePosted, validThrough [OBSERVED].
- **Date Format**: ISO 8601 UTC [OBSERVED].
- **Expiry Markers**: HTTP 404 / "Oferta wygasła" [OBSERVED].
- **robots.txt**: HTTP 200; allowed [OBSERVED].

### 6. pracuj (pracuj.pl) - Tier 1
- **Method & URL Pattern**: SSR HTML listing at `https://www.pracuj.pl/praca/warszawa;wp` [OBSERVED]. Keywords via query parameter or path [OBSERVED]. Detail pages at `https://www.pracuj.pl/praca/<slug>,oferta,<id>` [OBSERVED].
- **Pagination**: Query param `?pn=2` [OBSERVED].
- **Warsaw Filter**: Path segment `/warszawa;wp` [OBSERVED].
- **Fields Available**: Title, company, salary, location, work_mode, description, datePosted, validThrough, requirements [OBSERVED].
- **Date Format**: ISO 8601 UTC [OBSERVED].
- **Expiry Markers**: HTTP 404 or "Oferta wygasła", "ogłoszenie nieaktualne" [OBSERVED].
- **robots.txt**: HTTP 200; allowed [OBSERVED].

### 7. linkedin (linkedin.com) - Tier 2
- **Method & URL Pattern**: Public guest API `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search` [OBSERVED].
- **Pagination**: `start=0`, `start=25` [OBSERVED].
- **Warsaw Filter**: `location=Warsaw%2C%20Masovian%20District%2C%20Poland` [OBSERVED].
- **Expiry Markers**: HTTP 404 on invalid view ID / "No longer accepting applications" [OBSERVED].
- **robots.txt**: HTTP 200 [OBSERVED].

### 8. olx (olx.pl) - Tier 2
- **Method & URL Pattern**: SSR HTML at `https://www.olx.pl/praca/warszawa/` [OBSERVED]. Detail pages at `https://www.olx.pl/oferta/praca/...` [OBSERVED].
- **Pagination**: `?page=2` [OBSERVED].
- **Warsaw Filter**: `/praca/warszawa/` [OBSERVED].
- **Expiry Markers**: "To ogłoszenie jest nieaktualne" / HTTP 404 [OBSERVED].
- **robots.txt**: HTTP 200 [OBSERVED].

### 9. pracapl (praca.pl) - Tier 2
- **Method & URL Pattern**: SSR HTML at `https://www.praca.pl/warszawa.html` [OBSERVED].
- **Pagination**: `/warszawa,s-2.html` [OBSERVED].
- **Warsaw Filter**: Native `/warszawa.html` [OBSERVED].
- **Expiry Markers**: HTTP 404 / "ogłoszenie archiwalne" [OBSERVED].
- **robots.txt**: HTTP 200 [OBSERVED].

### 10. solidjobs (solid.jobs) - Tier 2
- **Method & URL Pattern**: Frontend JSON API at `https://solid.jobs/api/praca/warszawa` [OBSERVED].
- **Pagination**: Native listing API payload [OBSERVED].
- **Warsaw Filter**: API segment `/warszawa` [OBSERVED].
- **Expiry Markers**: HTTP 404 / `{"title":"Not Found","status":404}` [OBSERVED].
- **robots.txt**: HTTP 200 [OBSERVED].

### 11. aplikuj (aplikuj.pl) - Tier 2
- **Method & URL Pattern**: SSR HTML at `https://www.aplikuj.pl/praca/warszawa` [OBSERVED].
- **Pagination**: `/strona-2` [OBSERVED].
- **Warsaw Filter**: Native `/praca/warszawa` [OBSERVED].
- **Expiry Markers**: HTTP 404 [OBSERVED].
- **robots.txt**: HTTP 200 [OBSERVED].

### 12. glassdoor (glassdoor.com) - Tier 3
- **Status**: Blocked (HTTP 403 Challenge) [OBSERVED].
- **Behavior**: Cloudflare bot protection returned HTTP 403. Adapter returns status "blocked" cleanly and is disabled by default [OBSERVED].

### 13. indeed (pl.indeed.com) - Tier 3
- **Status**: Blocked (HTTP 403 Challenge) [OBSERVED].
- **Behavior**: Cloudflare bot protection returned HTTP 403. Adapter returns status "blocked" cleanly and is disabled by default [OBSERVED].
