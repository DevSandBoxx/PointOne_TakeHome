from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TimeEntry(BaseModel):
    """Time entry submitted for client/matter suggestion."""

    user_id: str = Field(..., description="The timekeeper submitting the entry")
    entry_id: str = Field(..., description="Unique identifier for the entry")
    narrative: str = Field(..., description="Free-text description of the work performed")
    hours: float = Field(..., ge=0, description="Number of hours billed")
    client_name: Optional[str] = Field(None, description="Currently assigned client (may be wrong)")
    matter_name: Optional[str] = Field(None, description="Currently assigned matter (may be wrong)")
    entry_date: date = Field(..., description="Date the work was performed")


class Suggestion(BaseModel):
    """A single client/matter suggestion with score and optional rationale."""

    client_id: str = Field(..., description="Client ID (for feedback)")
    matter_id: str = Field(..., description="Matter ID (for feedback)")
    client_name: str = Field(..., description="The suggested client")
    matter_name: str = Field(..., description="The suggested matter")
    score: float = Field(..., ge=0, le=1, description="Confidence of the match (0–1)")
    rationale: Optional[str] = Field(None, description="Human-readable explanation for the match")
    rationale_source: Literal["template", "ollama"] = Field(
        "template",
        description="Where the rationale came from (template vs Ollama LLM).",
    )


class SuggestionsResponse(BaseModel):
    """Ranked list of client/matter suggestions for a time entry."""

    low_confidence: bool = Field(
        ...,
        description="True when no candidate is a strong match; UI should warn user.",
    )
    suggestions: list[Suggestion] = Field(
        ...,
        description="Ranked list of candidate client/matter assignments",
    )


class FeedbackRequest(BaseModel):
    """Accept or reject a suggestion for a time entry."""

    user_id: str = Field(..., description="The timekeeper submitting the feedback")
    entry_id: str = Field(..., description="Time entry identifier")
    client_id: str = Field(..., description="Client ID of the suggestion")
    matter_id: str = Field(..., description="Matter ID of the suggestion")
    action: Literal["accepted", "rejected"] = Field(
        ...,
        description="Whether the suggestion was accepted or rejected",
    )
