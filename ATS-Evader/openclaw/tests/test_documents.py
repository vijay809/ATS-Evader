from pathlib import Path

import pytest

from openclaw.plugins.documents import DocumentIngestionError, DocumentIngestionService


def test_reads_txt_files(tmp_path: Path) -> None:
    file = tmp_path / "test.txt"
    file.write_text("Hello, this is text.", encoding="utf-8")

    service = DocumentIngestionService()
    content = service.read_text(file)
    assert content == "Hello, this is text."


def test_raises_error_on_missing_file() -> None:
    service = DocumentIngestionService()
    with pytest.raises(DocumentIngestionError, match="File not found"):
        service.read_text("does_not_exist.txt")


def test_raises_error_on_unsupported_extension(tmp_path: Path) -> None:
    file = tmp_path / "test.unknown"
    file.write_text("data")

    service = DocumentIngestionService()
    with pytest.raises(DocumentIngestionError, match="Failed to read .unknown file"):
        service.read_text(file)
