import hashlib
import json
import logging
import re
import sqlite3
import time
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from job_scout.models import JobOffer, now_warsaw_iso

logger = logging.getLogger("job_scout.store")


def get_app_dir() -> Path:
    try:
        app_dir = Path.home() / ".job-scout"
        app_dir.mkdir(parents=True, exist_ok=True)
        probe = app_dir / ".probe"
        probe.touch()
        probe.unlink(missing_ok=True)
        return app_dir
    except (PermissionError, OSError):
        app_dir = Path.cwd() / ".job-scout"
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    tracking_prefixes = ("utm_", "ref", "trk", "tracking", "source", "fbclid", "gclid")
    query_params = []
    for k, v in parse_qsl(parsed.query, keep_blank_values=True):
        lk = k.lower()
        if any(lk.startswith(prefix) for prefix in tracking_prefixes):
            continue
        query_params.append((k, v))

    clean_query = urlencode(sorted(query_params))
    # Normalize scheme to https and strip trailing slash from path if path is not root
    path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
    return urlunparse(("https", parsed.netloc.lower(), path, "", clean_query, ""))


def compute_job_id(canonical_url: str) -> str:
    return hashlib.sha1(canonical_url.encode("utf-8")).hexdigest()


def remove_diacritics(text: str) -> str:
    cleaned = text.replace("ł", "l").replace("Ł", "L")
    normalized = unicodedata.normalize("NFKD", cleaned)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def normalize_for_dedup(text: str | None) -> str:
    if not text:
        return ""
    clean = remove_diacritics(text.lower())
    # Strip common legal suffixes
    legal_suffixes = [
        r"\bsp[\.\s]+z\s+o[\.\s]+o\b",
        r"\bspolka\s+z\s+ograniczona\s+odpowiedzialnoscia\b",
        r"\bs[\.\s]*a\b",
        r"\bsp[\.\s]+k\b",
        r"\bsp[\.\s]+j\b",
        r"\bgmbh\b",
        r"\bltd\b",
        r"\binc\b",
        r"\bcorp\b",
        r"\bllc\b",
    ]
    for pattern in legal_suffixes:
        clean = re.sub(pattern, " ", clean)
    clean = re.sub(r"[^\w\s]", " ", clean)
    return " ".join(clean.split())


def compute_dedup_key(company: str | None, title: str, location: str | None) -> str:
    norm_company = normalize_for_dedup(company)
    norm_title = normalize_for_dedup(title)
    city = "warszawa"
    if location:
        norm_loc = normalize_for_dedup(location)
        if "warszaw" in norm_loc:
            city = "warszawa"
        else:
            city = norm_loc
    return f"{norm_company}|{norm_title}|{city}"


class JobStore:
    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            self.db_path = get_app_dir() / "jobs.db"
        else:
            self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    canonical_link TEXT UNIQUE,
                    source TEXT,
                    title TEXT,
                    company TEXT,
                    location TEXT,
                    dedup_key TEXT,
                    first_seen_at TEXT,
                    last_checked_at TEXT,
                    is_valid INTEGER,
                    data_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_dedup ON jobs(dedup_key)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    cache_key TEXT PRIMARY KEY,
                    data_json TEXT,
                    created_at REAL,
                    ttl_seconds REAL,
                    cache_type TEXT
                )
                """
            )
            conn.commit()

    def get_job_by_canonical_link(self, canonical_link: str) -> JobOffer | None:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT data_json FROM jobs WHERE canonical_link = ?", (canonical_link,)
            )
            row = cursor.fetchone()
            if row:
                data = json.loads(row["data_json"])
                return JobOffer.model_validate(data)
            return None

    def save_or_update_job(self, offer: JobOffer) -> JobOffer:
        canon_url = canonicalize_url(offer.link)
        job_id = compute_job_id(canon_url)
        now_iso = now_warsaw_iso()

        existing = self.get_job_by_canonical_link(canon_url)
        if existing:
            first_seen = existing.first_seen_at
            also_on = sorted(list(set(existing.also_on + offer.also_on)))
        else:
            first_seen = offer.first_seen_at or now_iso
            also_on = offer.also_on

        updated_offer = offer.model_copy(
            update={
                "id": job_id,
                "link": canon_url,
                "first_seen_at": first_seen,
                "last_checked_at": now_iso,
                "also_on": also_on,
            }
        )

        dedup_key = compute_dedup_key(
            updated_offer.company, updated_offer.title, updated_offer.location
        )

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, canonical_link, source, title, company, location,
                    dedup_key, first_seen_at, last_checked_at, is_valid, data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(canonical_link) DO UPDATE SET
                    title = excluded.title,
                    company = excluded.company,
                    location = excluded.location,
                    dedup_key = excluded.dedup_key,
                    last_checked_at = excluded.last_checked_at,
                    is_valid = excluded.is_valid,
                    data_json = excluded.data_json
                """,
                (
                    job_id,
                    canon_url,
                    updated_offer.source,
                    updated_offer.title,
                    updated_offer.company,
                    updated_offer.location,
                    dedup_key,
                    first_seen,
                    now_iso,
                    1 if updated_offer.is_valid else 0,
                    updated_offer.model_dump_json(),
                ),
            )
            conn.commit()

        return updated_offer

    def get_cached(self, cache_key: str) -> str | None:
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT data_json, created_at, ttl_seconds FROM cache WHERE cache_key = ?",
                (cache_key,),
            )
            row = cursor.fetchone()
            if row:
                created = row["created_at"]
                ttl = row["ttl_seconds"]
                if now - created < ttl:
                    return str(row["data_json"])
                conn.execute("DELETE FROM cache WHERE cache_key = ?", (cache_key,))
                conn.commit()
            return None

    def set_cached(
        self, cache_key: str, data_json: str, ttl_seconds: float, cache_type: str = "general"
    ) -> None:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cache (cache_key, data_json, created_at, ttl_seconds, cache_type)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    data_json = excluded.data_json,
                    created_at = excluded.created_at,
                    ttl_seconds = excluded.ttl_seconds,
                    cache_type = excluded.cache_type
                """,
                (cache_key, data_json, now, ttl_seconds, cache_type),
            )
            conn.commit()

    def deduplicate_offers(self, offers: list[JobOffer]) -> list[JobOffer]:
        groups: dict[str, list[JobOffer]] = {}
        for offer in offers:
            key = compute_dedup_key(offer.company, offer.title, offer.location)
            if key not in groups:
                groups[key] = []
            groups[key].append(offer)

        deduped: list[JobOffer] = []
        for _, group in groups.items():
            if len(group) == 1:
                deduped.append(group[0])
                continue

            def sort_score(o: JobOffer) -> tuple[int, int]:
                has_salary = 1 if o.salary and len(o.salary) > 0 else 0
                desc_len = len(o.description)
                return (has_salary, desc_len)

            sorted_group = sorted(group, key=sort_score, reverse=True)
            primary = sorted_group[0]
            other_links = [
                o.link
                for o in sorted_group[1:]
                if canonicalize_url(o.link) != canonicalize_url(primary.link)
            ]
            merged_also_on = sorted(list(set(primary.also_on + other_links)))
            merged_offer = primary.model_copy(update={"also_on": merged_also_on})
            deduped.append(merged_offer)

        return deduped


_shared_store: JobStore | None = None


def get_store() -> JobStore:
    global _shared_store
    if _shared_store is None:
        _shared_store = JobStore()
    return _shared_store

