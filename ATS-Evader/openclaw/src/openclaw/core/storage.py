"""SQLite persistence owned by the runtime.

Plugins receive higher-level services instead of direct database access. This keeps schema
ownership, migrations, and data retention decisions at the runtime boundary.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from sqlmodel import Field, Session, SQLModel, create_engine, select

if TYPE_CHECKING:
    from openclaw.core.documents import AnalysisResult, JobDescription, Resume, TailoredDraft
    from openclaw.core.tasks import Task


class TaskRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    status: str
    detail: str | None = None


class ResumeRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    content: str


class JobDescriptionRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    content: str


class AnalysisResultRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    resume_id: str
    job_id: str
    match_score: int
    matched_keywords: str
    missing_keywords: str
    recommendations: str
    summary: str


class TailoredDraftRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    resume_id: str
    job_id: str
    content: str
    change_summary: str
    warnings: str


class TaskRepository(Protocol):
    def save(self, task: Task) -> None: ...

    def list(self) -> Iterable[Task]: ...


class DocumentRepository(Protocol):
    def save_resume(self, resume: Resume) -> None: ...
    def save_job_description(self, jd: JobDescription) -> None: ...
    def save_analysis(self, analysis: AnalysisResult) -> None: ...
    def save_draft(self, draft: TailoredDraft) -> None: ...
    
    def get_resume(self, resume_id: str) -> Resume | None: ...
    def get_job_description(self, jd_id: str) -> JobDescription | None: ...
    def list_resumes(self) -> Iterable[Resume]: ...
    def list_job_descriptions(self) -> Iterable[JobDescription]: ...


class SQLiteTaskRepository:
    """Small repository adapter that makes task persistence replaceable and testable."""

    def __init__(self, database_path: Path) -> None:
        self._engine = create_engine(f"sqlite:///{database_path}")

    def initialize(self) -> None:
        SQLModel.metadata.create_all(self._engine)

    def save(self, task: Task) -> None:
        record = TaskRecord(
            id=str(task.id),
            name=task.name,
            status=task.status.value,
            detail=task.detail,
        )
        with Session(self._engine) as session:
            session.merge(record)
            session.commit()

    def list(self) -> Iterable[Task]:
        from uuid import UUID

        from openclaw.core.tasks import Task, TaskStatus

        with Session(self._engine) as session:
            records = session.exec(select(TaskRecord).order_by(TaskRecord.name)).all()
        return tuple(
            Task(
                id=UUID(record.id),
                name=record.name,
                status=TaskStatus(record.status),
                detail=record.detail,
            )
            for record in records
        )


class SQLiteDocumentRepository:
    def __init__(self, database_path: Path) -> None:
        self._engine = create_engine(f"sqlite:///{database_path}")

    def save_resume(self, resume: Resume) -> None:
        record = ResumeRecord(id=str(resume.id), name=resume.name, content=resume.content)
        with Session(self._engine) as session:
            session.merge(record)
            session.commit()

    def save_job_description(self, jd: JobDescription) -> None:
        record = JobDescriptionRecord(id=str(jd.id), name=jd.name, content=jd.content)
        with Session(self._engine) as session:
            session.merge(record)
            session.commit()

    def save_analysis(self, analysis: AnalysisResult) -> None:
        record = AnalysisResultRecord(
            id=str(analysis.id),
            resume_id=str(analysis.resume_id),
            job_id=str(analysis.job_id),
            match_score=analysis.match_score,
            matched_keywords=analysis.matched_keywords,
            missing_keywords=analysis.missing_keywords,
            recommendations=analysis.recommendations,
            summary=analysis.summary,
        )
        with Session(self._engine) as session:
            session.merge(record)
            session.commit()

    def save_draft(self, draft: TailoredDraft) -> None:
        record = TailoredDraftRecord(
            id=str(draft.id),
            resume_id=str(draft.resume_id),
            job_id=str(draft.job_id),
            content=draft.content,
            change_summary=draft.change_summary,
            warnings=draft.warnings,
        )
        with Session(self._engine) as session:
            session.merge(record)
            session.commit()

    def get_resume(self, resume_id: str) -> Resume | None:
        from uuid import UUID
        from openclaw.core.documents import Resume
        with Session(self._engine) as session:
            record = session.get(ResumeRecord, resume_id)
            if not record:
                return None
            return Resume(id=UUID(record.id), name=record.name, content=record.content)

    def get_job_description(self, jd_id: str) -> JobDescription | None:
        from uuid import UUID
        from openclaw.core.documents import JobDescription
        with Session(self._engine) as session:
            record = session.get(JobDescriptionRecord, jd_id)
            if not record:
                return None
            return JobDescription(id=UUID(record.id), name=record.name, content=record.content)

    def list_resumes(self) -> Iterable[Resume]:
        from uuid import UUID
        from openclaw.core.documents import Resume
        with Session(self._engine) as session:
            records = session.exec(select(ResumeRecord)).all()
        return tuple(Resume(id=UUID(record.id), name=record.name, content=record.content) for record in records)

    def list_job_descriptions(self) -> Iterable[JobDescription]:
        from uuid import UUID
        from openclaw.core.documents import JobDescription
        with Session(self._engine) as session:
            records = session.exec(select(JobDescriptionRecord)).all()
        return tuple(JobDescription(id=UUID(record.id), name=record.name, content=record.content) for record in records)

