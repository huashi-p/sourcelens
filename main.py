import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from rag_models import init_rag_db

from rag_answer import answer_with_citations
from rag_index import index_sources
from vector_search import vector_search
from schemas import (
    RagRequest,
    ReadRequest,
    SourceRequest,
)

@asynccontextmanager
async def lifespan(app):
    init_rag_db()
    yield
from compare import compare_sources
from fetcher import fetch_sources
from report import render_markdown, verify_report


app = FastAPI(
    title="SourceLens",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory="static"), name="static")

COMPARE_TIMEOUT = 90.0


async def answer_from_urls(
    question,
    urls,
    top_k,
    minimum_successful,
):
    sources = await fetch_sources(question, urls)
    successful = [source for source in sources if source.ok]

    if len(successful) < minimum_successful:
        raise HTTPException(
            status_code=422,
            detail={
                "error": (
                    f"成功来源少于 {minimum_successful} 个"
                ),
                "sources": [
                    source.model_dump(mode="json")
                    for source in sources
                ],
            },
        )

    index_result = await index_sources(successful)
    chunks = await vector_search(
        question,
        top_k=top_k,
        document_ids=index_result["document_ids"],
    )
    answer = await answer_with_citations(question, chunks)

    return {
        "ok": True,
        "question": question,
        "index": index_result,
        "retrieved_chunks": chunks,
        "answer": answer,
        "failed_sources": [
            {
                "url": source.url,
                "error": source.error,
            }
            for source in sources
            if not source.ok
        ],
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "sourcelens",
    }

@app.post("/api/compare")
async def compare_endpoint(request: SourceRequest):
    sources = await fetch_sources(
        request.question,
        request.urls,
    )
    successful = [source for source in sources if source.ok]

    if len(successful) < 2:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "成功来源少于两个",
                "sources": [
                    source.model_dump(mode="json")
                    for source in sources
                ],
            },
        )

    try:
        report = await asyncio.wait_for(
            compare_sources(request.question, sources),
            timeout=COMPARE_TIMEOUT,
        )
    except asyncio.TimeoutError as e:
        raise HTTPException(
            status_code=504,
            detail="模型比较超时",
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=502,
            detail=str(e),
        ) from e
    verification = verify_report(report, sources)

    if not verification["ok"]:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "报告未通过来源校验",
                "issues": verification["issues"],
            },
        )

    return {
        "ok": True,
        "question": request.question,
        "sources": [
            source.model_dump(mode="json")
            for source in sources
        ],
        "report": report,
        "markdown": render_markdown(report),
    }

@app.post("/api/rag")
async def rag_endpoint(request: RagRequest):
    return await answer_from_urls(
        request.question,
        request.urls,
        request.top_k,
        minimum_successful=2,
    )


@app.post("/api/read")
async def read_endpoint(request: ReadRequest):
    return await answer_from_urls(
        request.question,
        [request.url],
        request.top_k,
        minimum_successful=1,
    )
