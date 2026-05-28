from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, Field


class DataScope(str, Enum):
    public = "public"
    private = "private"
    hybrid = "hybrid"


class HonestyMode(str, Enum):
    authentic = "authentic"        # raw signal read, no spin
    polished = "polished"          # strengths-forward, professional
    recruiter = "recruiter"        # optimised for technical hiring managers
    playful = "playful"            # informal, conversational, personality-driven
    technical = "technical"        # dense specifics for a peer engineer audience
    brutally_honest = "brutally_honest"  # weaknesses named, no flattery


class OutputTarget(str, Enum):
    readme = "readme"
    report = "report"
    signals = "signals"


class AuthRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class AuthLoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AnalysisRunRequest(BaseModel):
    username: str = Field(min_length=1, pattern=r"^[A-Za-z0-9-]{1,39}$")
    scope: DataScope = DataScope.public
    honesty_mode: HonestyMode = HonestyMode.authentic
    output_targets: list[OutputTarget] = Field(default_factory=lambda: [OutputTarget.readme, OutputTarget.report])
    include_private: bool = False


class AnalysisRunResponse(BaseModel):
    analysis_id: UUID
    status: str


class EvidenceRef(BaseModel):
    source_type: str
    source_id: str
    excerpt: str | None = None


class Signal(BaseModel):
    name: str
    value: float | str
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[EvidenceRef]
    timeframe: str


class ArchetypeResult(BaseModel):
    top_archetype: str
    alternates: list[str]
    confidence: float = Field(ge=0, le=1)
    supporting_evidence: list[EvidenceRef]


class ReadmeSection(BaseModel):
    title: str
    content: str
    evidence_refs: list[EvidenceRef]


class ReadmeResult(BaseModel):
    markdown: str
    sections: list[ReadmeSection]


class ReportResult(BaseModel):
    summary: str
    archetype: ArchetypeResult
    standout_repos: list[str]
    timeline: list[str]


class AnalysisStatus(BaseModel):
    analysis_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime


class ShareCreateRequest(BaseModel):
    ttl_minutes: int = Field(default=1440, ge=5, le=10080)


class ShareCreateResponse(BaseModel):
    token: str
    url: str
    expires_at: datetime


class SharedReportResponse(BaseModel):
    analysis_id: str
    report: ReportResult
    readme: ReadmeResult


class DimensionScore(BaseModel):
    dimension: str
    score: float = Field(ge=1, le=5)
    reasoning: str
    judge: str


class EvalResult(BaseModel):
    scores: list[DimensionScore]
    aggregate: float
    model_set: list[str]
    analysis_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AnalysisRecord(BaseModel):
    analysis_id: UUID = Field(default_factory=uuid4)
    username: str
    scope: DataScope
    honesty_mode: HonestyMode
    output_targets: list[OutputTarget]
    include_private: bool
    status: str = "queued"
    attempts: int = 0
    failure_reason: str = ""
    last_duration_ms: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    signals: list[Signal] = Field(default_factory=list)
    archetype: ArchetypeResult | None = None
    readme: ReadmeResult | None = None
    report: ReportResult | None = None
    eval: EvalResult | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class GitHubRepo(BaseModel):
    name: str
    stars: int
    forks: int
    language: str
    updated_at: datetime
    description: str | None = None
    topics: list[str] = Field(default_factory=list)
    is_fork: bool = False


class GitHubCommit(BaseModel):
    sha: str
    message: str
    committed_at: datetime
    additions: int
    deletions: int
    repo_name: str = ""
    # Area B enrichment — new fields have defaults so existing callers are unaffected
    author_login: str | None = None
    author_date: datetime | None = None
    committer_date: datetime | None = None
    file_names: list[str] = Field(default_factory=list)
