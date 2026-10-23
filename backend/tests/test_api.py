"""API validation and failure handling (no model required: failures happen before
inference, or the model load failure is real)."""

import backend.agent_pipeline as agent_pipeline
import backend.main as main
from backend.agent_pipeline import agent
from tests.conftest import make_encrypted_pdf, make_scanned_pdf, submit, wait_for_job


def test_health_reports_local_model_status(client):
    data = client.get("/api/health").json()
    assert data["status"] == "healthy"
    assert data["mode"] == "local_indictrans2"
    assert "model_status" in data and "max_upload_mb" in data


def test_unsupported_format_is_400_not_500(client):
    r = submit(client, "slides.pptx", b"data")
    assert r.status_code == 400
    assert "Unsupported format" in r.json()["detail"]


def test_language_validation(client):
    assert submit(client, "a.txt", b"Hello", "English", "English").status_code == 400
    r = submit(client, "a.txt", b"Hello", "English", "Klingon")
    assert r.status_code == 400 and "Klingon" in r.json()["detail"]


def test_empty_and_oversized_uploads_rejected(client, monkeypatch, isolated_storage):
    assert submit(client, "a.txt", b"").status_code == 400
    monkeypatch.setattr(main, "MAX_UPLOAD_MB", 1)
    r = submit(client, "big.txt", b"a" * (1024 * 1024 + 10))
    assert r.status_code == 413
    uploads, _ = isolated_storage
    assert list(uploads.iterdir()) == []  # partial upload removed


def test_unknown_and_malformed_job_ids(client):
    assert client.get("/api/jobs/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/api/jobs/..%2F..%2Fsecret").status_code == 404
    assert client.get("/api/download/not-a-job").status_code == 404
    assert client.get("/api/document/00000000-0000-0000-0000-000000000000/other").status_code == 404


def _failed(client, filename, data):
    r = submit(client, filename, data)
    assert r.status_code == 202
    status = wait_for_job(client, r.json()["job_id"], timeout=60)
    assert status["status"] == "failed"
    return status


def test_corrupted_pdf_fails_with_clear_message(client):
    status = _failed(client, "broken.pdf", b"%PDF-1.7 this is not really a pdf")
    assert status["error_type"] == "document" and "corrupted" in status["error"]


def test_scanned_pdf_reports_missing_text_layer(client):
    status = _failed(client, "scan.pdf", make_scanned_pdf())
    assert status["error_type"] == "document" and "OCR" in status["error"]


def test_password_protected_pdf(client):
    status = _failed(client, "locked.pdf", make_encrypted_pdf())
    assert "password" in status["error"].lower()


def test_corrupted_office_files(client):
    assert _failed(client, "broken.docx", b"PK\x03\x04 nope")["error_type"] == "document"
    assert _failed(client, "broken.xlsx", b"not a workbook")["error_type"] == "document"
    assert _failed(client, "broken.xls", b"not a workbook")["error_type"] == "document"


def test_numbers_only_document_is_reported(client):
    status = _failed(client, "numbers.csv", b"1,2,3\n4,5,6\n")
    assert "No translatable text" in status["error"]


def test_model_load_failure_is_reported_not_silently_bypassed(client, monkeypatch, tmp_path):
    """A model that cannot load must fail the job with a clear message. The old code fell back to
    cloud APIs or returned the source text unchanged."""
    monkeypatch.setitem(agent_pipeline.MODEL_NAMES, "indic-en", str(tmp_path / "missing-model"))
    agent._models.pop("indic-en", None)
    r = submit(client, "note.txt", "यह एक परीक्षण है।".encode("utf-8"), "Hindi", "English")
    status = wait_for_job(client, r.json()["job_id"], timeout=120)
    assert status["status"] == "failed"
    assert status["error_type"] == "model"
    assert status["error"]
    health = client.get("/api/health").json()
    assert health["model_error"]


def test_original_is_downloadable_with_unicode_filename_even_when_job_failed(client):
    r = submit(client, "रिपोर्ट.pdf", b"%PDF-1.7 broken")
    job_id = r.json()["job_id"]
    wait_for_job(client, job_id, timeout=60)
    d = client.get(f"/api/download/{job_id}?type=original")
    assert d.status_code == 200
    assert "filename*=utf-8''" in d.headers["content-disposition"]
    assert client.get(f"/api/download/{job_id}").status_code == 409  # translated not ready
