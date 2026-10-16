from pydantic import BaseModel, Field


class CriticResponse(BaseModel):
    confidence: int = Field(
        ..., description="how confident is the critic that the answer is reliable?"
    )
    is_correct: bool = Field(
        ..., description="is the answer supported by the retrieved information?"
    )
    reasoning: str = Field(..., description="Why did critic agent gave that confidence")
    feedback: str = Field(..., description="Feedback on rag agent response")
