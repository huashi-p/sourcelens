import asyncio
import json
import time
from dataclasses import asdict, dataclass


URL_LIMIT = 2
URL_TIMEOUT = 0.35
semaphore = asyncio.Semaphore(URL_LIMIT)


@dataclass
class SourceResult:
    url: str
    ok: bool
    title: str
    text: str
    error: str


async def mock_fetch(url, delay, should_fail=False):
    await asyncio.sleep(delay)

    if should_fail:
        raise RuntimeError(f"{url} 返回了无效页面")

    return SourceResult(
        url=url,
        ok=True,
        title=f"{url} 的页面标题",
        text=f"{url} 的相关正文",
        error="",
    )


async def limited_fetch(url, delay, should_fail=False):
    async with semaphore:
        try:
            return await asyncio.wait_for(
                mock_fetch(url, delay, should_fail),
                timeout=URL_TIMEOUT,
            )
        except Exception as e:
            return SourceResult(
                url=url,
                ok=False,
                title="",
                text="",
                error=str(e) or type(e).__name__,
            )


async def main():
    started = time.perf_counter()
    specs = [
        ("https://docs.example.com/a", 0.20, False),
        ("https://blog.example.com/b", 0.10, True),
        ("https://slow.example.com/c", 0.50, False),
        ("https://docs.example.com/d", 0.15, False),
    ]

    tasks = [
        limited_fetch(url, delay, should_fail)
        for url, delay, should_fail in specs
    ]
    results = await asyncio.gather(*tasks)
    elapsed = round((time.perf_counter() - started) * 1000, 2)

    success_results = [item for item in results if item.ok]
    failed_results = [item for item in results if not item.ok]

    report = {
        "question": "示例研究问题",
        "source_count": len(results),
        "success_count": len(success_results),
        "failure_count": len(failed_results),
        "elapsed_ms": elapsed,
        "sources": [asdict(item) for item in results],
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))


asyncio.run(main())