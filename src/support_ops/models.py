
from datetime import datetime
from math import isfinite
from typing import Literal

from enum import Enum
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .vocab import (
    Intent,
    Urgency,
    Sentiment,
    InternalQueue,
    ReplySafetyLabel,
    PipelineState,
)


# ============================================================
# Base models
# ============================================================

class InputModel(BaseModel):
    """Model for validating external input files."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )


class StageModel(BaseModel):
    """Base model for intermediate pipeline-stage artifacts."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )


class OutputModel(BaseModel):
    """Base model for final pipeline outputs."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )


# ============================================================
# Stage 1: Input models
# ============================================================

class Ticket(InputModel):
    """A support ticket loaded from tickets.json."""

    ticket_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    customer_tier: str = Field(min_length=1)
    language_hint: str = Field(min_length=1)
    subject: str = ""
    message: str = ""
    created_at: datetime


class KBArticle(InputModel):
    """A knowledge-base article loaded from kb_articles.json."""

    article_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    body: str = ""
    tags: list[str] = Field(default_factory=list)


# ============================================================
# Pipeline metadata and stage state
# ============================================================

class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageState(StageModel):
    """Records the execution state of one pipeline stage."""

    stage_name: str = Field(min_length=1)
    state: PipelineState
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    input_artifacts: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_timestamps(self):
        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError(
                "completed_at cannot be earlier than started_at"
            )

        if self.status == StageStatus.FAILED and not self.error_message:
            raise ValueError("Failed stages must include error_message")

        return self


class RunManifest(OutputModel):
    """Metadata required to identify and replay a pipeline run."""

    run_id: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    started_at: datetime
    finished_at: datetime | None = None
    provider: str
    model: str
    input_hashes: dict[str, str]
    stage_states: list[StageState] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_run_timestamps(self):
        if (
            self.finished_at is not None
            and self.finished_at < self.started_at
        ):
            raise ValueError(
                "finished_at cannot be earlier than started_at"
            )
        return self


# ============================================================
# Stage 2: Preprocessing
# ============================================================

class PreprocessedTicket(StageModel):
    """Original and normalized ticket text."""

    ticket_id: str
    original_subject: str
    original_message: str
    subject_for_processing: str
    message_for_processing: str
    original_language: str
    translated: bool


# ============================================================
# Stage 3: Classification
# ============================================================

class Classification(StageModel):
    """Structured intent, urgency, and risk assessment."""

    ticket_id: str
    intent: Intent
    urgency: Urgency
    sentiment: Sentiment
    mentions_funds_blocked: bool = False
    mentions_regulator_or_legal_threat: bool = False
    requires_specialist_handling: bool = False
    original_language: str
    translated: bool


# ============================================================
# Stage 4: Knowledge-base retrieval
# ============================================================

class RetrievedArticle(StageModel):
    """One article selected by the retrieval stage."""

    article_id: str
    title: str
    score: float = Field(ge=0.0, le=1.0)

    @field_validator("score")
    @classmethod
    def score_must_be_finite(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("Retrieval score must be finite")
        return value


class TicketRetrieval(StageModel):
    """Top-two KB retrieval results for one ticket."""

    ticket_id: str
    retrieved_articles: list[RetrievedArticle] = Field(
        min_length=2,
        max_length=2,
    )

    @model_validator(mode="after")
    def article_ids_must_be_unique(self):
        article_ids = [
            article.article_id
            for article in self.retrieved_articles
        ]
        if len(article_ids) != len(set(article_ids)):
            raise ValueError("Retrieved article IDs must be unique")
        return self


# ============================================================
# Stage 5: Priority scoring
# ============================================================

class PriorityResult(StageModel):
    """Explainable priority score and batch ranking."""

    ticket_id: str

    base_priority: int = Field(ge=0)
    customer_tier_bonus: int = Field(ge=0)
    funds_blocked_bonus: int = Field(ge=0)
    regulatory_legal_threat_bonus: int = Field(ge=0)
    specialist_handling_bonus: int = Field(ge=0)
    retrieval_weakness_bonus: int = Field(ge=0)

    priority_score: int = Field(ge=0)
    expedited: bool
    rank: int = Field(ge=1)

    @model_validator(mode="after")
    def score_must_equal_components(self):
        expected = (
            self.base_priority
            + self.customer_tier_bonus
            + self.funds_blocked_bonus
            + self.regulatory_legal_threat_bonus
            + self.specialist_handling_bonus
            + self.retrieval_weakness_bonus
        )

        if self.priority_score != expected:
            raise ValueError(
                f"priority_score must equal component sum ({expected})"
            )

        return self


# ============================================================
# Stage 6: Routing
# ============================================================

class RoutingDecision(StageModel):
    """Internal support queue assignments and review requirements."""

    ticket_id: str
    queues: list[InternalQueue] = Field(min_length=1)
    routing_rationale: str = Field(min_length=1)
    reply_safety_label: ReplySafetyLabel

    @model_validator(mode="after")
    def queues_must_be_unique(self):
        if len(self.queues) != len(set(self.queues)):
            raise ValueError("Duplicate queues are not allowed")
        return self


# ============================================================
# Stage 7: Reply drafting
# ============================================================

class ReplyDraft(OutputModel):
    """Human-reviewable response draft; never auto-sent."""

    ticket_id: str
    channel: str
    draft_reply: str = Field(min_length=1)
    citations: list[str] = Field(min_length=1)
    review_gate_note: str = Field(min_length=1)

    @field_validator("citations")
    @classmethod
    def citations_must_be_unique(
        cls, value: list[str]
    ) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Duplicate citations are not allowed")
        return value


# ============================================================
# Additional operational outputs
# ============================================================

class RetrievalQualityNote(OutputModel):
    ticket_id: str
    issue: str
    recommended_improvement: str


class HandoffMemory(OutputModel):
    """Compact context for the next human support agent."""

    ticket_id: str
    customer_problem_summary: str
    open_questions: list[str] = Field(default_factory=list)
    do_not_say: list[str] = Field(default_factory=list)
    recommended_next_action: str


class ValidationCheck(StageModel):
    name: str
    passed: bool
    details: str = ""


class ValidationReport(OutputModel):
    run_id: str
    checks: list[ValidationCheck]
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)

    @model_validator(mode="after")
    def counts_must_match_checks(self):
        actual_passed = sum(check.passed for check in self.checks)
        actual_failed = len(self.checks) - actual_passed

        if self.passed_count != actual_passed:
            raise ValueError("passed_count does not match checks")
        if self.failed_count != actual_failed:
            raise ValueError("failed_count does not match checks")

        return self
