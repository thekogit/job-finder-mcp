# DEVIATIONS LOG (JS-MCP-001)

This log records any deviation from manual specifications as required by Section 0.2 and Section 2.5.

| ID | Section | Deviation | Reason | Approved By |
|---|---|---|---|---|
| DEV-001 | 3.1 | Dual HTTP/2 and HTTP/1.1 client transport with automatic fallback | Grupa Pracuj (`pracuj.pl`, `theprotocol.it`) uses Akamai bot management that returns HTTP 403 when negotiating HTTP/2 with Python httpx (fingerprinted h2 settings/frames), while responding HTTP 200 over HTTP/1.1. Added HTTP/1.1 transport routing for these hosts and auto-fallback on 403. | Operator (Automatic Section 0.2 rule) |

