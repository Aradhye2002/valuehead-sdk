"""Response models for the ValueHead SDK."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SubmitResult(BaseModel):
    session_id: str
    status: str
    transcript_preview: str | None = None


class ToolCallJudgement(BaseModel):
    score: int = 0
    summary: str = ""
    reasoning: str = ""
    call_content: str = ""


class TurnJudgement(BaseModel):
    turn: int
    score: int = 0
    turn_reasoning: str = ""
    user_summary: str = ""
    user_content: str = ""
    assistant_summary: str = ""
    assistant_content: str = ""
    tool_calls: list[ToolCallJudgement] = Field(default_factory=list)


class TrajectoryFailure(BaseModel):
    type: str = ""
    description: str = ""
    after_turn: int = 0


class TrajectoryJudgement(BaseModel):
    score: int = 0
    reasoning: str = ""
    completed: bool = False
    early_termination: bool = False
    failures: list[TrajectoryFailure] = Field(default_factory=list)


class ScoreSummary(BaseModel):
    total_turns: int = 0
    judged_turns: int = 0
    helpful: int = 0
    neutral: int = 0
    harmful: int = 0
    net_score: int = 0
    trajectory_score: int | None = None


class SessionDetail(BaseModel):
    id: str
    status: str
    created_at: str
    total_turns: int
    judgements: dict[str, TurnJudgement] = {}
    trajectory: TrajectoryJudgement | None = None
    summary: ScoreSummary = ScoreSummary()
    error: str | None = None
    metadata: dict[str, Any] = {}


class SessionListItem(BaseModel):
    id: str
    status: str
    created_at: str
    total_turns: int
    summary: ScoreSummary = ScoreSummary()
    metadata: dict[str, Any] = {}


class SessionsListResponse(BaseModel):
    sessions: list[SessionListItem] = []
    total: int = 0
    count: int = 0
