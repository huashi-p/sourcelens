from sqlalchemy import select
from sqlalchemy.orm import Session

from embedding_client import embed_texts
from rag_models import (
    SourceChunk,
    SourceDocument,
    engine,
)


async def vector_search(
    question,
    top_k=5,
    document_ids=None,
):
    top_k = max(1, min(int(top_k), 10))

    if document_ids is not None:
        document_ids = [
            int(document_id)
            for document_id in document_ids
        ]
        if not document_ids:
            return []

    query_vectors = await embed_texts([question])
    query_vector = query_vectors[0]

    distance = SourceChunk.embedding.cosine_distance(
        query_vector
    )
    with Session(engine) as db:
        statement = (
            select(
                SourceChunk,
                SourceDocument,
                distance.label("distance"),
            )
            .join(
                SourceDocument,
                SourceChunk.document_id == SourceDocument.id,
            )
            .where(SourceChunk.embedding.is_not(None))
        )

        if document_ids is not None:
            statement = statement.where(
                SourceChunk.document_id.in_(document_ids)
            )

        rows = db.execute(
            statement
            .order_by(distance)
            .limit(top_k)
        ).all()

    return [
        {
            "chunk_id": chunk.id,
            "document_id": document.id,
            "url": document.url,
            "title": document.title,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "distance": round(float(score), 6),
            "similarity": round(1.0 - float(score), 6),
        }
        for chunk, document, score in rows
    ]
