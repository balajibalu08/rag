from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    query: str = Field(
        ..., description="Question to answer using the indexed documents."
    )

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, query: str) -> str:
        query = query.strip()
        if not query:
            raise ValueError("The query cannot be blank.")
        return query


class ChatResponse(BaseModel):
    query: str = Field(..., description="Question submitted by the user.")
    answer: str = Field(..., description="Answer generated from retrieved documents.")
    sources: list[str] = Field(
        default_factory=list,
        description="Sources that support the answer.",
    )
    confidence: int | None = Field(
        None,
        ge=0,
        le=100,
        description="Critic confidence score, when available.",
    )
    is_correct: bool | None = Field(
        None,
        description="Whether the critic considers the answer supported.",
    )
    reasoning: str | None = Field(
        None,
        description="Critic's reasoning, when available.",
    )
    feedback: str | None = Field(
        None,
        description="Critic feedback, when available.",
    )
