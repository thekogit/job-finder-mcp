"""Skew monitor entry point.

    python -m evals.skew.run --fixtures                 # offline, used in CI
    python -m evals.skew.run --fixtures --embedder gemma  # needs llama-server on :8091
    python -m evals.skew.run --weekly                   # LIVE: scrapes the boards (ask first)
    python -m evals.skew.run --write-baselines          # rebuild baselines from fixtures

Exit code: 0 when the run completed (alerts are reported, not fatal), 1 when the fixture
self-test fails (a synthetic mutation went undetected, or an unmutated fixture alerted).
"""

import argparse
import asyncio
import json
import logging
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from evals.fixture_offers import FIXTURES_DIR, fixture_requirement_texts, is_requirement_like
from evals.skew.semantic import (
    Cluster,
    Embedder,
    LlamaCppEmbedder,
    TfidfEmbedder,
    emerging_clusters,
)
from evals.skew.structural import (
    MUTATIONS,
    Alert,
    Payload,
    compare,
    fixture_payloads,
    load_baselines,
    mutate,
    payloads_from_page,
    write_baselines,
)

logger = logging.getLogger("evals.skew")

SKEW_DIR = Path(__file__).parent
BASELINE_DIR = SKEW_DIR / "baselines"
SEMANTIC_BASELINE = BASELINE_DIR / "semantic" / "requirements.json"
REPORT_DIR = Path("reports/skew")

# Per embedder: (join threshold, novelty threshold, centre on the baseline mean).
# Chosen in-sample from the injection sweep in evals/skew/results/semantic_injection.md.
THRESHOLDS: dict[str, tuple[float, float, bool]] = {
    "gemma": (0.45, 0.45, True),
    "tfidf": (0.30, 0.30, False),
}


def make_embedder(name: str) -> Embedder:
    if name == "gemma":
        return LlamaCppEmbedder()
    if name == "tfidf":
        return TfidfEmbedder()
    raise ValueError(f"unknown embedder {name!r}")


# --- structural ---------------------------------------------------------------------------


def structural_alerts(payloads: list[Payload], baselines: dict[str, dict[str, Any]]) -> list[Alert]:
    alerts: list[Alert] = []
    for payload in payloads:
        baseline = baselines.get(payload.board)
        if baseline is not None:
            alerts.extend(compare(payload, baseline))
    return alerts


def mutation_self_test(
    payloads: list[Payload], baselines: dict[str, dict[str, Any]]
) -> list[tuple[str, str, str, bool, list[str]]]:
    """For each board/kind, mutate one sample three ways; each must raise an alert."""
    rows: list[tuple[str, str, str, bool, list[str]]] = []
    seen: set[tuple[str, str]] = set()
    for payload in payloads:
        if payload.data is None or (payload.board, payload.kind) in seen:
            continue
        seen.add((payload.board, payload.kind))
        for mutation in MUTATIONS:
            mutated = mutate(payload.data, mutation)
            if mutated is None:
                continue
            probe = Payload(payload.board, payload.kind, f"{payload.origin} [{mutation}]", data=mutated)
            alerts = compare(probe, baselines[payload.board])
            rows.append(
                (payload.board, payload.kind, mutation, bool(alerts), sorted({a.alert for a in alerts}))
            )
    return rows


# --- live capture -------------------------------------------------------------------------


async def capture_live(limit: int) -> tuple[list[Payload], list[str]]:
    """Run each enabled adapter with a small limit and fingerprint every response it got."""
    from job_scout.http import get_http_client
    from job_scout.models import SearchQuery
    from job_scout.registry import registry

    client = get_http_client()
    captured: list[tuple[str, str]] = []

    skipped: Counter[int] = Counter()

    async def record(resp: httpx.Response) -> None:
        if resp.url.path.endswith("/robots.txt"):
            return
        if not resp.is_success:
            # A 429 / 403 / challenge page is not the board's schema: fingerprinting it
            # would fake a link_drop or missing_path. Count it instead.
            skipped[resp.status_code] += 1
            return
        await resp.aread()
        captured.append((str(resp.url), resp.text))

    transports = (client.client, client.client_h1)
    for transport in transports:
        transport.event_hooks["response"].append(record)
    payloads: list[Payload] = []
    requirements: list[str] = []
    try:
        for source in registry.enabled_source_ids():
            captured.clear()
            skipped.clear()
            offers, report = await registry.run_listing(source, SearchQuery(limit=limit))
            logger.info(
                "%s: %s, %d offers, %d responses fingerprinted, non-2xx skipped: %s",
                source, report.status, len(offers), len(captured), dict(skipped) or "none",
            )
            for i, (url, body) in enumerate(captured):
                page = "listing" if i == 0 else "detail"
                payloads.extend(payloads_from_page(source, url, body, page))
            for offer in offers:
                requirements.extend(r for r in offer.requirements + offer.nice_to_have if is_requirement_like(r))
    finally:
        for transport in transports:
            transport.event_hooks["response"].remove(record)
        await client.close()
    return payloads, list(dict.fromkeys(requirements))


# --- report -------------------------------------------------------------------------------


def render_report(
    title: str,
    command: str,
    payloads: list[Payload],
    alerts: list[Alert],
    self_test: list[tuple[str, str, str, bool, list[str]]] | None,
    embedder_name: str | None,
    clusters: list[Cluster] | None,
    current_count: int,
    baseline_count: int,
) -> str:
    lines = [
        f"# {title}",
        "",
        f"- Date: {date.today().isoformat()}",
        f"- Command: `{command}`",
        f"- Payloads fingerprinted: {len(payloads)} "
        f"({', '.join(f'{k} {v}' for k, v in sorted(Counter(p.kind for p in payloads).items()))})",
        "",
        "## Structural skew",
        "",
    ]
    if alerts:
        samples = Counter((p.board, p.kind) for p in payloads)
        grouped = Counter((a.board, a.kind, a.alert, a.path, a.detail) for a in alerts)
        lines += ["| Board | Payload | Alert | Path | Detail | Samples |", "|---|---|---|---|---|---|"]
        lines += [
            f"| {b} | {k} | {al} | `{p}` | {d} | {n}/{samples[(b, k)]} |"
            for (b, k, al, p, d), n in grouped.items()
        ]
    else:
        lines.append("No alerts.")
    if self_test is not None:
        detected = sum(1 for r in self_test if r[3])
        lines += [
            "",
            f"### Synthetic-mutation self-test: {detected}/{len(self_test)} detected",
            "",
            "| Board | Payload | Mutation | Detected | Alert types |",
            "|---|---|---|---|---|",
        ]
        lines += [f"| {b} | {k} | {m} | {'yes' if d else '**NO**'} | {', '.join(t)} |" for b, k, m, d, t in self_test]
    lines += ["", "## Semantic skew", ""]
    if clusters is None:
        lines.append("Skipped (no embedder).")
    else:
        join, novelty, center = THRESHOLDS[embedder_name or "tfidf"]
        lines += [
            f"- Embedder: {embedder_name}; join {join}, novelty {novelty}, centred: {center}",
            f"- Baseline requirement strings: {baseline_count}; current: {current_count}",
            f"- Emerging clusters: {len(clusters)}",
            "",
        ]
        for c in clusters:
            lines.append(f"- **{c.size} strings**, nearest baseline {c.similarity}: {c.nearest_baseline!r}")
            lines += [f"  - {m}" for m in c.members[:8]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixtures", action="store_true", help="offline run on tests/fixtures")
    mode.add_argument("--weekly", action="store_true", help="LIVE run against the boards")
    mode.add_argument("--write-baselines", action="store_true", help="rebuild baselines from fixtures")
    parser.add_argument("--embedder", choices=["gemma", "tfidf", "none"], default="tfidf")
    parser.add_argument("--limit", type=int, default=3, help="offers per board in --weekly")
    parser.add_argument("--report", type=Path, help="report path (default reports/skew/<date>-<mode>.md)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")

    if args.write_baselines:
        payloads = fixture_payloads(FIXTURES_DIR)
        note = "tests/fixtures (recorded 2026-10-11/12 during the JS-MCP-001 build)"
        for path in write_baselines(BASELINE_DIR, payloads, note):
            print(path.as_posix())
        SEMANTIC_BASELINE.parent.mkdir(parents=True, exist_ok=True)
        texts = fixture_requirement_texts(FIXTURES_DIR)
        SEMANTIC_BASELINE.write_text(
            json.dumps({"source": note, "count": len(texts), "texts": texts}, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(SEMANTIC_BASELINE.as_posix())
        return 0

    baselines = load_baselines(BASELINE_DIR)
    baseline_texts: list[str] = json.loads(SEMANTIC_BASELINE.read_text(encoding="utf-8"))["texts"]
    self_test = None
    if args.fixtures:
        payloads = fixture_payloads(FIXTURES_DIR)
        current_texts = fixture_requirement_texts(FIXTURES_DIR)
        self_test = mutation_self_test(payloads, baselines)
        mode_name = "fixtures"
    else:
        payloads, current_texts = asyncio.run(capture_live(args.limit))
        mode_name = "weekly"

    alerts = structural_alerts(payloads, baselines)
    clusters = None
    if args.embedder != "none" and current_texts:
        join, novelty, center = THRESHOLDS[args.embedder]
        clusters = emerging_clusters(
            baseline_texts, current_texts, make_embedder(args.embedder), novelty, join, center=center
        )

    command = "python -m evals.skew.run " + " ".join(argv if argv is not None else sys.argv[1:])
    report = render_report(
        f"Skew report ({mode_name})", command, payloads, alerts, self_test,
        None if args.embedder == "none" else args.embedder, clusters, len(current_texts), len(baseline_texts),
    )
    out = args.report or REPORT_DIR / f"{date.today().isoformat()}-{mode_name}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(out.as_posix())

    if self_test is not None:
        missed = [r for r in self_test if not r[3]]
        if missed or alerts:
            print(f"self-test failed: {len(missed)} undetected mutations, {len(alerts)} alerts on clean fixtures", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
