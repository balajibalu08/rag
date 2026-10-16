from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    query: str = Field(
        ...,
        description="Question to answer using the indexed documents.",
    )

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, query: str) -> str:
        query = query.strip()

        if not query:
            raise ValueError("The query cannot be blank.")

        return query
