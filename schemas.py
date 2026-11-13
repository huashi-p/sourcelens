from pydantic import BaseModel, Field, HttpUrl


class SourceRequest(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    urls: list[HttpUrl] = Field(min_length=2, max_length=5)


class SourceStatus(BaseModel):
    url: str
    final_url: str | None = None
    ok: bool
    status_code: int = 0
    title: str = ""
    text: str = ""
    elapsed_ms: float = 0
    error: str = ""

class RagRequest(SourceRequest):
    top_k: int = Field(default=5, ge=1, le=10)

class ReadRequest(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    url: HttpUrl
    top_k: int = Field(default=5, ge=1, le=10)