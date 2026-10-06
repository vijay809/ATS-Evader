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


def test_job_description_serial_no(tmp_path: Path) -> None:
    from openclaw.core.documents import JobDescription
    from openclaw.core.storage import SQLiteDocumentRepository

    repo = SQLiteDocumentRepository(tmp_path / "test.db")
    jd1 = JobDescription(name="Engineer at Google", content="Python JD", url="https://naukri.com/jd-100")
    repo.save_job_description(jd1)
    assert jd1.serial_no == 1

    jd2 = JobDescription(name="Lead at Meta", content="Rust JD", url="https://linkedin.com/jd-200")
    repo.save_job_description(jd2)
    assert jd2.serial_no == 2

    assert repo.get_next_serial_no() == 3

    # Lookup by ID
    found1 = repo.get_job_description(str(jd1.id))
    assert found1 is not None
    assert found1.serial_no == 1

    # Lookup by serial_no string
    found_by_serial = repo.get_job_description("1")
    assert found_by_serial is not None
    assert found_by_serial.name == "Engineer at Google"

    # Lookup by Portal_SerialNo string
    found_by_portal = repo.get_job_description("Naukri_1")
    assert found_by_portal is not None
    assert found_by_portal.name == "Engineer at Google"

