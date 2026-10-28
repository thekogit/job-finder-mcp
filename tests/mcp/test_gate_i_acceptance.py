from datetime import datetime

import pytest

from job_scout.models import WARSAW_TZ
from job_scout.server import check_validity, search_jobs


@pytest.mark.live
@pytest.mark.asyncio
async def test_gate_i_acceptance():
    # Acceptance query:
    # "Find me fresh Python jobs in Warsaw or remote, hybrid or remote only, posted in the last 7 days, with salary info."
    res = await search_jobs(
        keywords="Python",
        work_modes=["hybrid", "remote"],
        max_age_days=7,
        only_with_salary=True,
        limit=10,
    )

    print(f"\n[GATE I] Search returned {len(res.jobs)} jobs (total: {res.total})")
    assert len(res.jobs) > 0, "Gate I search returned 0 jobs"

    now = datetime.now(WARSAW_TZ)
    urls_to_verify = []

    for idx, job in enumerate(res.jobs, start=1):
        print(f"\nOffer #{idx}:")
        print(f"  Title:    {job.title}")
        print(f"  Company:  {job.company}")
        print(f"  Salary:   {job.salary[0].raw if job.salary else None}")
        print(f"  Location: {job.location}")
        print(f"  Modes:    {job.work_mode}")
        print(f"  Link:     {job.link}")
        print(f"  Posted:   {job.posted_at}")

        # Constraint 1: non-null salary
        assert job.salary is not None and len(job.salary) > 0, f"Job {job.id} has no salary info"

        # Constraint 2: work modes include hybrid or remote
        assert job.work_mode is not None and len(job.work_mode) > 0, f"Job {job.id} has no work mode"
        assert any(m in ("hybrid", "remote") for m in job.work_mode), (
            f"Job {job.id} work mode {job.work_mode} does not match hybrid or remote"
        )

        # Constraint 3: posted in the last 7 days (if date known)
        if job.posted_at:
            dt = datetime.fromisoformat(job.posted_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=WARSAW_TZ)
            age_days = (now - dt).total_seconds() / 86400.0
            print(f"  Age:      {age_days:.1f} days")
            assert age_days <= 7.05, f"Job {job.id} posted {age_days:.1f} days ago (> 7 days)"

        urls_to_verify.append(job.link)

    # Constraint 4: every link is valid HTTP 200
    validity = await check_validity(urls=urls_to_verify)
    print(f"\n[GATE I] Validity check for {len(validity)} URLs:")
    for v in validity:
        print(f"  {v.url} -> is_valid={v.is_valid} ({v.reason})")
        assert v.is_valid is True, f"URL {v.url} is not valid: {v.reason}"

    print("\n[GATE I] All acceptance constraints PASSED!")
