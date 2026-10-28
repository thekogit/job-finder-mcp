import asyncio
import email.utils
import logging
import sys
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from job_scout.store import get_app_dir

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

logger = logging.getLogger("job_scout.http")


def setup_logging() -> None:
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    )

    # Stderr handler (NEVER stdout per Section 3.3)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    root_logger.addHandler(stderr_handler)

    # File handler to ~/.job-scout/server.log
    try:
        log_file = get_app_dir() / "server.log"
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        sys.stderr.write(f"Failed to initialize file logger: {e}\n")


class HostRateLimiter:
    def __init__(self, min_interval_seconds: float = 2.0, max_concurrent: int = 2) -> None:
        self.min_interval = min_interval_seconds
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.lock = asyncio.Lock()
        self.last_request_time: float = 0.0

    async def acquire(self) -> None:
        await self.semaphore.acquire()
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_request_time
            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed
                await asyncio.sleep(wait_time)
            self.last_request_time = time.monotonic()

    def release(self) -> None:
        self.semaphore.release()


class HttpClient:
    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 30.0,
        min_interval_seconds: float = 2.0,
        max_concurrent: int = 2,
    ) -> None:
        setup_logging()
        self.user_agent = user_agent
        self.timeout = timeout
        self.min_interval_seconds = min_interval_seconds
        self.max_concurrent = max_concurrent
        self._limiters: dict[str, HostRateLimiter] = {}
        self._robots_parsers: dict[str, RobotFileParser] = {}
        self._robots_checked: set[str] = set()

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
            "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
            "DNT": "1",
        }
        self._h1_hosts: set[str] = {
            "pracuj.pl",
            "www.pracuj.pl",
            "theprotocol.it",
            "www.theprotocol.it",
        }
        self.client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
            headers=headers,
        )
        self.client_h1 = httpx.AsyncClient(
            http2=False,
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
            headers=headers,
        )

    def _get_limiter(self, host: str) -> HostRateLimiter:
        if host not in self._limiters:
            self._limiters[host] = HostRateLimiter(
                min_interval_seconds=self.min_interval_seconds,
                max_concurrent=self.max_concurrent,
            )
        return self._limiters[host]

    async def check_robots(self, url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host not in self._robots_checked:
            self._robots_checked.add(host)
            robots_url = f"{parsed.scheme}://{host}/robots.txt"
            parser = RobotFileParser()
            parser.set_url(robots_url)
            active_client = (
                self.client_h1 if host in self._h1_hosts else self.client
            )
            try:
                # Use raw client directly without strict rate limits for robots
                resp = await active_client.get(robots_url, timeout=10.0)
                if resp.status_code == 200:
                    parser.parse(resp.text.splitlines())
                    self._robots_parsers[host] = parser
                    logger.info("Fetched robots.txt for host %s", host)
                else:
                    self._robots_parsers[host] = parser
            except Exception as e:
                logger.warning("Failed to fetch robots.txt for %s: %s", host, e)
                self._robots_parsers[host] = parser

        cached_parser = self._robots_parsers.get(host)
        if cached_parser is None:
            return True
        try:
            return bool(cached_parser.can_fetch(self.user_agent, url))
        except Exception:
            return True

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str | int] | None = None,
        json_data: dict[str, object] | None = None,
        max_retries: int = 3,
        base_backoff: float = 5.0,
    ) -> httpx.Response:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        limiter = self._get_limiter(host)

        attempt = 0
        while True:
            await limiter.acquire()
            try:
                active_client = (
                    self.client_h1 if host in self._h1_hosts else self.client
                )
                logger.info("%s %s (attempt %d)", method, url, attempt + 1)
                resp = await active_client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_data,
                )

                if resp.status_code == 403 and active_client is self.client:
                    logger.warning(
                        "Received HTTP 403 over HTTP/2 for %s; retrying with HTTP/1.1",
                        url,
                    )
                    self._h1_hosts.add(host)
                    resp = await self.client_h1.request(
                        method=method,
                        url=url,
                        headers=headers,
                        params=params,
                        json=json_data,
                    )

                if resp.status_code in (429, 503) and attempt < max_retries:
                    retry_after = resp.headers.get("Retry-After")
                    delay = base_backoff * (2**attempt)
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            try:
                                date_tuple = email.utils.parsedate_tz(retry_after)
                                if date_tuple:
                                    target_ts = email.utils.mktime_tz(date_tuple)
                                    delay = max(0.0, target_ts - time.time())
                            except Exception as parse_err:
                                logger.debug("Retry-After parse failed: %s", parse_err)
                    logger.warning(
                        "Received HTTP %d for %s. Backing off for %.1fs (attempt %d/%d)",
                        resp.status_code,
                        url,
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue

                return resp
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as net_err:
                if attempt < max_retries:
                    delay = 2.0 * (attempt + 1)
                    logger.warning(
                        "Network error %s for %s. Retrying in %.1fs (attempt %d/%d)",
                        net_err,
                        url,
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue
                raise
            finally:
                limiter.release()

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str | int] | None = None,
        max_retries: int = 3,
    ) -> httpx.Response:
        return await self.request(
            "GET", url, headers=headers, params=params, max_retries=max_retries
        )

    async def post(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        json_data: dict[str, object] | None = None,
        max_retries: int = 3,
    ) -> httpx.Response:
        return await self.request(
            "POST", url, headers=headers, json_data=json_data, max_retries=max_retries
        )

    async def close(self) -> None:
        await self.client.aclose()
        await self.client_h1.aclose()


_shared_client: HttpClient | None = None


def get_http_client() -> HttpClient:
    global _shared_client
    if _shared_client is None:
        _shared_client = HttpClient()
    return _shared_client
