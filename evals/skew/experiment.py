"""Semantic-skew injection experiment: EmbeddingGemma 2 vs. a TF-IDF baseline.

    python -m evals.skew.experiment            # needs llama-server with EmbeddingGemma on :8091

Setup (seeded, deterministic):

* The fixture requirement strings (evals/skew/baselines/semantic/requirements.json) are split 80/20 with ``random.Random(SEED)``.
  The 80% is the baseline. The 20% is the "current week": real requirements the baseline
  has not seen verbatim, which mostly should *not* be flagged.
* Four hand-written synthetic topics (``synthetic_emerging.json``, 4 strings each in
  EN/PL/UA) are added to the current week. They should each be flagged.

Scoring per novelty threshold:

* topic recall: a topic counts as detected when one flagged cluster holds >= 2 of its
  strings and the cluster's majority comes from that topic;
* cross-lingual topics: detected topics whose flagged cluster spans >= 2 languages;
* false alerts: flagged clusters made only of real held-out strings. These are not all
  wrong (a held-out string can be genuinely new), so read them as an upper bound on noise.

Writes ``evals/skew/results/semantic_injection.md``.
"""

import json
import random
import sys
from datetime import date
from pathlib import Path

from evals.skew.run import SEMANTIC_BASELINE, SKEW_DIR
from evals.skew.semantic import Embedder, LlamaCppEmbedder, TfidfEmbedder, emerging_clusters

SEED = 20261108
HOLDOUT = 0.2
SWEEP: list[tuple[str, bool, float, list[float]]] = [
    # (embedder, centre on baseline mean, join threshold, novelty thresholds to sweep)
    ("gemma", True, 0.45, [0.35, 0.40, 0.45, 0.50, 0.55]),
    ("gemma", False, 0.80, [0.75, 0.80, 0.85, 0.90]),  # negative experiment: raw cosine
    ("tfidf", False, 0.30, [0.10, 0.20, 0.30, 0.40]),
]
LANG = {0: "en", 1: "en", 2: "pl", 3: "uk"}  # position of each string within a topic


def main() -> int:
    texts: list[str] = json.loads(SEMANTIC_BASELINE.read_text(encoding="utf-8"))["texts"]
    synthetic = json.loads((SKEW_DIR / "synthetic_emerging.json").read_text(encoding="utf-8"))["topics"]
    shuffled = texts[:]
    random.Random(SEED).shuffle(shuffled)
    cut = int(len(shuffled) * (1 - HOLDOUT))
    baseline, held_out = shuffled[:cut], shuffled[cut:]
    topic_of: dict[str, str] = {}
    lang_of: dict[str, str] = {}
    for topic, strings in synthetic.items():
        for i, s in enumerate(strings):
            topic_of[s] = topic
            lang_of[s] = LANG[i]
    current = held_out + list(topic_of)

    lines = [
        "# Semantic skew: injection experiment",
        "",
        f"- Date: {date.today().isoformat()}",
        "- Command: `python -m evals.skew.experiment`",
        f"- Seed {SEED}; baseline {len(baseline)} real fixture strings; current week "
        f"{len(held_out)} held-out real strings + {len(topic_of)} synthetic strings "
        f"({len(synthetic)} topics x 4: 2 EN, 1 PL, 1 UA).",
        "- EmbeddingGemma 2 Q8_0 (SHA256 6f1bd4ac...) via llama.cpp b12192 CPU, "
        "prefix `task: clustering | query: `. TF-IDF: word unigrams fitted on baseline + current.",
        "",
        "| Embedder | Centred | Join | Novelty | Topics detected | Cross-lingual | Flagged clusters | False alerts (real-only) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, center, join, thresholds in SWEEP:
        for novelty in thresholds:
            embedder: Embedder = LlamaCppEmbedder() if name == "gemma" else TfidfEmbedder()
            clusters = emerging_clusters(baseline, current, embedder, novelty, join, center=center)
            detected: set[str] = set()
            crossling: set[str] = set()
            false_alerts = 0
            for c in clusters:
                topics = [topic_of[m] for m in c.members if m in topic_of]
                if not topics:
                    false_alerts += 1
                    continue
                top = max(set(topics), key=topics.count)
                if topics.count(top) >= 2 and topics.count(top) * 2 > c.size:
                    detected.add(top)
                    if len({lang_of[m] for m in c.members if topic_of.get(m) == top}) >= 2:
                        crossling.add(top)
            lines.append(
                f"| {name} | {'yes' if center else 'no'} | {join} | {novelty} | {len(detected)}/{len(synthetic)} | "
                f"{len(crossling)}/{len(synthetic)} | {len(clusters)} | {false_alerts} |"
            )
            print(lines[-1], file=sys.stderr)
    lines += [
        "",
        "Caveats:",
        "",
        "- The monitor's thresholds (`evals/skew/run.py`, `THRESHOLDS`) were picked from this",
        "  same sweep, so these rows are in-sample. They show the method can separate the",
        "  injected topics; they are not a held-out detection rate.",
        "- 4 synthetic topics x 4 strings is a small probe. A real emerging skill arrives",
        "  gradually and mixed with noise; the weekly live run has not been executed yet.",
        "- \"False alerts\" counts flagged clusters of real held-out strings; some may be",
        "  legitimately new to the 80% baseline, so it is an upper bound on noise.",
    ]
    out = SKEW_DIR / "results" / "semantic_injection.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(Path(out).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
