import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

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


class SalaryRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: float | int | None = None
    max: float | int | None = None
    currency: str = "PLN"
    period: SalaryPeriod = SalaryPeriod.MONTH
    gross_net: SalaryGrossNet = SalaryGrossNet.UNKNOWN
    contract: SalaryContract = SalaryContract.UNKNOWN
    raw: str


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
