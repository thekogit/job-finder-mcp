# Semantic skew: injection experiment

- Date: 2026-11-08
- Command: `python -m evals.skew.experiment`
- Seed 20261108; baseline 500 real fixture strings; current week 126 held-out real strings + 16 synthetic strings (4 topics x 4: 2 EN, 1 PL, 1 UA).
- EmbeddingGemma 2 Q8_0 (SHA256 6f1bd4ac...) via llama.cpp b12192 CPU, prefix `task: clustering | query: `. TF-IDF: word unigrams fitted on baseline + current.

| Embedder | Centred | Join | Novelty | Topics detected | Cross-lingual | Flagged clusters | False alerts (real-only) |
|---|---|---|---|---|---|---|---|
| gemma | yes | 0.45 | 0.35 | 4/4 | 4/4 | 4 | 0 |
| gemma | yes | 0.45 | 0.4 | 4/4 | 4/4 | 4 | 0 |
| gemma | yes | 0.45 | 0.45 | 4/4 | 4/4 | 4 | 0 |
| gemma | yes | 0.45 | 0.5 | 4/4 | 4/4 | 4 | 0 |
| gemma | yes | 0.45 | 0.55 | 4/4 | 4/4 | 4 | 0 |
| gemma | no | 0.8 | 0.75 | 0/4 | 0/4 | 0 | 0 |
| gemma | no | 0.8 | 0.8 | 0/4 | 0/4 | 0 | 0 |
| gemma | no | 0.8 | 0.85 | 0/4 | 0/4 | 0 | 0 |
| gemma | no | 0.8 | 0.9 | 0/4 | 0/4 | 0 | 0 |
| tfidf | no | 0.3 | 0.1 | 0/4 | 0/4 | 1 | 1 |
| tfidf | no | 0.3 | 0.2 | 2/4 | 1/4 | 3 | 1 |
| tfidf | no | 0.3 | 0.3 | 2/4 | 1/4 | 4 | 2 |
| tfidf | no | 0.3 | 0.4 | 2/4 | 1/4 | 7 | 5 |

Caveats:

- The monitor's thresholds (`evals/skew/run.py`, `THRESHOLDS`) were picked from this
  same sweep, so these rows are in-sample. They show the method can separate the
  injected topics; they are not a held-out detection rate.
- 4 synthetic topics x 4 strings is a small probe. A real emerging skill arrives
  gradually and mixed with noise; the weekly live run has not been executed yet.
- "False alerts" counts flagged clusters of real held-out strings; some may be
  legitimately new to the 80% baseline, so it is an upper bound on noise.
