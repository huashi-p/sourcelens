import hashlib

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from chunking import split_text
from embedding_client import embed_texts
from rag_models import (
    SourceChunk,
    SourceDocument,
    engine,
)


def content_hash(text):
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()

async def index_sources(sources):
    prepared = []

    for source in sources:
        if not source.ok or not source.text.strip():
            continue

        chunks = split_text(
            source.text,
            max_chars=800,
            overlap=120,
        )
        if not chunks:
            continue

        vectors = await embed_texts(chunks)
        prepared.append(
            {
                "url": source.final_url or source.url,
                "title": source.title,
                "text": source.text,
                "chunks": chunks,
                "vectors": vectors,
            }
        )

    inserted_documents = 0
    inserted_chunks = 0
    document_ids = []

    with Session(engine) as db:
        for item in prepared:
            document = db.scalar(
                select(SourceDocument).where(
                    SourceDocument.url == item["url"]
                )
            )

            if document is None:
                document = SourceDocument(
                    url=item["url"],
                    title=item["title"],
                    content_hash=content_hash(item["text"]),
                )
                db.add(document)
                db.flush()
                inserted_documents += 1
            else:
                document.title = item["title"]
                document.content_hash = content_hash(item["text"])
                db.execute(
                    delete(SourceChunk).where(
                        SourceChunk.document_id == document.id
                    )
                )
            if document.id not in document_ids:
                document_ids.append(document.id)

            for index, (chunk, vector) in enumerate(
                    zip(item["chunks"], item["vectors"])
            ):
                db.add(
                    SourceChunk(
                        document_id=document.id,
                        chunk_index=index,
                        content=chunk,
                        embedding=vector,
                    )
                )
                inserted_chunks += 1

        db.commit()

    return {
        "documents": len(prepared),
        "new_documents": inserted_documents,
        "chunks": inserted_chunks,
        "document_ids": document_ids,
    }