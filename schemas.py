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
