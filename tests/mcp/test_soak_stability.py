import time

import pytest

from job_scout.server import search_jobs
from job_scout.store import get_store


@pytest.mark.live
@pytest.mark.asyncio
async def test_soak_and_stability():
    store = get_store()
    # Invalidate cache table first to guarantee run 1 is live
    with store._get_connection() as conn:
        conn.execute("DELETE FROM cache")

    test_query = {
        "sources": ["justjoin"],
        "keywords": "python",
        "limit": 5,
        "max_age_days": 14,
    }

    # Run 1 (live fetch)
    t0 = time.perf_counter()
    res1 = await search_jobs(**test_query)
    t1 = time.perf_counter()
    dur1 = t1 - t0

    # Run 2 (cached)
    t2 = time.perf_counter()
    res2 = await search_jobs(**test_query)
    t3 = time.perf_counter()
    dur2 = t3 - t2

    # Run 3 (cached)
    t4 = time.perf_counter()
    res3 = await search_jobs(**test_query)
    t5 = time.perf_counter()
    dur3 = t5 - t4

    print(f"\n[SOAK] Run 1 duration: {dur1:.4f}s ({len(res1.jobs)} jobs)")
    print(f"[SOAK] Run 2 duration: {dur2:.4f}s ({len(res2.jobs)} jobs)")
    print(f"[SOAK] Run 3 duration: {dur3:.4f}s ({len(res3.jobs)} jobs)")

    # Assertions per Section 8.8:
    # 1. Runs 2 and 3 served from cache, wall-clock time >= 5x faster
    speedup2 = dur1 / max(dur2, 0.0001)
    speedup3 = dur1 / max(dur3, 0.0001)
    print(f"[SOAK] Speedup run 2: {speedup2:.1f}x, run 3: {speedup3:.1f}x")
    assert speedup2 >= 5.0, f"Run 2 speedup was only {speedup2:.1f}x (expected >= 5x)"
    assert speedup3 >= 5.0, f"Run 3 speedup was only {speedup3:.1f}x (expected >= 5x)"

    # 2. Returned offer IDs identical across runs
    ids1 = [o.id for o in res1.jobs]
    ids2 = [o.id for o in res2.jobs]
    ids3 = [o.id for o in res3.jobs]
    assert len(ids1) > 0, "Expected non-zero jobs returned"
    assert ids1 == ids2, "Offer IDs differ between Run 1 and Run 2"
    assert ids2 == ids3, "Offer IDs differ between Run 2 and Run 3"

    # 3. Zero duplicate records in SQLite (COUNT(DISTINCT id) == COUNT(*))
    store = get_store()
    with store._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT id), COUNT(*) FROM jobs")
        distinct_count, total_count = cursor.fetchone()
        print(f"[SOAK] DB jobs: distinct={distinct_count}, total={total_count}")
        assert distinct_count == total_count, (
            f"Duplicate records found in SQLite: {distinct_count} distinct vs {total_count} total"
        )
