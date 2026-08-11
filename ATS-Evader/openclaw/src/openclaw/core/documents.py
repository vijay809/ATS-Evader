"""Domain models for user-supplied and AI-generated documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass(slots=True)
class Resume:
    content: str
    name: str = "Imported Resume"
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class StructuredResume:
    raw_content: str
    parsed_json: str
    name: str = "Master Resume"
    is_active: bool = False
    created_at: float = field(default_factory=lambda: __import__('time').time())
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class Preference:
    key: str
    value: str
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class JobDescription:
    content: str
    name: str = "Imported JD"
    status: str = "Discovered"
    url: str | None = None
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class AnalysisResult:
    resume_id: UUID
    job_id: UUID
    match_score: int
    matched_keywords: str
    missing_keywords: str
    recommendations: str
    summary: str
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class TailoredDraft:
    resume_id: UUID
    job_id: UUID
    content: str
    change_summary: str
    warnings: str
    id: UUID = field(default_factory=uuid4)
