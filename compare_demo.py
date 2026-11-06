import asyncio
import json

from pathlib import Path

from report import render_markdown
from compare import compare_sources
from fetcher import fetch_sources

from report import render_markdown, verify_report


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

    verification = verify_report(report, sources)

    if not verification["ok"]:
        raise RuntimeError(verification["issues"])

    markdown = render_markdown(report)
    
    output = Path(__file__).parent / "latest-report.md"
    output.write_text(markdown, encoding="utf-8")
    print(f"报告已写入：{output}")


if __name__ == "__main__":
    asyncio.run(main())

