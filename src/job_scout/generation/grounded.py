"""Grounded field extraction: every value carries a verbatim quote, or it is empty.

Order of work for one offer:

1. Deterministic: a seniority keyword in the title is its own quote; the board's raw
   work-mode text becomes the work-mode quote when it occurs verbatim in the listing.
2. LLM, only for fields still empty: the model must return the value *and* a quote that
   is a substring of the listing (whitespace/NBSP normalised only; no case folding, no
   translation). A failed check is sent back verbatim and the model may retry at most
   ``MAX_RETRIES`` times. After that the field is ``None`` with confidence ``not_found``.

A structured value from the board's own JSON is never overridden.
"""

import hashlib
import json
import logging
import os
import re
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, Self

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, ValidationInfo, model_validator

from job_scout.models import Evidence, JobOffer, Seniority, WorkMode
from job_scout.normalize.text import is_verbatim_quote
from job_scout.store import get_app_dir

logger = logging.getLogger(__name__)

MAX_RETRIES = 2

# --- deterministic seniority -------------------------------------------------------------

_SENIORITY_PATTERNS: tuple[tuple[Seniority, re.Pattern[str]], ...] = (
    (
        Seniority.INTERN,
        re.compile(
            r"\b(?:Intern|Internship|Trainee|Stażysta|Stażystka|Praktykant(?:ka)?|Стажер|Стажист)\b",
            re.IGNORECASE,
        ),
    ),
    (Seniority.JUNIOR, re.compile(r"\b(?:Junior|Jr\.?|Młodszy|Młodsza|Молодший)\b", re.IGNORECASE)),
    (Seniority.MID, re.compile(r"\b(?:Mid|Regular|Middle|Mid-level)\b", re.IGNORECASE)),
    (Seniority.SENIOR, re.compile(r"\b(?:Senior|Sr\.?|Starszy|Starsza|Старший)\b", re.IGNORECASE)),
    (Seniority.LEAD, re.compile(r"\b(?:Lead|Principal|Staff|Head of)\b", re.IGNORECASE)),
)


def deterministic_seniority(title: str) -> tuple[Seniority, Evidence] | None:
    """Seniority named in the title, quoted verbatim. Ambiguous titles return None.

    "Mid/Senior Python Developer" names two levels, so it is left to the reader rather
    than resolved by a rule.
    """
    hits: dict[Seniority, str] = {}
    for level, pattern in _SENIORITY_PATTERNS:
        match = pattern.search(title)
        if match:
            hits[level] = match.group(0)
    if len(hits) != 1:
        return None
    level, quote = next(iter(hits.items()))
    return level, Evidence(field="seniority", quote=quote)


# --- LLM client ---------------------------------------------------------------------------


class LLMClient(Protocol):
    model: str

    def complete(self, messages: list[dict[str, str]]) -> Awaitable[str]: ...


def _load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def default_cache_dir() -> Path:
    override = os.environ.get("JOB_SCOUT_LLM_CACHE_DIR")
    return Path(override) if override else get_app_dir() / "llm_cache"


class OpenAICompatibleClient:
    """Minimal chat-completions client with an on-disk response cache.

    The cache key is the SHA-256 of the model name and the exact message list, so a rerun
    with the same prompt never calls the API again (reproducible evals, resumable runs).
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        cache_dir: Path | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self.cache_dir = cache_dir or default_cache_dir()
        self.timeout = timeout

    @classmethod
    def from_env(cls, dotenv: Path | None = Path(".env")) -> "OpenAICompatibleClient | None":
        """Build a client from LLM_BASE_URL / LLM_API_KEY / LLM_MODEL, or None if unset."""
        file_values = _load_dotenv(dotenv) if dotenv is not None else {}

        def get(name: str) -> str | None:
            return os.environ.get(name) or file_values.get(name) or None

        base_url, api_key, model = get("LLM_BASE_URL"), get("LLM_API_KEY"), get("LLM_MODEL")
        if not (base_url and api_key and model):
            return None
        return cls(base_url=base_url, api_key=api_key, model=model)

    def cache_key(self, messages: list[dict[str, str]]) -> str:
        payload = json.dumps({"model": self.model, "messages": messages}, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def complete(self, messages: list[dict[str, str]]) -> str:
        key = self.cache_key(messages)
        path = self.cache_dir / f"{key}.json"
        if path.is_file():
            cached: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return str(cached["content"])

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            body = resp.json()
        content = str(body["choices"][0]["message"]["content"] or "")

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"model": self.model, "messages": messages, "content": content},
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        return content


# --- validated LLM answer -----------------------------------------------------------------


class GroundedFields(BaseModel):
    """The LLM's answer. Validate with ``context={"source_text": listing_text}``."""

    model_config = ConfigDict(extra="forbid")

    seniority: Seniority | None = None
    seniority_quote: str | None = None
    work_mode: list[WorkMode] | None = None
    work_mode_quote: str | None = None

    @model_validator(mode="after")
    def _quotes_are_verbatim(self, info: ValidationInfo) -> Self:
        if all(
            v is None
            for v in (self.seniority, self.seniority_quote, self.work_mode, self.work_mode_quote)
        ):
            return self  # an empty answer has nothing to ground
        context = info.context if isinstance(info.context, dict) else {}
        source_text = context.get("source_text")
        if not isinstance(source_text, str):
            raise ValueError("validation context must carry the listing as 'source_text'")
        errors = field_errors(self, source_text)
        if errors:
            raise ValueError(" | ".join(errors))
        return self


def field_errors(fields: GroundedFields, source_text: str) -> list[str]:
    errors: list[str] = []
    pairs: tuple[tuple[str, object, str | None], ...] = (
        ("seniority", fields.seniority, fields.seniority_quote),
        ("work_mode", fields.work_mode or None, fields.work_mode_quote),
    )
    for name, value, quote in pairs:
        if value is None and quote is None:
            continue
        if value is None:
            errors.append(f"{name}_quote is given but {name} is null; set both or neither")
        elif quote is None or not quote.strip():
            errors.append(f"{name} is set but {name}_quote is empty; quote the listing or use null")
        elif not is_verbatim_quote(quote, source_text):
            errors.append(
                f"{name}_quote {quote!r} is not an exact substring of the listing; copy it "
                "character for character in the listing's own language, or use null"
            )
    return errors


SYSTEM_PROMPT = """You extract two fields from one job listing and justify each with a quote.

Return one JSON object and nothing else:
{"seniority": "intern"|"junior"|"mid"|"senior"|"lead"|null,
 "seniority_quote": string|null,
 "work_mode": ["onsite"|"hybrid"|"remote", ...]|null,
 "work_mode_quote": string|null}

Rules:
- A quote is copied character for character from the listing, in the listing's own
  language (Polish, Ukrainian or English). Never translate, paraphrase or change case.
- Keep quotes short: the few words that state the value.
- Seniority only when the listing names the level. Do not derive it from years of
  experience or salary.
- If the listing does not state a field, set the value and its quote to null."""


@dataclass
class Attempt:
    number: int
    raw: str
    errors: list[str]


@dataclass
class GroundingOutcome:
    fields: GroundedFields
    attempts: list[Attempt] = field(default_factory=list)
    status: Literal["grounded_first_try", "grounded_after_retry", "partial", "abstained"] = "abstained"


def _parse_answer(raw: str, source_text: str) -> tuple[GroundedFields | None, list[str]]:
    try:
        return GroundedFields.model_validate_json(raw, context={"source_text": source_text}), []
    except ValidationError as err:
        return None, [f"{'.'.join(str(p) for p in e['loc']) or 'answer'}: {e['msg']}" for e in err.errors()]


def _salvage(raw: str, source_text: str) -> GroundedFields:
    """Keep each field of the last answer that is grounded on its own; drop the rest."""
    try:
        data = json.loads(raw)
        candidate = GroundedFields.model_construct(
            seniority=Seniority(data["seniority"]) if data.get("seniority") else None,
            seniority_quote=data.get("seniority_quote"),
            work_mode=[WorkMode(m) for m in data["work_mode"]] if data.get("work_mode") else None,
            work_mode_quote=data.get("work_mode_quote"),
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        return GroundedFields()
    keep: dict[str, Any] = {}
    for name in ("seniority", "work_mode"):
        single = GroundedFields.model_construct(
            **{name: getattr(candidate, name), f"{name}_quote": getattr(candidate, f"{name}_quote")}
        )
        if not field_errors(single, source_text) and getattr(candidate, name) is not None:
            keep[name] = getattr(candidate, name)
            keep[f"{name}_quote"] = getattr(candidate, f"{name}_quote")
    return GroundedFields.model_validate(keep, context={"source_text": source_text})


def _log_attempts(client: LLMClient, source_text: str, outcome: GroundingOutcome) -> None:
    cache_dir = getattr(client, "cache_dir", None)
    if not isinstance(cache_dir, Path):
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "at": datetime.now(UTC).isoformat(),
        "model": client.model,
        "listing_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "status": outcome.status,
        "attempts": [{"n": a.number, "errors": a.errors, "raw": a.raw} for a in outcome.attempts],
    }
    with (cache_dir / "attempts.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


async def extract_grounded(
    source_text: str, client: LLMClient, max_retries: int = MAX_RETRIES
) -> GroundingOutcome:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Listing:\n<<<\n{source_text}\n>>>"},
    ]
    outcome = GroundingOutcome(fields=GroundedFields())
    raw = ""
    for number in range(1, max_retries + 2):
        raw = await client.complete(messages)
        parsed, errors = _parse_answer(raw, source_text)
        outcome.attempts.append(Attempt(number=number, raw=raw, errors=errors))
        if parsed is not None:
            outcome.fields = parsed
            outcome.status = "grounded_first_try" if number == 1 else "grounded_after_retry"
            break
        messages = [
            *messages,
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": "Your answer failed validation:\n- "
                + "\n- ".join(errors)
                + "\nReturn the corrected JSON object only.",
            },
        ]
    else:
        outcome.fields = _salvage(raw, source_text)
        has_any = outcome.fields.seniority is not None or outcome.fields.work_mode is not None
        outcome.status = "partial" if has_any else "abstained"
    _log_attempts(client, source_text, outcome)
    return outcome


# --- applying grounding to an offer -------------------------------------------------------


def listing_text(offer: JobOffer) -> str:
    """The exact text that evidence quotes are checked against (see JobOffer validator)."""
    return f"{offer.title}\n{offer.description}"


def ground_deterministic(offer: JobOffer) -> JobOffer:
    update: dict[str, Any] = {}
    if offer.seniority is None:
        found = deterministic_seniority(offer.title)
        if found is not None:
            level, evidence = found
            update.update(seniority=level, seniority_evidence=evidence, seniority_confidence="quoted")
    if (
        offer.work_mode
        and offer.work_mode_evidence is None
        and offer.raw_work_mode
        and len(offer.raw_work_mode) <= 200
        and is_verbatim_quote(offer.raw_work_mode, listing_text(offer))
    ):
        update["work_mode_evidence"] = Evidence(field="work_mode", quote=offer.raw_work_mode)
    if not update:
        return offer
    return JobOffer.model_validate({**offer.model_dump(), **update})


async def ground_offer(offer: JobOffer, client: LLMClient | None) -> JobOffer:
    """Deterministic grounding, then the LLM for whatever is still empty (if a client is set)."""
    offer = ground_deterministic(offer)
    if client is None or (offer.seniority is not None and offer.work_mode is not None):
        return offer
    text = listing_text(offer)
    try:
        outcome = await extract_grounded(text, client)
    except (httpx.HTTPError, KeyError, ValueError) as err:
        logger.warning("Grounded extraction failed for %s: %s", offer.link, err)
        return offer

    update: dict[str, Any] = {}
    f = outcome.fields
    if offer.seniority is None and f.seniority is not None and f.seniority_quote:
        update.update(
            seniority=f.seniority,
            seniority_evidence=Evidence(field="seniority", quote=f.seniority_quote),
            seniority_confidence="quoted",
        )
    if offer.work_mode is None and f.work_mode and f.work_mode_quote:
        update.update(
            work_mode=f.work_mode,
            work_mode_evidence=Evidence(field="work_mode", quote=f.work_mode_quote),
        )
    if not update:
        return offer
    return JobOffer.model_validate({**offer.model_dump(), **update})
