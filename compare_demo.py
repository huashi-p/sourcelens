import asyncio
import json

from compare import compare_sources
from fetcher import fetch_sources


async def main():
    question = "比较这些资料对异步请求的主要观点"
    urls = [
        "https://www.python-httpx.org/async/",
        "https://docs.python.org/3/library/asyncio-task.html",
    ]

    sources = await fetch_sources(question, urls)
    preview = [
        {
            "url": source.url,
            "final_url": source.final_url,
            "ok": source.ok,
            "title": source.title,
            "text_chars": len(source.text),
            "error": source.error,
            "elapsed_ms": source.elapsed_ms,
        }
        for source in sources
    ]

    print(json.dumps(preview, ensure_ascii=False, indent=2))

    try:
        report = await compare_sources(question, sources)
    except ValueError as e:
        print(json.dumps(
            {
                "ok": False,
                "error": str(e),
            },
            ensure_ascii=False,
            indent=2,
        ))
        return

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

