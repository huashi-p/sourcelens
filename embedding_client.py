import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI


load_dotenv(Path(__file__).resolve().parent / ".env")

client = None
EMBEDDING_DIMENSION = int(
    os.getenv("EMBEDDING_DIMENSION", "1024")
)
EMBEDDING_BATCH_SIZE = int(
    os.getenv("EMBEDDING_BATCH_SIZE", "16")
)

def get_client():
    global client

    if client is not None:
        return client

    api_key = os.getenv("EMBEDDING_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 EMBEDDING_API_KEY")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=os.getenv(
            "EMBEDDING_BASE_URL",
            "https://api.siliconflow.cn/v1",
        ),
    )
    return client

async def embed_texts(texts):
    cleaned = [
        str(text).strip()
        for text in texts
        if str(text).strip()
    ]
    if not cleaned:
        return []

    vectors = []
    model = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

    for start in range(0, len(cleaned), EMBEDDING_BATCH_SIZE):
        batch = cleaned[start:start + EMBEDDING_BATCH_SIZE]
        response = await get_client().embeddings.create(
            model=model,
            input=batch,
        )
        ordered = sorted(
            response.data,
            key=lambda item: item.index,
        )
        vectors.extend(item.embedding for item in ordered)

    if len(vectors) != len(cleaned):
        raise ValueError("Embedding 返回数量与输入数量不一致")

    for vector in vectors:
        if len(vector) != EMBEDDING_DIMENSION:
            raise ValueError(
                f"Embedding 维度为 {len(vector)}，"
                f"配置要求 {EMBEDDING_DIMENSION}"
            )

    return vectors