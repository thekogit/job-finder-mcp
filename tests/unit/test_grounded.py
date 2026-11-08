"""Grounded extraction tests. No network: a scripted fake LLM stands in for the API.

The listing texts below are short synthetic snippets written for these tests (one each in
Polish, Ukrainian and English); they are not recorded board data.
"""

import json
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import ValidationError

from job_scout.generation.grounded import (
    MAX_RETRIES,
    GroundedFields,
    OpenAICompatibleClient,
    deterministic_seniority,
    extract_grounded,
    ground_offer,
)
from job_scout.models import Evidence, JobOffer, Seniority, WorkMode

PL_TEXT = "Starszy Programista Python\nOferujemy pracę w modelu hybrydowym (2 dni w biurze)."
UA_TEXT = "Python-розробник\nШукаємо Senior розробника. Формат роботи: повністю віддалено."
EN_TEXT = "Data Engineer\nYou will work fully remote from anywhere in Poland."


class ScriptedLLM:
    model = "fake-model"

    def __init__(self, answers: list[dict[str, object] | str]) -> None:
        self.answers = list(answers)
        self.seen: list[list[dict[str, str]]] = []

    async def complete(self, messages: list[dict[str, str]]) -> str:
        self.seen.append(messages)
        answer = self.answers.pop(0)
        return answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)


def _offer(title: str, description: str, **extra: object) -> JobOffer:
    return JobOffer.model_validate(
        {
            "id": "1",
            "link": "https://example.com/1",
            "source": "test",
            "title": title,
            "description": description,
            "first_seen_at": "2026-11-08T00:00:00+01:00",
            "last_checked_at": "2026-11-08T00:00:00+01:00",
            **extra,
        }
    )


@pytest.mark.parametrize(
    ("title", "level", "quote"),
    [
        ("Senior Python Developer", Seniority.SENIOR, "Senior"),
        ("Młodszy Specjalista ds. Danych", Seniority.JUNIOR, "Młodszy"),
        ("Старший інженер", Seniority.SENIOR, "Старший"),
        ("Tech Lead (Java)", Seniority.LEAD, "Lead"),
        ("Stażysta w dziale IT", Seniority.INTERN, "Stażysta"),
    ],
)
def test_deterministic_seniority_quotes_the_title(title: str, level: Seniority, quote: str) -> None:
    found = deterministic_seniority(title)
    assert found is not None
    assert found[0] == level
    assert found[1].quote == quote
    assert quote in title


@pytest.mark.parametrize("title", ["Mid/Senior Python Developer", "Python Developer"])
def test_deterministic_seniority_abstains_when_ambiguous_or_absent(title: str) -> None:
    assert deterministic_seniority(title) is None


def test_job_offer_rejects_quote_that_is_not_in_the_listing() -> None:
    with pytest.raises(ValidationError, match="not substrings"):
        _offer(
            "Python Developer",
            EN_TEXT,
            seniority="senior",
            seniority_evidence=Evidence(field="seniority", quote="Senior"),
        )


def test_job_offer_rejects_translated_or_case_folded_quote() -> None:
    with pytest.raises(ValidationError):
        _offer(
            "Python-розробник",
            UA_TEXT,
            work_mode=["remote"],
            work_mode_evidence=Evidence(field="work_mode", quote="fully remote"),
        )
    with pytest.raises(ValidationError):
        _offer(
            "Data Engineer",
            EN_TEXT,
            work_mode=["remote"],
            work_mode_evidence=Evidence(field="work_mode", quote="FULLY REMOTE"),
        )


def test_quote_check_normalises_whitespace_and_nbsp_only() -> None:
    offer = _offer(
        "Dev",
        "Praca\xa0zdalna,   pełny etat",
        work_mode=["remote"],
        work_mode_evidence=Evidence(field="work_mode", quote="Praca zdalna, pełny etat"),
    )
    assert offer.work_mode_evidence is not None


def test_seniority_needs_evidence() -> None:
    with pytest.raises(ValidationError, match="without a verbatim"):
        _offer("Dev", "text", seniority="senior")


async def test_first_try_grounded_polish() -> None:
    llm = ScriptedLLM(
        [
            {
                "seniority": "senior",
                "seniority_quote": "Starszy Programista",
                "work_mode": ["hybrid"],
                "work_mode_quote": "w modelu hybrydowym",
            }
        ]
    )
    outcome = await extract_grounded(PL_TEXT, llm)
    assert outcome.status == "grounded_first_try"
    assert outcome.fields.work_mode == [WorkMode.HYBRID]
    assert len(llm.seen) == 1


async def test_bad_quote_is_fed_back_and_corrected_ukrainian() -> None:
    llm = ScriptedLLM(
        [
            # translated quote: not a substring of the Ukrainian listing
            {"seniority": "senior", "seniority_quote": "Senior", "work_mode": ["remote"], "work_mode_quote": "fully remote"},
            {"seniority": "senior", "seniority_quote": "Senior", "work_mode": ["remote"], "work_mode_quote": "повністю віддалено"},
        ]
    )
    outcome = await extract_grounded(UA_TEXT, llm)
    assert outcome.status == "grounded_after_retry"
    assert [a.number for a in outcome.attempts] == [1, 2]
    retry_prompt = llm.seen[1][-1]["content"]
    assert "'fully remote' is not an exact substring" in retry_prompt
    assert outcome.fields.work_mode_quote == "повністю віддалено"


async def test_gives_up_after_max_retries_and_salvages_grounded_fields() -> None:
    bad = {"seniority": "senior", "seniority_quote": "senior level", "work_mode": ["remote"], "work_mode_quote": "fully remote"}
    llm = ScriptedLLM([bad] * (MAX_RETRIES + 1))
    outcome = await extract_grounded(EN_TEXT, llm)
    assert len(llm.seen) == MAX_RETRIES + 1
    assert outcome.status == "partial"
    assert outcome.fields.seniority is None  # ungrounded: dropped
    assert outcome.fields.work_mode == [WorkMode.REMOTE]  # grounded on its own: kept


async def test_malformed_json_ends_in_abstention() -> None:
    llm = ScriptedLLM(["not json"] * (MAX_RETRIES + 1))
    outcome = await extract_grounded(EN_TEXT, llm)
    assert outcome.status == "abstained"
    assert outcome.fields == GroundedFields()


async def test_ground_offer_never_overrides_structured_work_mode() -> None:
    offer = _offer("Senior Dev", "Hybrid work in Warsaw.", work_mode=["hybrid"])
    llm = ScriptedLLM([])  # must not be called: both fields are filled deterministically
    grounded = await ground_offer(offer, llm)
    assert grounded.work_mode == [WorkMode.HYBRID]
    assert grounded.seniority == Seniority.SENIOR
    assert grounded.seniority_evidence == Evidence(field="seniority", quote="Senior")
    assert llm.seen == []


async def test_ground_offer_fills_only_missing_fields_from_llm() -> None:
    offer = _offer("Data Engineer", EN_TEXT)
    llm = ScriptedLLM(
        [{"seniority": None, "seniority_quote": None, "work_mode": ["remote"], "work_mode_quote": "fully remote"}]
    )
    grounded = await ground_offer(offer, llm)
    assert grounded.work_mode == [WorkMode.REMOTE]
    assert grounded.work_mode_evidence == Evidence(field="work_mode", quote="fully remote")
    assert grounded.seniority is None
    assert grounded.seniority_confidence == "not_found"


@respx.mock
async def test_client_caches_responses_on_disk(tmp_path: Path) -> None:
    route = respx.post("https://llm.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
    )
    client = OpenAICompatibleClient("https://llm.test/v1", "k", "m", cache_dir=tmp_path)
    messages = [{"role": "user", "content": "hi"}]
    assert await client.complete(messages) == "{}"
    assert await client.complete(messages) == "{}"
    assert route.call_count == 1
    assert len(list(tmp_path.glob("*.json"))) == 1
