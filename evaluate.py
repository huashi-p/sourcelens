import asyncio
import json
import math
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from rag_models import (
    SourceChunk,
    SourceDocument,
    engine,
)

from fetcher import fetch_sources
from rag_answer import answer_with_citations
from rag_index import index_sources
from vector_search import vector_search

TOP_K = 5


def load_dataset(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def normalized(text):
    return " ".join((text or "").split()).casefold()

def resolve_gold_chunk_ids(cases):
    gold = {}

    with Session(engine) as db:
        rows = db.execute(
            select(SourceChunk, SourceDocument).join(
                SourceDocument,
                SourceChunk.document_id == SourceDocument.id,
            )
        ).all()

        for case in cases:
            quote = normalized(case.get("relevant_quote"))
            if not quote:
                gold[case["id"]] = set()
                continue

            matched = {
                chunk.id
                for chunk, document in rows
                if document.url == case["expected_source"]
                and quote in normalized(chunk.content)
            }

            gold[case["id"]] = matched
            if not matched:
                raise ValueError(
                    f"{case['id']} 的标准引文没有落在任何 chunk 中"
                )

    return gold

from relevance import query_terms


def keyword_search(question, rows, top_k=5):
    terms = query_terms(question)
    scored = []

    for chunk, document in rows:
        text = normalized(chunk.content)
        score = sum(text.count(term) for term in terms)
        scored.append((score, chunk, document))

    scored.sort(
        key=lambda item: (item[0], -item[1].id),
        reverse=True,
    )
    return scored[:top_k]


def recall_at_k(result_ids, gold_ids, k=TOP_K):
    if not gold_ids:
        return None

    return (
        len(set(result_ids[:k]) & gold_ids)
        / len(gold_ids)
    )


def reciprocal_rank(result_ids, gold_ids):
    for rank, chunk_id in enumerate(result_ids, start=1):
        if chunk_id in gold_ids:
            return 1 / rank

    return 0.0


def average(values):
    values = [
        value
        for value in values
        if value is not None
    ]
    return sum(values) / len(values) if values else 0.0


def p95(values):
    values = sorted(values)
    if not values:
        return 0.0

    index = max(
        0,
        math.ceil(0.95 * len(values)) - 1,
    )
    return values[index]

def summarize_results(
    case_results,
    answer_rows,
    unanswerable_rows,
):
    generated_answers = [
        row
        for row in answer_rows
        if row.get("success")
    ]
    total_citations = sum(
        row["citation_count"]
        for row in generated_answers
    )
    verified_citations = sum(
        row["verified_count"]
        for row in generated_answers
    )
    covered_answers = sum(
        1
        for row in generated_answers
        if row["verified_count"] > 0
    )
    refused_count = sum(
        1
        for row in unanswerable_rows
        if row.get("success")
        and row["answer"]["answerable"] is False
    )

    return {
        "answerable_count": len(case_results),
        "generated_answer_count": len(generated_answers),
        "keyword": {
            "recall_at_5": average([
                row["keyword_recall_at_5"]
                for row in case_results
            ]),
            "mrr": average([
                row["keyword_rr"]
                for row in case_results
            ]),
            "p95_latency_ms": p95([
                row["keyword_latency_ms"]
                for row in case_results
            ]),
        },
        "vector": {
            "recall_at_5": average([
                row["vector_recall_at_5"]
                for row in case_results
            ]),
            "mrr": average([
                row["vector_rr"]
                for row in case_results
            ]),
            "p95_latency_ms": p95([
                row["vector_latency_ms"]
                for row in case_results
            ]),
            "citation_coverage": (
                covered_answers / len(generated_answers)
                if generated_answers else 0.0
            ),
            "citation_correctness": (
                verified_citations / total_citations
                if total_citations else 0.0
            ),
            "refusal_rate": (
                refused_count / len(unanswerable_rows)
                if unanswerable_rows else 0.0
            ),
        },
    }

async def run_evaluation(dataset, top_k=TOP_K):
    all_cases = []

    for group in dataset["groups"]:
        for case in group["questions"]:
            item = dict(case)
            item["group_id"] = group["id"]
            item["domain"] = group["domain"]
            all_cases.append(item)

    indexed_groups = {}

    for group in dataset["groups"]:
        sources = await fetch_sources(
            "评测资料抓取",
            group["urls"],
        )
        successful = [
            source
            for source in sources
            if source.ok
        ]

        if len(successful) < 2:
            raise RuntimeError(
                f"{group['id']} 成功来源少于两个"
            )

        index_result = await index_sources(successful)
        indexed_groups[group["id"]] = {
            "document_ids": index_result["document_ids"],
            "source_urls": {
                source.url: source.final_url or source.url
                for source in successful
            },
        }

        print(
            f"已索引 {group['id']}："
            f"{index_result['chunks']} 个 chunks"
        )

    gold_ids = resolve_gold_chunk_ids(all_cases)

    group_rows = {}

    with Session(engine) as db:
        for group in dataset["groups"]:
            document_ids = indexed_groups[
                group["id"]
            ]["document_ids"]

            group_rows[group["id"]] = db.execute(
                select(SourceChunk, SourceDocument)
                .join(
                    SourceDocument,
                    SourceChunk.document_id
                    == SourceDocument.id,
                )
                .where(
                    SourceChunk.document_id.in_(document_ids)
                )
            ).all()

    keyword_recalls = []
    keyword_rrs = []
    keyword_latencies = []
    vector_recalls = []
    vector_rrs = []
    vector_latencies = []
    case_results = []
    answer_rows = []
    unanswerable_rows = []

    for group in dataset["groups"]:
        group_id = group["id"]
        rows = group_rows[group_id]

        answerable_cases = [
            case
            for case in all_cases
            if case["group_id"] == group_id
            and case["answerable"]
        ]

        for case in answerable_cases:
            keyword_query = (
                case.get("keyword_query")
                or case["question"]
            )

            started = time.perf_counter()
            keyword_rows = keyword_search(
                keyword_query,
                rows,
                top_k=top_k,
            )
            keyword_latency = (
                time.perf_counter() - started
            ) * 1000

            keyword_ids = [
                row[1].id
                for row in keyword_rows
            ]

            started = time.perf_counter()
            vector_rows = await vector_search(
                case["question"],
                top_k=top_k,
                document_ids=indexed_groups[
                    group_id
                ]["document_ids"],
            )
            vector_latency = (
                time.perf_counter() - started
            ) * 1000

            vector_ids = [
                row["chunk_id"]
                for row in vector_rows
            ]

            gold = gold_ids[case["id"]]
            keyword_recall = recall_at_k(
                keyword_ids,
                gold,
                top_k,
            )
            vector_recall = recall_at_k(
                vector_ids,
                gold,
                top_k,
            )
            keyword_rr = reciprocal_rank(
                keyword_ids,
                gold,
            )
            vector_rr = reciprocal_rank(
                vector_ids,
                gold,
            )

            keyword_recalls.append(keyword_recall)
            vector_recalls.append(vector_recall)
            keyword_rrs.append(keyword_rr)
            vector_rrs.append(vector_rr)
            keyword_latencies.append(keyword_latency)
            vector_latencies.append(vector_latency)

            case_results.append(
                {
                    "id": case["id"],
                    "domain": case["domain"],
                    "group_id": group_id,
                    "question": case["question"],
                    "keyword_query": keyword_query,
                    "gold_chunk_ids": sorted(gold),
                    "keyword_top_ids": keyword_ids,
                    "vector_top_ids": vector_ids,
                    "keyword_recall_at_5": keyword_recall,
                    "vector_recall_at_5": vector_recall,
                    "keyword_rr": keyword_rr,
                    "vector_rr": vector_rr,
                    "keyword_latency_ms": round(
                        keyword_latency,
                        3,
                    ),
                    "vector_latency_ms": round(
                        vector_latency,
                        3,
                    ),
                }
            )
            try:
                answer = await answer_with_citations(
                    case["question"],
                    vector_rows,
                )
                citations = answer.get(
                    "citations",
                    [],
                )
                answer_rows.append(
                    {
                        "id": case["id"],
                        "domain": case["domain"],
                        "group_id": group_id,
                        "success": True,
                        "answer": answer,
                        "citation_count": len(citations),
                        "verified_count": answer.get(
                            "verified_citations",
                            0,
                        ),
                    }
                )
            except Exception as error:
                answer_rows.append(
                    {
                        "id": case["id"],
                        "domain": case["domain"],
                        "group_id": group_id,
                        "success": False,
                        "answer": None,
                        "citation_count": 0,
                        "verified_count": 0,
                        "error": (
                            f"{type(error).__name__}: "
                            f"{error}"
                        ),
                    }
                )

    unanswerable_cases = [
        case
        for case in all_cases
        if not case["answerable"]
    ]

    for case in unanswerable_cases:
        group_id = case["group_id"]

        chunks = await vector_search(
            case["question"],
            top_k=top_k,
            document_ids=indexed_groups[
                group_id
            ]["document_ids"],
        )

        try:
            answer = await answer_with_citations(
                case["question"],
                chunks,
            )
            unanswerable_rows.append(
                {
                    "id": case["id"],
                    "domain": case["domain"],
                    "group_id": group_id,
                    "success": True,
                    "answer": answer,
                }
            )
        except Exception as error:
            unanswerable_rows.append(
                {
                    "id": case["id"],
                    "domain": case["domain"],
                    "group_id": group_id,
                    "success": False,
                    "answer": None,
                    "error": (
                        f"{type(error).__name__}: "
                        f"{error}"
                    ),
                }
            )

    domains = sorted({
        case["domain"]
        for case in all_cases
    })
    domain_results = {}

    for domain in domains:
        domain_case_results = [
            row
            for row in case_results
            if row["domain"] == domain
        ]
        domain_answer_rows = [
            row
            for row in answer_rows
            if row["domain"] == domain
        ]
        domain_unanswerable_rows = [
            row
            for row in unanswerable_rows
            if row["domain"] == domain
        ]

        domain_results[domain] = summarize_results(
            domain_case_results,
            domain_answer_rows,
            domain_unanswerable_rows,
        )

    overall = summarize_results(
        case_results,
        answer_rows,
        unanswerable_rows,
    )

    return {
        "dataset_version": dataset["version"],
        "captured_at": dataset.get("captured_at"),
        "embedding_model": dataset.get(
            "embedding_model"
        ),
        "top_k": top_k,
        "chunk_size": dataset.get("chunk_size"),
        "chunk_overlap": dataset.get(
            "chunk_overlap"
        ),
        "overall": overall,
        "domains": domain_results,
        "cases": case_results,
        "answers": answer_rows,
        "unanswerable_results": unanswerable_rows,
    }


async def main():
    project_root = Path(__file__).resolve().parent
    dataset_path = (
        project_root
        / "evaluation"
        / "dataset.json"
    )

    dataset = load_dataset(dataset_path)
    top_k = int(dataset.get("top_k", TOP_K))
    result = await run_evaluation(
        dataset,
        top_k=top_k,
    )

    output_path = (
        project_root
        / "evaluation"
        / "results-v2.json"
    )
    output_path.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("评测完成")
    print(f"结果已保存：{output_path}")
    print(
        json.dumps(
            result["overall"],
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())