"""Parallel jobs: inference turns are handed out fairly, in arrival order; jobs can be stopped."""

import json
import threading
import time

import backend.main as main
from backend.agent_pipeline import FairLock
from tests.conftest import submit


def test_queued_job_can_be_stopped_and_is_not_resumed_after_restart(client, isolated_storage, monkeypatch):
    monkeypatch.setattr(main, "_run_job", lambda job_id: None)  # keep it queued (no worker picks it up)
    job_id = submit(client, "a.txt", b"Hello there.").json()["job_id"]
    stopped = client.delete(f"/api/jobs/{job_id}").json()
    assert stopped["status"] == "cancelled"
    _, outputs = isolated_storage
    assert json.loads((outputs / f"job_{job_id}.json").read_text())["status"] == "cancelled"
    main.JOB_CACHE.clear()
    assert main.resume_unfinished_jobs() == 0


def test_running_job_stops_at_its_next_progress_update(isolated_storage, monkeypatch):
    uploads, _ = isolated_storage
    job_id = "88888888-8888-8888-8888-888888888888"
    upload = uploads / f"{job_id}.txt"
    upload.write_text("Hello there.", encoding="utf-8")
    now = time.time()
    main.JOB_CACHE[job_id] = {
        "job_id": job_id, "status": "queued", "user_filename": "a.txt", "upload_path": str(upload),
        "source_lang": "English", "target_lang": "Hindi", "tone": "Professional", "created_at": now, "updated_at": now,
    }

    def fake_process(progress, **kwargs):  # stands in for document processing: reports progress per batch
        main._CANCELLED.add(job_id)
        progress(3, 50, "Translating segments (1/2)")
        raise AssertionError("should have stopped at the progress update")

    monkeypatch.setattr(main.DocumentProcessor, "process_document", staticmethod(lambda **kw: fake_process(**kw)))
    main._run_job(job_id)
    assert main.JOB_CACHE[job_id]["status"] == "cancelled"
    main._CANCELLED.discard(job_id)


def test_fair_lock_serves_waiters_in_arrival_order():
    lock = FairLock()
    order = []
    lock.__enter__()  # held, so every thread below has to queue

    def worker(n):
        with lock:
            order.append(n)

    threads = []
    for n in range(5):
        t = threading.Thread(target=worker, args=(n,))
        t.start()
        threads.append(t)
        time.sleep(0.05)  # deterministic arrival order
    lock.__exit__(None, None, None)
    for t in threads:
        t.join(timeout=5)
    assert order == [0, 1, 2, 3, 4]


def test_two_jobs_alternate_batches_instead_of_one_finishing_first():
    lock = FairLock()
    timeline = []

    def job(name):
        for _ in range(4):
            with lock:
                timeline.append(name)
                time.sleep(0.02)  # a "batch" of model work

    a = threading.Thread(target=job, args=("A",))
    b = threading.Thread(target=job, args=("B",))
    a.start()
    time.sleep(0.005)
    b.start()
    a.join()
    b.join()
    # Both jobs progress together: B gets a turn long before A has finished all of its batches
    assert timeline.index("B") < 3 and timeline[-1] in ("A", "B") and timeline.count("A") == 4
    assert "".join(timeline) != "AAAABBBB"
