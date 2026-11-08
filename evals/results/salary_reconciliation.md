# Salary reconciliation (fixtures)

- Date: 2026-11-08
- Command: `python -m evals.salary_reconciliation`
- Bands with board-published structured numbers: 33
- **Reconciled: 33/33**
- Per check: extracted 33/33, matches_board 33/33, consistent 33/33, round_trip 33/33
- Contract types as extracted: b2b 26, unknown 7

Scope: this checks the arithmetic and the extraction against the board's own numbers.
It does not check gross/net: no fixture band states it, so `uop_gross` and `b2b_net`
comparison bases are unavailable for every band here (see README, salary filter).

| Origin | Board min | Board max | Period | Cur | Contract | Reconciled | Note |
|---|---|---|---|---|---|---|---|
| solidjobs/listing_1.json#35338 | 26900.0 | 33600.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#37990 | 30200.0 | 36100.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#37991 | 20200.0 | 26900.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#37994 | 23500.0 | 31100.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#37992 | 20200.0 | 26900.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#35339 | 23500.0 | 26900.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#33306 | 28600.0 | 38600.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#35333 | 20200.0 | 26900.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#33308 | 28600.0 | 30200.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#37984 | 23500.0 | 26900.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#33303 | 12000.0 | 15000.0 | month | PLN | unknown | yes |  |
| solidjobs/listing_1.json#37983 | 24000.0 | 32000.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#36662 | 12000.0 | 15000.0 | month | PLN | unknown | yes |  |
| solidjobs/listing_1.json#36660 | 12000.0 | 15000.0 | month | PLN | unknown | yes |  |
| solidjobs/listing_1.json#33301 | 12000.0 | 15000.0 | month | PLN | unknown | yes |  |
| solidjobs/listing_1.json#37978 | 18500.0 | 26900.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#37838 | 15100.0 | 19200.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#37837 | 30200.0 | 37000.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#37832 | 21800.0 | 26000.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#37834 | 21800.0 | 26000.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#37835 | 21800.0 | 26000.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#37826 | 20200.0 | 26900.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#37824 | 26900.0 | 30200.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#37831 | 25200.0 | 27700.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#37827 | 25200.0 | 28600.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#38907 | 19300.0 | 20200.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#38906 | 16800.0 | 20200.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#38905 | 16800.0 | 20200.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#38903 | 23500.0 | 28600.0 | month | PLN | b2b | yes |  |
| solidjobs/listing_1.json#38904 | 23500.0 | 26900.0 | month | PLN | b2b | yes |  |
| nofluffjobs/detail_1.html | 27000.0 | 27000.0 | month | PLN | unknown | yes |  |
| nofluffjobs/detail_2.html | 200.0 | 200.0 | hour | PLN | unknown | yes |  |
| nofluffjobs/detail_3.html | 170.0 | 170.0 | hour | PLN | unknown | yes |  |
