import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from job_scout.normalize.text import is_verbatim_quote

WARSAW_TZ = ZoneInfo("Europe/Warsaw")


class WorkMode(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"


class SalaryPeriod(StrEnum):
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"
    YEAR = "year"


class SalaryGrossNet(StrEnum):
    GROSS = "gross"
    NET = "net"
    UNKNOWN = "unknown"


class SalaryContract(StrEnum):
    UOP = "uop"
    B2B = "b2b"
    UZ = "uz"
    UOD = "uod"
    OTHER = "other"
    UNKNOWN = "unknown"


# ISO 4217 codes this project can meet on Polish/EU boards. A code outside this set is
# rejected rather than guessed; extend the set when a board starts publishing another one.
SUPPORTED_CURRENCIES: frozenset[str] = frozenset(
    {"PLN", "EUR", "USD", "GBP", "CHF", "UAH", "CZK", "SEK", "NOK", "DKK", "HUF", "RON"}
)


class SalaryRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: float | int | None = None
    max: float | int | None = None
    currency: str = "PLN"
    period: SalaryPeriod = SalaryPeriod.MONTH
    gross_net: SalaryGrossNet = SalaryGrossNet.UNKNOWN
    contract: SalaryContract = SalaryContract.UNKNOWN
    raw: str

    @model_validator(mode="after")
    def _check_band(self) -> Self:
        problems: list[str] = []
        if self.min is None and self.max is None:
            problems.append("at least one of min/max is required")
        for name, value in (("min", self.min), ("max", self.max)):
            if value is not None and not value > 0:
                problems.append(f"{name} must be positive, got {value}")
        if self.min is not None and self.max is not None and self.min > self.max:
            problems.append(f"min ({self.min}) is greater than max ({self.max})")
        if self.currency not in SUPPORTED_CURRENCIES:
            problems.append(f"currency {self.currency!r} is not a supported ISO 4217 code")
        if not self.raw.strip():
            problems.append("raw must be non-empty")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class Seniority(StrEnum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"


class Evidence(BaseModel):
    """A verbatim quote from the listing that supports one extracted field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: Literal["seniority", "work_mode"]
    quote: str = Field(min_length=1)


class JobOffer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    link: str
    source: str
    title: str
    company: str | None = None
    location: str | None = None
    description: str
    description_truncated: bool = False
    requirements: list[str] = Field(default_factory=list)
    requirements_confidence: Literal["structured", "section", "not_found"] = "not_found"
    nice_to_have: list[str] = Field(default_factory=list)
    salary: list[SalaryRange] | None = None
    work_mode: list[WorkMode] | None = None
    raw_work_mode: str | None = None
    contract_types: list[str] = Field(default_factory=list)
    posted_at: str | None = None
    valid_until: str | None = None
    date_confidence: Literal["exact", "relative", "unknown"] = "unknown"
    first_seen_at: str
    last_checked_at: str
    is_valid: bool = True
    also_on: list[str] = Field(default_factory=list)
    seniority: Seniority | None = None
    seniority_evidence: Evidence | None = None
    seniority_confidence: Literal["quoted", "not_found"] = "not_found"
    work_mode_evidence: Evidence | None = None

    @model_validator(mode="after")
    def _check_evidence_is_verbatim(self) -> Self:
        source_text = f"{self.title}\n{self.description}"
        bad: list[str] = []
        for evidence in (self.seniority_evidence, self.work_mode_evidence):
            if evidence is not None and not is_verbatim_quote(evidence.quote, source_text):
                bad.append(f"{evidence.field}: {evidence.quote!r}")
        if bad:
            raise ValueError(
                "evidence quotes are not substrings of the listing title/description: "
                + "; ".join(bad)
            )
        if self.seniority is not None and self.seniority_evidence is None:
            raise ValueError("seniority is set without a verbatim seniority_evidence quote")
        if self.seniority_confidence == "quoted" and self.seniority is None:
            raise ValueError("seniority_confidence is 'quoted' but seniority is empty")
        return self


class SourceFetchStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    ERROR = "error"
    DISABLED = "disabled"
    TIMEOUT = "timeout"


class SourceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: SourceFetchStatus
    count: int = 0
    error: str | None = None


class SearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: str | None = None
    sources: list[str] | None = None
    max_age_days: int = 14
    work_modes: list[str] | None = None
    salary_min_pln_month: int | None = None
    only_with_salary: bool = False
    include_metro: bool = False
    verify_validity: bool = True
    limit: int = 50
    offset: int = 0


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: dict[str, Any]
    generated_at: str
    sources: list[SourceReport]
    total: int
    offset: int
    returned: int
    jobs: list[JobOffer]


class ValidityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    is_valid: bool
    reason: str | None = None
    checked_at: str


class SourceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    tier: int
    enabled: bool
    robots_ok: bool
    last_success_at: str | None = None
    last_error: str | None = None


def now_warsaw_iso() -> str:
    return datetime.now(WARSAW_TZ).isoformat()


def export_schemas(output_dir: Path | str = "schema") -> None:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    job_offer_schema = JobOffer.model_json_schema()
    search_result_schema = SearchResult.model_json_schema()

    (target / "job_offer.schema.json").write_text(
        json.dumps(job_offer_schema, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (target / "search_result.schema.json").write_text(
        json.dumps(search_result_schema, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    export_schemas()
