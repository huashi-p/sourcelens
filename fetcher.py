import asyncio
import re
import time
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from schemas import SourceRequest, SourceStatus
from url_guard import SourceReadError, validate_public_url


MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_RETRIES = 2
RETRYABLE_CODES = {"timeout", "network_error", "http_429", "http_5xx"}
ALLOWED_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
}

MAX_TEXT_CHARS = 20000
MAX_CONCURRENT = 2
SOURCE_TIMEOUT = 10.0


def extract_text(html):
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(
        ["script", "style", "noscript", "svg", "nav", "footer", "form"]
    ):
        tag.decompose()

    root = (
        soup.find("main")
        or soup.find("article")
        or soup.body
        or soup
    )
    text = root.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:MAX_TEXT_CHARS]


async def fetch_once(client, url):
    current_url = await validate_public_url(url)

    for redirect_count in range(MAX_REDIRECTS + 1):
        async with client.stream("GET", current_url) as response:
            if 300 <= response.status_code < 400:
                location = response.headers.get("location")

                if not location or redirect_count >= MAX_REDIRECTS:
                    raise SourceReadError(
                        "invalid_redirect",
                        "重定向无效或次数过多",
                    )

                next_url = urljoin(str(response.url), location)
                current_url = await validate_public_url(next_url)
                continue

            if response.status_code == 429:
                raise SourceReadError("http_429", "来源正在限流")

            if response.status_code >= 500:
                raise SourceReadError(
                    "http_5xx",
                    f"来源返回 HTTP {response.status_code}",
                )

            if response.status_code >= 400:
                raise SourceReadError(
                    "http_error",
                    f"来源返回 HTTP {response.status_code}",
                )

            content_type = (
                response.headers.get("content-type", "")
                .split(";")[0]
                .strip()
                .lower()
            )

            if content_type not in ALLOWED_CONTENT_TYPES:
                raise SourceReadError(
                    "content_type",
                    f"不支持的内容类型：{content_type or '未知'}",
                )

            body = bytearray()

            async for chunk in response.aiter_bytes():
                body.extend(chunk)

                if len(body) > MAX_RESPONSE_BYTES:
                    raise SourceReadError(
                        "response_too_large",
                        "响应超过 2 MB",
                    )

            html = bytes(body).decode(
                response.encoding or "utf-8",
                errors="replace",
            )
            return current_url, html


async def fetch_with_retry(client, url):
        for attempt in range(MAX_RETRIES + 1):
            try:
                return await fetch_once(client, url)
            except SourceReadError as e:
                if e.code not in RETRYABLE_CODES:
                    raise
                if attempt >= MAX_RETRIES:
                    raise
            except httpx.TimeoutException as e:
                if attempt >= MAX_RETRIES:
                    raise SourceReadError("timeout", "来源请求超时") from e
            except httpx.TransportError as e:
                if attempt >= MAX_RETRIES:
                    raise SourceReadError("network_error", "网络请求失败") from e

            await asyncio.sleep(0.4 * (2 ** attempt))


async def fetch_sources(question, urls):
    request = SourceRequest(question=question, urls=urls)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(SOURCE_TIMEOUT, connect=3.0),
        follow_redirects=False,
        headers={"User-Agent": "SourceLens/0.1"},
    ) as client:
        async def safe_fetch(url):
            started = time.perf_counter()

            async with semaphore:
                try:
                    final_url, html = await asyncio.wait_for(
                        fetch_with_retry(client, str(url)),
                        timeout=SOURCE_TIMEOUT,
                    )
                    soup = BeautifulSoup(html, "html.parser")
                    title = (
                        soup.title.get_text(" ", strip=True)
                        if soup.title
                        else ""
                    )
                    return SourceStatus(
                        url=str(url),
                        final_url=final_url,
                        ok=True,
                        title=title[:300],
                        text=extract_text(html),
                        elapsed_ms=round(
                            (time.perf_counter() - started) * 1000,
                            2,
                        ),
                    )
                except asyncio.TimeoutError:
                    return SourceStatus(
                        url=str(url),
                        ok=False,
                        error="timeout",
                        elapsed_ms=round(
                            (time.perf_counter() - started) * 1000,
                            2,
                        ),
                    )
                except SourceReadError as e:
                    return SourceStatus(
                        url=str(url),
                        ok=False,
                        error=e.code,
                        elapsed_ms=round(
                            (time.perf_counter() - started) * 1000,
                            2,
                        ),
                    )
                except Exception as e:
                    return SourceStatus(
                        url=str(url),
                        ok=False,
                        error=str(e) or type(e).__name__,
                        elapsed_ms=round(
                            (time.perf_counter() - started) * 1000,
                            2,
                        ),
                    )

        tasks = [safe_fetch(url) for url in request.urls]
        return await asyncio.gather(*tasks)




