"""Big-document reliability: restart resume, checkpoints, cleanup of active jobs, compact results.
No model needed (job scheduling is observed, not executed, where translation would start)."""

import json
import os
import time

import backend.main as main
from backend.document_processors import _Context


def _job(job_id, upload_path, status="processing", created_at=None):
    now = created_at or time.time()
    return {
        "job_id": job_id, "status": status, "stage": 3, "progress": 40, "message": "",
        "user_filename": "big.pdf", "upload_path": str(upload_path), "source_lang": "English",
        "target_lang": "Hindi", "tone": "Professional", "created_at": now, "updated_at": now,
    }


def test_unfinished_jobs_are_resumed_after_restart(isolated_storage, monkeypatch):
    uploads, outputs = isolated_storage
    started = []
    monkeypatch.setattr(main, "_run_job", lambda job_id: started.append(job_id))
    ids = ["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222",
           "33333333-3333-3333-3333-333333333333"]
    for job_id, status in zip(ids, ["processing", "queued", "completed"]):
        upload = uploads / f"{job_id}.pdf"
        upload.write_bytes(b"%PDF")
        (outputs / f"job_{job_id}.json").write_text(json.dumps(_job(job_id, upload, status)))

    assert main.resume_unfinished_jobs() == 2
    deadline = time.time() + 5
    while len(started) < 2 and time.time() < deadline:
        time.sleep(0.05)
    assert sorted(started) == sorted(ids[:2])           # completed job is not re-run
    assert main.JOB_CACHE[ids[0]]["status"] == "queued"


def test_checkpoint_reload_skips_a_line_cut_off_by_the_crash(isolated_storage):
    ctx = _Context(isolated_storage[0] / "a.txt", "44444444-4444-4444-4444-444444444444", "English", "Hindi", lambda *a: None)
    ctx.checkpoint_path.write_text(
        json.dumps({"s": "Hello.", "t": "नमस्ते।"}, ensure_ascii=False) + "\n" + '{"s": "Half writ', encoding="utf-8"
    )
    assert ctx._load_checkpoint() == {"Hello.": "नमस्ते।"}


def test_cleanup_never_deletes_files_of_running_jobs(isolated_storage):
    uploads, _ = isolated_storage
    running_id = "55555555-5555-5555-5555-555555555555"
    running, stale = uploads / f"{running_id}.pdf", uploads / "66666666-6666-6666-6666-666666666666.pdf"
    for f in (running, stale):
        f.write_bytes(b"x")
        old = time.time() - 3 * 24 * 3600
        os.utime(f, (old, old))
    main.JOB_CACHE[running_id] = _job(running_id, running)
    main.cleanup_expired_files()
    assert running.exists() and not stale.exists()


def test_big_results_are_compacted_and_full_text_is_served(client, isolated_storage, monkeypatch):
    uploads, outputs = isolated_storage
    monkeypatch.setattr(main, "MAX_PREVIEW_CHARS", 1000)
    job_id = "77777777-7777-7777-7777-777777777777"
    output = outputs / f"translated_{job_id}.txt"
    output.write_text("x", encoding="utf-8")
    full = "अनुवाद " * 2000
    result = {
        "output_filename": output.name, "output_format": "txt", "output_path": str(output), "pages": 1,
        "chunk_count": 3000, "source_lang": "English", "target_lang": "Hindi",
        "chunks": [{"chunk_id": i, "original": "a", "translated": "b"} for i in range(3000)],
        "full_original": "a " * 2000, "full_translated": full, "warnings": [],
    }
    job = _job(job_id, uploads / f"{job_id}.txt", status="completed")
    job["result"] = main._compact_result(job_id, result)
    main.JOB_CACHE[job_id] = job

    status = client.get(f"/api/jobs/{job_id}").json()["result"]
    assert len(status["full_translated"]) == 1000 and status["text_truncated"] is True
    assert len(status["chunks"]) == main.MAX_PREVIEW_CHUNKS and status["chunks_truncated"] is True
    text = client.get(status["full_text_url"])
    assert text.status_code == 200 and text.content.decode("utf-8") == full
