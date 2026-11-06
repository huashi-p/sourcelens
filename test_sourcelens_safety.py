import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

import compare
import fetcher
from schemas import SourceStatus
from url_guard import SourceReadError, validate_public_url


def run(coro):
    return asyncio.run(coro)


def test_private_and_file_urls_are_blocked():
    for url in [
        "http://127.0.0.1/",
        "http://169.254.169.254/",
        "file:///etc/passwd",
    ]:
        with pytest.raises(SourceReadError):
            run(validate_public_url(url))


def test_extract_text_removes_page_chrome():
    html = """
    <html>
      <head><title>Test</title><style>hidden</style></head>
      <body>
        <nav>navigation</nav>
        <main><h1>Title</h1><p>Useful content.</p></main>
        <script>ignored()</script>
        <footer>footer</footer>
      </body>
    </html>
    """
    text = fetcher.extract_text(html)

    assert "Useful content." in text
    assert "navigation" not in text
    assert "ignored()" not in text
    assert "footer" not in text


def test_fetch_sources_uses_guard_and_keeps_partial_success(monkeypatch):
    calls = []
    urls = [
        "https://public.example.com/ok",
        "https://public.example.com/fail",
    ]

    async def fake_validate(url):
        calls.append(str(url))
        return str(url)

    def handler(request):
        if request.url.path.endswith("/fail"):
            return httpx.Response(
                500,
                request=request,
                headers={"content-type": "text/html"},
                text="failed",
            )

        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><head><title>Example</title></head>"
                "<body><main>Useful content.</main></body></html>"
            ),
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        return real_client(transport=transport, follow_redirects=False)

    monkeypatch.setattr(fetcher, "validate_public_url", fake_validate)
    monkeypatch.setattr(fetcher.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(fetcher, "MAX_RETRIES", 0)

    results = run(fetcher.fetch_sources(
        "比较两个测试来源",
        urls,
    ))

    assert calls == urls
    assert [source.ok for source in results] == [True, False]
    assert results[0].final_url == urls[0]
    assert results[0].title == "Example"
    assert "Useful content." in results[0].text
    assert results[1].error == "http_5xx"


def test_compare_rejects_one_source_common_claim(monkeypatch):
    sources = [
        SourceStatus(
            url="https://a.example.com",
            final_url="https://a.example.com",
            ok=True,
            title="A",
            text="A content",
        ),
        SourceStatus(
            url="https://b.example.com",
            final_url="https://b.example.com",
            ok=True,
            title="B",
            text="B content",
        ),
    ]

    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        content = json.dumps({
            "common_points": [
                {
                    "text": "shared",
                    "evidence_quote": "shared quote",
                    "source_ids": ["SOURCE_1"],
                }
            ],
            "conflicts": [],
            "unanswered": [],
            "limitations": [],
        })
        message = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=fake_create)
        )
    )
    monkeypatch.setattr(compare, "client", fake_client)

    with pytest.raises(ValueError):
        run(compare.compare_sources("比较来源", sources))

    assert call_count == 2


def test_compare_attaches_verified_source_urls(monkeypatch):
    sources = [
        SourceStatus(
            url="https://a.example.com",
            final_url="https://a.example.com/final",
            ok=True,
            title="A",
            text="A content",
        ),
        SourceStatus(
            url="https://b.example.com",
            final_url="https://b.example.com/final",
            ok=True,
            title="B",
            text="B content",
        ),
        SourceStatus(
            url="https://failed.example.com",
            ok=False,
            error="timeout",
        ),
    ]

    async def fake_create(**kwargs):
        content = json.dumps({
            "common_points": [
                {
                    "text": "shared",
                    "evidence_quote": "shared quote",
                    "source_ids": ["SOURCE_1", "SOURCE_2"],
                }
            ],
            "conflicts": [],
            "unanswered": [],
            "limitations": [],
        })
        message = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=fake_create)
        )
    )
    monkeypatch.setattr(compare, "client", fake_client)

    report = run(compare.compare_sources("比较来源", sources))

    assert report["common_points"][0]["source_urls"] == [
        "https://a.example.com/final",
        "https://b.example.com/final",
    ]
    assert report["failed_sources"] == [
        {
            "url": "https://failed.example.com",
            "error": "timeout",
        }
    ]

def test_compare_accepts_verified_common_and_conflict(
    monkeypatch,
):
    sources = [
        SourceStatus(
            url="https://a.example.com",
            final_url="https://a.example.com/final",
            ok=True,
            title="A",
            text="FastAPI 可以使用 Semaphore 限制并发。",
        ),
        SourceStatus(
            url="https://b.example.com",
            final_url="https://b.example.com/final",
            ok=True,
            title="B",
            text="Semaphore 用于控制异步任务并发。",
        ),
        SourceStatus(
            url="https://failed.example.com",
            ok=False,
            error="timeout",
        ),
    ]

    async def fake_create(**kwargs):
        content = json.dumps({
            "common_points": [
                {
                    "text": "Semaphore 可以限制并发",
                    "evidence_quote": "Semaphore 可以限制并发",
                    "source_ids": ["SOURCE_1", "SOURCE_2"],
                }
            ],
            "conflicts": [
                {
                    "text": "两个来源对适用场景的描述不同",
                    "evidence_quote": "适用场景不同",
                    "source_ids": ["SOURCE_1", "SOURCE_2"],
                }
            ],
            "unanswered": [],
            "limitations": [],
        })
        message = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=fake_create)
        )
    )
    monkeypatch.setattr(compare, "client", fake_client)

    report = run(compare.compare_sources(
        "如何限制并发",
        sources,
    ))

    assert report["common_points"][0]["source_urls"] == [
        "https://a.example.com/final",
        "https://b.example.com/final",
    ]
    assert report["conflicts"][0]["source_urls"] == [
        "https://a.example.com/final",
        "https://b.example.com/final",
    ]
    assert report["failed_sources"] == [
        {
            "url": "https://failed.example.com",
            "error": "timeout",
        }
    ]


def test_compare_rejects_unknown_source_id(monkeypatch):
    sources = [
        SourceStatus(
            url="https://a.example.com",
            ok=True,
            title="A",
            text="A content",
        ),
        SourceStatus(
            url="https://b.example.com",
            ok=True,
            title="B",
            text="B content",
        ),
    ]

    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        content = json.dumps({
            "common_points": [
                {
                    "text": "伪造的观点",
                    "evidence_quote": "伪造的证据",
                    "source_ids": ["SOURCE_9"],
                }
            ],
            "conflicts": [],
            "unanswered": [],
            "limitations": [],
        })
        message = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=fake_create)
        )
    )
    monkeypatch.setattr(compare, "client", fake_client)

    with pytest.raises(ValueError):
        run(compare.compare_sources("比较来源", sources))

    assert call_count == 2