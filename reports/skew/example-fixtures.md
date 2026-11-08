# Skew report (fixtures)

- Date: 2026-11-08
- Command: `python -m evals.skew.run --fixtures --embedder gemma --report reports/skew/example-fixtures.md`
- Payloads fingerprinted: 55 (api:listing 2, html:listing 18, jsonld:detail 19, next_data:detail 10, next_data:listing 6)

## Structural skew

No alerts.

### Synthetic-mutation self-test: 36/36 detected

| Board | Payload | Mutation | Detected | Alert types |
|---|---|---|---|---|
| bulldogjob | jsonld:detail | renamed_key | yes | renamed_key |
| bulldogjob | jsonld:detail | list_to_dict | yes | container_change |
| bulldogjob | jsonld:detail | casing_change | yes | casing_change |
| bulldogjob | next_data:detail | renamed_key | yes | renamed_key |
| bulldogjob | next_data:detail | list_to_dict | yes | container_change |
| bulldogjob | next_data:detail | casing_change | yes | casing_change |
| bulldogjob | next_data:listing | renamed_key | yes | renamed_key |
| bulldogjob | next_data:listing | list_to_dict | yes | container_change |
| bulldogjob | next_data:listing | casing_change | yes | casing_change |
| justjoin | jsonld:detail | renamed_key | yes | renamed_key |
| justjoin | jsonld:detail | casing_change | yes | casing_change |
| nofluffjobs | jsonld:detail | renamed_key | yes | renamed_key |
| nofluffjobs | jsonld:detail | list_to_dict | yes | container_change |
| nofluffjobs | jsonld:detail | casing_change | yes | casing_change |
| pracuj | jsonld:detail | renamed_key | yes | renamed_key |
| pracuj | jsonld:detail | casing_change | yes | casing_change |
| pracuj | next_data:detail | renamed_key | yes | renamed_key |
| pracuj | next_data:detail | list_to_dict | yes | container_change |
| pracuj | next_data:detail | casing_change | yes | casing_change |
| pracuj | next_data:listing | renamed_key | yes | renamed_key |
| pracuj | next_data:listing | list_to_dict | yes | container_change |
| pracuj | next_data:listing | casing_change | yes | casing_change |
| rocketjobs | jsonld:detail | renamed_key | yes | renamed_key |
| rocketjobs | jsonld:detail | casing_change | yes | casing_change |
| solidjobs | api:listing | renamed_key | yes | renamed_key |
| solidjobs | api:listing | list_to_dict | yes | container_change |
| solidjobs | api:listing | casing_change | yes | casing_change |
| theprotocol | jsonld:detail | renamed_key | yes | renamed_key |
| theprotocol | jsonld:detail | list_to_dict | yes | container_change |
| theprotocol | jsonld:detail | casing_change | yes | casing_change |
| theprotocol | next_data:detail | renamed_key | yes | renamed_key |
| theprotocol | next_data:detail | list_to_dict | yes | container_change |
| theprotocol | next_data:detail | casing_change | yes | casing_change |
| theprotocol | next_data:listing | renamed_key | yes | renamed_key |
| theprotocol | next_data:listing | list_to_dict | yes | container_change |
| theprotocol | next_data:listing | casing_change | yes | casing_change |

## Semantic skew

- Embedder: gemma; join 0.45, novelty 0.45, centred: True
- Baseline requirement strings: 626; current: 626
- Emerging clusters: 0

