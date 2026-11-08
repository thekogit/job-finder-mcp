from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from evals.skew.run import BASELINE_DIR, main, mutation_self_test, structural_alerts
from evals.skew.semantic import Matrix, TfidfEmbedder, emerging_clusters, leader_clusters
from evals.skew.structural import (
    Payload,
    build_baseline,
    compare,
    fingerprint,
    fixture_payloads,
    load_baselines,
    payloads_from_page,
)

FIXTURES = Path("tests/fixtures")


def test_fingerprint_collapses_lists_ids_and_apollo_keys() -> None:
    fp = fingerprint(
        {
            "items": [{"a": 1}, {"a": 2.5}],
            "12345": {"x": None},
            "Job:256082-some-slug": {"t": "s"},
            "jobs({\"page\":1})": [],
            "__namespaces": {"ui": "copy"},
        }
    )
    assert fp["$.items[].a"] == {"int", "float"}
    assert fp["$.<id>.x"] == {"null"}
    assert fp["$.Job:<id>.t"] == {"str"}
    assert fp["$.jobs(<args>)"] == {"list"}
    assert not any("__namespaces" in p for p in fp)


BASE = {"title": "Dev", "salary": {"min": 1, "max": 2}, "skills": ["py", "sql"]}


@pytest.fixture
def baseline() -> dict[str, object]:
    samples = [Payload("b", "jsonld:detail", f"s{i}", data=BASE) for i in range(2)]
    return build_baseline("b", samples, "test")


@pytest.mark.parametrize(
    ("mutated", "expected"),
    [
        ({**BASE, "Title": "Dev", "title": None} | {"title": "x"}, set()),  # extra key only: no alert
        ({k: v for k, v in BASE.items() if k != "title"} | {"Title": "Dev"}, {"casing_change"}),
        ({k: v for k, v in BASE.items() if k != "title"} | {"job_title": "Dev"}, {"renamed_key"}),
        ({k: v for k, v in BASE.items() if k != "title"}, {"missing_path"}),
        ({**BASE, "skills": {"0": "py", "1": "sql"}}, {"container_change"}),
        ({**BASE, "salary": {"min": "1", "max": 2}}, {"type_change"}),
    ],
)
def test_compare_classifies_alerts(
    baseline: dict[str, object], mutated: dict[str, object], expected: set[str]
) -> None:
    alerts = compare(Payload("b", "jsonld:detail", "live", data=mutated), baseline)
    assert {a.alert for a in alerts} == expected


def test_field_seen_only_as_null_may_gain_a_value() -> None:
    samples = [Payload("b", "jsonld:detail", f"s{i}", data={"note": None}) for i in range(3)]
    base = build_baseline("b", samples, "test")
    live = Payload("b", "jsonld:detail", "live", data={"note": {"text": "filled"}})
    assert compare(live, base) == []


def test_container_change_does_not_spray_child_alerts(baseline: dict[str, object]) -> None:
    mutated = {**BASE, "salary": [1, 2]}
    alerts = compare(Payload("b", "jsonld:detail", "live", data=mutated), baseline)
    assert [(a.alert, a.path) for a in alerts] == [("container_change", "$.salary")]


def test_html_listing_link_drop() -> None:
    html = FIXTURES.joinpath("justjoin/listing_1.html").read_text(encoding="utf-8")
    healthy = payloads_from_page("justjoin", "l1", html, "listing")
    base = build_baseline("justjoin", healthy, "test")
    broken = payloads_from_page("justjoin", "l2", "<html><a href='/x'>x</a></html>", "listing")
    alerts = [a for p in broken for a in compare(p, base)]
    assert [a.alert for a in alerts] == ["link_drop"]


def test_committed_baselines_match_fixtures_and_catch_every_mutation() -> None:
    payloads = fixture_payloads(FIXTURES)
    baselines = load_baselines(BASELINE_DIR)
    assert structural_alerts(payloads, baselines) == []
    rows = mutation_self_test(payloads, baselines)
    assert rows, "self-test produced no mutations"
    assert [r for r in rows if not r[3]] == []


class FakeEmbedder:
    """Maps each text to a fixed axis by its first word: same word = same direction."""

    name = "fake"

    def __init__(self) -> None:
        self.axes: dict[str, int] = {}

    def embed(self, texts: Sequence[str]) -> Matrix:
        rows = np.zeros((len(texts), 16))
        for i, text in enumerate(texts):
            axis = self.axes.setdefault(text.split()[0].lower(), len(self.axes))
            rows[i, axis] = 1.0
            rows[i, 15] = 0.1  # shared component, like a real model's anisotropy
        normalised: Matrix = rows / np.linalg.norm(rows, axis=1, keepdims=True)
        return normalised


def test_emerging_cluster_flagged_and_known_topics_not() -> None:
    baseline = ["python backend", "python data", "sql queries", "sql tuning"]
    current = ["python apis", "sql joins", "qiskit circuits", "qiskit algorithms"]
    clusters = emerging_clusters(baseline, current, FakeEmbedder(), novelty_threshold=0.5, join_threshold=0.9)
    assert [c.members for c in clusters] == [("qiskit algorithms", "qiskit circuits")]


def test_singletons_are_not_flagged() -> None:
    clusters = emerging_clusters(["python"], ["qiskit once"], FakeEmbedder(), 0.5, 0.9)
    assert clusters == []


def test_leader_clustering_is_order_independent() -> None:
    texts = ["b x", "a y", "b z", "a w"]
    emb = FakeEmbedder()
    first = leader_clusters(texts, emb.embed(texts), 0.9)
    reordered = list(reversed(texts))
    second = leader_clusters(reordered, emb.embed(reordered), 0.9)
    as_sets = lambda groups, src: sorted(sorted(src[i] for i in g) for g in groups)  # noqa: E731
    assert as_sets(first, texts) == as_sets(second, reordered)


def test_tfidf_cannot_link_translations() -> None:
    emb = TfidfEmbedder().fit(["Znajomość Qiskit", "Знання квантових обчислень"])
    vectors = emb.embed(["Znajomość Qiskit", "Знання квантових обчислень"])
    assert float(vectors[0] @ vectors[1]) == 0.0


def test_fixture_run_cli_offline(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    assert main(["--fixtures", "--embedder", "tfidf", "--report", str(report)]) == 0
    text = report.read_text(encoding="utf-8")
    assert "No alerts." in text
    assert "Synthetic-mutation self-test: 36/36 detected" in text


def test_report_groups_repeated_alerts() -> None:
    from evals.skew.run import render_report
    from evals.skew.structural import Alert

    payloads = [Payload("b", "jsonld:detail", f"s{i}", data={}) for i in range(3)]
    alerts = [Alert("b", "jsonld:detail", "type_change", "$.x", "str -> list", f"s{i}") for i in range(2)]
    text = render_report("t", "cmd", payloads, alerts, None, None, None, 0, 0)
    assert text.count("type_change") == 1
    assert "| 2/3 |" in text
