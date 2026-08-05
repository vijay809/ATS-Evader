"""Document ingestion plugin for OpenClaw."""

from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader
from docx import Document

from openclaw.plugins.manager import PluginContext

logger = logging.getLogger(__name__)

DOCUMENTS_SERVICE = "documents.ingestion"


class DocumentIngestionError(RuntimeError):
    """Failed to read or parse the document."""


class DocumentIngestionService:
    def read_text(self, file_path: str | Path) -> str:
        path = Path(file_path)
        if not path.exists():
            raise DocumentIngestionError(f"File not found: {path}")

        ext = path.suffix.lower()
        try:
            if ext == ".pdf":
                return self._read_pdf(path)
            elif ext == ".docx":
                return self._read_docx(path)
            elif ext in {".txt", ".md"}:
                return path.read_text(encoding="utf-8")
            else:
                raise DocumentIngestionError(f"Unsupported file extension: {ext}")
        except Exception as error:
            raise DocumentIngestionError(f"Failed to read {ext} file") from error

    @staticmethod
    def _read_pdf(path: Path) -> str:
        reader = PdfReader(path)
        text = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text.append(page_text)
        return "\n".join(text)

    @staticmethod
    def _read_docx(path: Path) -> str:
        doc = Document(str(path))
        return "\n".join(paragraph.text for paragraph in doc.paragraphs)


class DocumentsPlugin:
    name = "documents"
    requires: tuple[str, ...] = ()

    def __init__(self) -> None:
        self._context: PluginContext | None = None

    async def start(self, context: PluginContext) -> None:
        context.services.provide(DOCUMENTS_SERVICE, DocumentIngestionService())
        self._context = context

    async def stop(self) -> None:
        if self._context is not None:
            self._context.services.remove(DOCUMENTS_SERVICE)
            self._context = None


def create_plugin() -> DocumentsPlugin:
    return DocumentsPlugin()
