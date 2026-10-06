"""SQLite persistence owned by the runtime.

Plugins receive higher-level services instead of direct database access. This keeps schema
ownership, migrations, and data retention decisions at the runtime boundary.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from sqlmodel import Field, Session, SQLModel, create_engine, desc, func, select

if TYPE_CHECKING:
    from openclaw.core.documents import (
        AnalysisResult,
        JobDescription,
        Preference,
        Resume,
        StructuredResume,
        TailoredDraft,
    )
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

class StructuredResumeRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    raw_content: str
    parsed_json: str
    is_active: bool = False
    created_at: float = 0.0

class PreferenceRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    key: str
    value: str


class JobDescriptionRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    serial_no: int | None = Field(default=None, index=True)
    name: str
    content: str
    status: str = "Discovered"
    url: str | None = None


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
    def save_structured_resume(self, resume: StructuredResume) -> None: ...
    def save_preference(self, pref: Preference) -> None: ...
    def save_job_description(self, jd: JobDescription) -> None: ...
    def save_analysis(self, analysis: AnalysisResult) -> None: ...
    def save_draft(self, draft: TailoredDraft) -> None: ...
    
    def get_resume(self, resume_id: str) -> Resume | None: ...
    def get_structured_resume(self) -> StructuredResume | None: ...
    def get_active_structured_resume(self) -> StructuredResume | None: ...
    def list_structured_resumes(self) -> Iterable[StructuredResume]: ...
    def set_active_structured_resume(self, resume_id: str) -> None: ...
    def delete_structured_resume(self, resume_id: str) -> None: ...
    def get_preferences(self) -> Iterable[Preference]: ...
    def get_job_description(self, jd_id: str) -> JobDescription | None: ...
    def list_resumes(self) -> Iterable[Resume]: ...
    def list_job_descriptions(self) -> Iterable[JobDescription]: ...
    def get_latest_analysis(self, job_id: str) -> AnalysisResult | None: ...
    def get_next_serial_no(self) -> int: ...


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
        SQLModel.metadata.create_all(self._engine)
        with self._engine.begin() as conn:
            import sqlalchemy as sa
            try:
                conn.execute(sa.text("ALTER TABLE jobdescriptionrecord ADD COLUMN serial_no INTEGER"))
            except Exception:
                pass
            try:
                conn.execute(sa.text("UPDATE jobdescriptionrecord SET serial_no = rowid WHERE serial_no IS NULL"))
            except Exception:
                pass

    def save_resume(self, resume: Resume) -> None:
        record = ResumeRecord(id=str(resume.id), name=resume.name, content=resume.content)
        with Session(self._engine) as session:
            session.merge(record)
            session.commit()

    def save_structured_resume(self, resume: StructuredResume) -> None:
        record = StructuredResumeRecord(
            id=str(resume.id), name=resume.name, raw_content=resume.raw_content, 
            parsed_json=resume.parsed_json, is_active=resume.is_active, created_at=resume.created_at
        )
        with Session(self._engine) as session:
            session.merge(record)
            session.commit()

    def save_preference(self, pref: Preference) -> None:
        record = PreferenceRecord(id=str(pref.id), key=pref.key, value=pref.value)
        with Session(self._engine) as session:
            session.merge(record)
            session.commit()

    def save_job_description(self, jd: JobDescription) -> None:
        with Session(self._engine) as session:
            if jd.serial_no is None:
                max_serial = session.exec(select(func.max(JobDescriptionRecord.serial_no))).one_or_none()
                if max_serial is None:
                    max_serial = session.exec(select(func.count(JobDescriptionRecord.id))).one_or_none() or 0
                jd.serial_no = (max_serial or 0) + 1

            record = JobDescriptionRecord(
                id=str(jd.id),
                serial_no=jd.serial_no,
                name=jd.name,
                content=jd.content,
                status=jd.status,
                url=jd.url,
            )
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

    def get_structured_resume(self) -> StructuredResume | None:
        return self.get_active_structured_resume()

    def get_active_structured_resume(self) -> StructuredResume | None:
        from uuid import UUID

        from openclaw.core.documents import StructuredResume
        with Session(self._engine) as session:
            record = session.exec(select(StructuredResumeRecord).where(StructuredResumeRecord.is_active == True)).first()
            if not record:
                record = session.exec(select(StructuredResumeRecord).order_by(desc(StructuredResumeRecord.created_at))).first()
            if not record:
                return None
            return StructuredResume(id=UUID(record.id), name=record.name, raw_content=record.raw_content, parsed_json=record.parsed_json, is_active=record.is_active, created_at=record.created_at)

    def list_structured_resumes(self) -> Iterable[StructuredResume]:
        from uuid import UUID

        from openclaw.core.documents import StructuredResume
        with Session(self._engine) as session:
            records = session.exec(select(StructuredResumeRecord).order_by(desc(StructuredResumeRecord.created_at))).all()
        return tuple(StructuredResume(id=UUID(r.id), name=r.name, raw_content=r.raw_content, parsed_json=r.parsed_json, is_active=r.is_active, created_at=r.created_at) for r in records)

    def set_active_structured_resume(self, resume_id: str) -> None:
        with Session(self._engine) as session:
            all_records = session.exec(select(StructuredResumeRecord)).all()
            for r in all_records:
                r.is_active = False
                session.add(r)
            target = session.get(StructuredResumeRecord, resume_id)
            if target:
                target.is_active = True
                session.add(target)
            session.commit()

    def delete_structured_resume(self, resume_id: str) -> None:
        with Session(self._engine) as session:
            target = session.get(StructuredResumeRecord, resume_id)
            if target:
                session.delete(target)
                session.commit()

    def get_preferences(self) -> Iterable[Preference]:
        from uuid import UUID

        from openclaw.core.documents import Preference
        with Session(self._engine) as session:
            records = session.exec(select(PreferenceRecord)).all()
        return tuple(Preference(id=UUID(record.id), key=record.key, value=record.value) for record in records)

    def get_job_description(self, jd_id: str) -> JobDescription | None:
        from uuid import UUID

        from openclaw.core.documents import JobDescription
        with Session(self._engine) as session:
            record = session.get(JobDescriptionRecord, jd_id)
            if not record:
                clean_id = jd_id.split("_")[-1] if "_" in jd_id else jd_id
                if clean_id.isdigit():
                    record = session.exec(
                        select(JobDescriptionRecord).where(JobDescriptionRecord.serial_no == int(clean_id))
                    ).first()
            if not record:
                return None
            try:
                rec_id = UUID(record.id)
            except ValueError:
                rec_id = record.id
            return JobDescription(
                id=rec_id,
                serial_no=record.serial_no,
                name=record.name,
                content=record.content,
                status=record.status,
                url=record.url,
            )

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
            records = session.exec(select(JobDescriptionRecord).order_by(JobDescriptionRecord.serial_no)).all()
        result = []
        for record in records:
            try:
                rec_id = UUID(record.id)
            except ValueError:
                rec_id = record.id
            result.append(
                JobDescription(
                    id=rec_id,
                    serial_no=record.serial_no,
                    name=record.name,
                    content=record.content,
                    status=record.status,
                    url=record.url,
                )
            )
        return tuple(result)

    def get_next_serial_no(self) -> int:
        with Session(self._engine) as session:
            max_serial = session.exec(select(func.max(JobDescriptionRecord.serial_no))).one_or_none()
            if max_serial is None:
                count = session.exec(select(func.count(JobDescriptionRecord.id))).one_or_none() or 0
                return count + 1
            return max_serial + 1

    def get_latest_analysis(self, job_id: str) -> AnalysisResult | None:
        from uuid import UUID

        from openclaw.core.documents import AnalysisResult
        with Session(self._engine) as session:
            # Get most recent analysis for this job
            record = session.exec(
                select(AnalysisResultRecord)
                .where(AnalysisResultRecord.job_id == job_id)
                .order_by(desc(AnalysisResultRecord.id))  # Just use ID or if we had timestamp we'd use that
            ).first()
            if not record:
                return None
            return AnalysisResult(
                id=UUID(record.id),
                resume_id=UUID(record.resume_id),
                job_id=UUID(record.job_id),
                match_score=record.match_score,
                matched_keywords=record.matched_keywords,
                missing_keywords=record.missing_keywords,
                recommendations=record.recommendations,
                summary=record.summary
            )

