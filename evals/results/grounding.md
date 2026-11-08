# Grounded extraction (fixtures)

- Date: 2026-11-08
- Command: `python -m evals.grounding_eval`
- Model: `beam:cloud` (OpenAI-compatible endpoint), temperature 0, max 2 retries
- Listings: 19 tier-1 detail fixtures (title + stored description, <= 4 000 chars). Polish and English, plus one Ukrainian description (pracuj/detail_4.html, recorded 2026-11-08; Polish title).

- First-attempt pass (all quotes verbatim on try 1): **17/19**
- Final status: grounded_after_retry 2, grounded_first_try 17
- Fields kept: seniority 11/19, work_mode 11/19
- Independent re-check of kept quotes: 22/22 verbatim
- Seniority agreement with the title-keyword rule (both non-null): 9/9 (agreement, not accuracy: no human labels)
- First-attempt validation errors by kind: quote not verbatim 2

| Fixture | Status | Attempts | Seniority | Quote | Work mode | Quote | Title rule |
|---|---|---|---|---|---|---|---|
| pracuj/detail_1.html | grounded_first_try | 1 | intern | "umowa o staż / praktyki" | - | - | - |
| pracuj/detail_2.html | grounded_first_try | 1 | senior | "Senior AEM Developer (f/m/x)" | - | - | senior |
| pracuj/detail_3.html | grounded_first_try | 1 | senior | "Senior AI Engineer" | remote | "remote work opportunities" | senior |
| pracuj/detail_4.html | grounded_first_try | 1 | - | - | - | - | - |
| justjoin/detail_1.html | grounded_first_try | 1 | - | - | remote | "pełną elastyczność miejsca i czasu pracy" | - |
| justjoin/detail_2.html | grounded_first_try | 1 | - | - | onsite | "Praca stacjonarna" | - |
| justjoin/detail_3.html | grounded_first_try | 1 | lead | "Lead Oracle Database Administrator" | hybrid | "hybrid model - 2 days in the office, 3 days remote" | lead |
| rocketjobs/detail_1.html | grounded_first_try | 1 | - | - | - | - | - |
| rocketjobs/detail_2.html | grounded_first_try | 1 | - | - | remote | "mostly remote" | - |
| rocketjobs/detail_3.html | grounded_first_try | 1 | lead | "Kierownik Zmiany" | onsite | "na Lotnisku Chopina" | - |
| nofluffjobs/detail_1.html | grounded_after_retry | 3 | senior | "Senior Software Engineer" | onsite | "w biurze nad Wisłą" | senior |
| nofluffjobs/detail_2.html | grounded_first_try | 1 | lead | "DevOps Tech Lead" | - | - | lead |
| nofluffjobs/detail_3.html | grounded_first_try | 1 | lead | "Technical Lead" | remote | "100% zdalnie" | lead |
| bulldogjob/detail_1.html | grounded_after_retry | 2 | junior | "(Młodszy)" | onsite | "pracy w terenie" | junior |
| bulldogjob/detail_2.html | grounded_first_try | 1 | - | - | - | - | lead |
| bulldogjob/detail_3.html | grounded_first_try | 1 | lead | "Java Team Lead" | - | - | lead |
| theprotocol/detail_1.html | grounded_first_try | 1 | senior | "Senior Cloud Data Engineer" | hybrid | "Hybrid work model" | senior |
| theprotocol/detail_2.html | grounded_first_try | 1 | - | - | hybrid | "modelu hybrydowym" | - |
| theprotocol/detail_3.html | grounded_first_try | 1 | - | - | - | - | - |
