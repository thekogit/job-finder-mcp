"""Semantic skew: flag requirement clusters with no near neighbour in the baseline.

Requirement and tech-stack strings are embedded, clustered with a deterministic greedy
leader pass (fixed input order, no random init), and a cluster is an *emerging skill*
when its centroid's best cosine similarity to any baseline vector is below a threshold.

Embedders sit behind a small protocol so tests use a fake:

* ``LlamaCppEmbedder``: EmbeddingGemma 2 (Q8_0 GGUF) served by ``llama-server --embeddings``,
  with the ``task: clustering | query: `` prefix, a NaN/norm check on every vector and an
  on-disk cache keyed by model SHA-256 + prefix + text.
* ``TfidfEmbedder``: word TF-IDF fitted on the texts it sees; the negative-experiment
  baseline (it cannot match a Polish requirement to its Ukrainian translation).
"""

import hashlib
import json
import math
import os
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx
import numpy as np
import numpy.typing as npt

Matrix = npt.NDArray[np.float64]

GEMMA_SHA256 = "6f1bd4ac6c5df7444f9cca7ca36cafe6cfa34cd6f49fefb1e0b4be8143aed8bc"
CLUSTERING_PREFIX = "task: clustering | query: "


class Embedder(Protocol):
    name: str

    def embed(self, texts: Sequence[str]) -> Matrix:
        """Return one L2-normalised row per text."""
        ...


def _normalise_rows(matrix: Matrix) -> Matrix:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    result: Matrix = matrix / norms
    return result


class LlamaCppEmbedder:
    def __init__(
        self,
        base_url: str | None = None,
        cache_dir: Path = Path(".job-scout/embed_cache"),
        model_sha256: str = GEMMA_SHA256,
        batch_size: int = 32,
    ) -> None:
        self.base_url = (base_url or os.environ.get("EMBED_BASE_URL") or "http://127.0.0.1:8091/v1").rstrip("/")
        self.model_sha256 = model_sha256
        self.name = f"embeddinggemma-2-Q8_0@{model_sha256[:12]}"
        self.batch_size = batch_size
        self.cache_path = cache_dir / f"{model_sha256[:16]}.jsonl"
        self._cache: dict[str, list[float]] = {}
        if self.cache_path.is_file():
            for line in self.cache_path.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                self._cache[record["key"]] = record["vector"]

    def _key(self, text: str) -> str:
        payload = f"{self.model_sha256}\n{CLUSTERING_PREFIX}\n{text}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _fetch(self, texts: list[str]) -> list[list[float]]:
        resp = httpx.post(
            f"{self.base_url}/embeddings",
            json={"input": [CLUSTERING_PREFIX + t for t in texts], "model": "embeddinggemma-2"},
            timeout=120.0,
        )
        resp.raise_for_status()
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        vectors = [list(map(float, d["embedding"])) for d in data]
        for text, vec in zip(texts, vectors, strict=True):
            norm = math.sqrt(sum(x * x for x in vec))
            if any(math.isnan(x) for x in vec) or not 0.5 < norm < 2.0:
                # The model card warns that float16 compute yields NaN / degraded vectors.
                raise ValueError(f"degenerate embedding (norm={norm}) for {text[:60]!r}")
        return vectors

    def embed(self, texts: Sequence[str]) -> Matrix:
        missing = list(dict.fromkeys(t for t in texts if self._key(t) not in self._cache))
        if missing:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_path.open("a", encoding="utf-8") as fh:
                for start in range(0, len(missing), self.batch_size):
                    batch = missing[start : start + self.batch_size]
                    for text, vec in zip(batch, self._fetch(batch), strict=True):
                        key = self._key(text)
                        self._cache[key] = vec
                        fh.write(json.dumps({"key": key, "vector": vec}) + "\n")
        return _normalise_rows(np.array([self._cache[self._key(t)] for t in texts], dtype=np.float64))


_TOKEN = re.compile(r"\w+", re.UNICODE)


class TfidfEmbedder:
    """Word unigram TF-IDF. Call ``fit`` on the full corpus before ``embed``."""

    name = "tfidf-word-unigram"

    def __init__(self) -> None:
        self.vocab: dict[str, int] = {}
        self.idf: Matrix = np.zeros(0)

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return [t.lower() for t in _TOKEN.findall(text)]

    def fit(self, corpus: Sequence[str]) -> "TfidfEmbedder":
        df: Counter[str] = Counter()
        for text in corpus:
            df.update(set(self._tokens(text)))
        self.vocab = {tok: i for i, tok in enumerate(sorted(df))}
        n = len(corpus)
        self.idf = np.array([math.log((1 + n) / (1 + df[t])) + 1 for t in sorted(df)])
        return self

    def embed(self, texts: Sequence[str]) -> Matrix:
        matrix = np.zeros((len(texts), len(self.vocab)))
        for row, text in enumerate(texts):
            for tok, count in Counter(self._tokens(text)).items():
                col = self.vocab.get(tok)
                if col is not None:
                    matrix[row, col] = count * self.idf[col]
        return _normalise_rows(matrix)


@dataclass(frozen=True)
class Cluster:
    members: tuple[str, ...]
    nearest_baseline: str
    similarity: float

    @property
    def size(self) -> int:
        return len(self.members)


def leader_clusters(texts: Sequence[str], vectors: Matrix, join_threshold: float) -> list[list[int]]:
    """Greedy leader clustering in a fixed order: deterministic, no random init."""
    order = sorted(range(len(texts)), key=lambda i: texts[i])
    clusters: list[list[int]] = []
    centroids: list[npt.NDArray[np.float64]] = []
    for i in order:
        if centroids:
            sims = np.array([float(c @ vectors[i]) for c in centroids])
            best = int(np.argmax(sims))
            if sims[best] >= join_threshold:
                clusters[best].append(i)
                mean = vectors[clusters[best]].mean(axis=0)
                centroids[best] = mean / (np.linalg.norm(mean) or 1.0)
                continue
        clusters.append([i])
        centroids.append(vectors[i].copy())
    return clusters


def emerging_clusters(
    baseline_texts: Sequence[str],
    current_texts: Sequence[str],
    embedder: Embedder,
    novelty_threshold: float,
    join_threshold: float,
    min_size: int = 2,
    center: bool = False,
) -> list[Cluster]:
    """Clusters of current texts whose centroid has no baseline neighbour >= threshold.

    ``center=True`` subtracts the baseline mean vector and re-normalises before any cosine
    is taken. EmbeddingGemma's raw vectors are anisotropic (two random fixture requirements
    average ~0.84 cosine), so without centring every string looks "near" the baseline;
    see evals/skew/results/semantic_injection.md.
    """
    if isinstance(embedder, TfidfEmbedder):
        embedder.fit([*baseline_texts, *current_texts])
    base = embedder.embed(baseline_texts)
    current = embedder.embed(current_texts)
    if center:
        mean = base.mean(axis=0)
        base = _normalise_rows(base - mean)
        current = _normalise_rows(current - mean)
    flagged: list[Cluster] = []
    for members in leader_clusters(current_texts, current, join_threshold):
        if len(members) < min_size:
            continue
        mean = current[members].mean(axis=0)
        centroid = mean / (np.linalg.norm(mean) or 1.0)
        sims = base @ centroid
        best = int(np.argmax(sims))
        if float(sims[best]) < novelty_threshold:
            flagged.append(
                Cluster(
                    members=tuple(sorted(current_texts[i] for i in members)),
                    nearest_baseline=baseline_texts[best],
                    similarity=round(float(sims[best]), 4),
                )
            )
    return flagged
