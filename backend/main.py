import json
import logging
import re
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

from backend.config import (
    UPLOADS_DIR,
    OUTPUTS_DIR,
    INDIC_LANGUAGES,
    INDICTRANS2_EN_INDIC_MODEL,
    JOB_TTL_HOURS,
    MAX_PARALLEL_JOBS,
    MAX_UPLOAD_MB,
    PRELOAD_MODELS,
    SUPPORTED_EXTENSIONS,
    get_lang_code,
    resolve_lang_code,
)
from backend.document_processors import DocumentError, DocumentProcessor
from backend.agent_pipeline import ModelLoadError, TranslationError, agent

logger = logging.getLogger("transdoc_api")

MAX_PREVIEW_CHUNKS = 2000
MAX_PREVIEW_CHARS = 200_000  # full text beyond this is served by /api/text/{job_id}
_JOB_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# One worker: a single model instance in memory, documents translated one at a time.
# Created per app lifespan so a restarted app (reload, tests) gets a live executor.
_executor: Optional[ThreadPoolExecutor] = None
JOB_CACHE: Dict[str, Dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()
_CANCELLED: set = set()  # job ids the user stopped; running jobs notice at their next progress update


class JobCancelled(Exception):
    """Raised inside a running job once the user has stopped it."""


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=MAX_PARALLEL_JOBS, thread_name_prefix="translate")
    return _executor


def cleanup_expired_files(now: Optional[float] = None) -> int:
    """Deletes uploads/outputs (and in-memory jobs) older than JOB_TTL_HOURS. Returns files removed.
    Files of queued/running jobs are never deleted, however long a big document takes."""
    cutoff = (now or time.time()) - JOB_TTL_HOURS * 3600
    with _JOBS_LOCK:
        active = {j for j, job in JOB_CACHE.items() if job["status"] in ("queued", "processing")}
    removed = 0
    for directory in (UPLOADS_DIR, OUTPUTS_DIR):
        for f in directory.iterdir():
            if any(job_id in f.name for job_id in active):
                continue
            if f.is_file() and not f.name.startswith(".") and f.stat().st_mtime < cutoff:
                try:
                    f.unlink()
                    removed += 1
                except OSError as e:
                    logger.warning(f"Could not delete expired file {f}: {e}")
    with _JOBS_LOCK:
        for job_id in [j for j, job in JOB_CACHE.items()
                       if job["created_at"] < cutoff and job["status"] in ("completed", "failed", "cancelled")]:
            JOB_CACHE.pop(job_id, None)
    return removed


def _preload_models() -> None:
    try:
        agent.check_availability()
    except Exception as e:
        logger.warning(f"Could not check which translation directions are available: {e}")
    for direction in PRELOAD_MODELS:
        try:
            agent.load_model(direction)
        except Exception as e:
            logger.error(f"Preloading {direction} failed: {e}")


def resume_unfinished_jobs() -> int:
    """Re-queues jobs that were queued or running when the backend stopped (restart, rebuild, crash).
    Translations finished before the stop are reused from the job's checkpoint file."""
    resumed = []
    for meta in OUTPUTS_DIR.glob("job_*.json"):
        try:
            job = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if job.get("status") not in ("queued", "processing") or not Path(job.get("upload_path", "")).exists():
            continue
        if job.get("cancel_requested"):
            job.update(status="cancelled", message="Stopped by the user")
            with _JOBS_LOCK:
                JOB_CACHE[job["job_id"]] = job
            _persist_job(job["job_id"])
            continue
        job.update(status="queued", stage=1, progress=0, message="Resuming after a restart")
        with _JOBS_LOCK:
            JOB_CACHE[job["job_id"]] = job
        resumed.append(job)
    for job in sorted(resumed, key=lambda j: j["created_at"]):
        _get_executor().submit(_run_job, job["job_id"])
    return len(resumed)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _executor
    _get_executor()
    resumed = resume_unfinished_jobs()
    if resumed:
        logger.info(f"Resumed {resumed} unfinished translation job(s)")
    removed = cleanup_expired_files()
    if removed:
        logger.info(f"Removed {removed} expired file(s) older than {JOB_TTL_HOURS}h")
    # Availability check (network metadata only) and optional preloading run in the background
    threading.Thread(target=_preload_models, daemon=True, name="preload").start()
    yield
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None


app = FastAPI(
    title="IndicTrans2 Document Translation API",
    description="Offline neural & local document translation service for PDF, XLSX, DOCX, and TXT using AI4Bharat IndicTrans2",
    version="2.1.0",
    lifespan=lifespan,
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_media_type(ext: str) -> str:
    ext_lower = ext.lower().lstrip(".")
    mime_types = {
        "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain; charset=utf-8",
        "csv": "text/csv; charset=utf-8",
        "md": "text/markdown; charset=utf-8",
    }
    return mime_types.get(ext_lower, "application/octet-stream")


# ---------------------------------------------------------------------- job store
def _meta_path(job_id: str) -> Path:
    return OUTPUTS_DIR / f"job_{job_id}.json"


def _get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Looks a job up in memory, falling back to its persisted metadata (survives restarts)."""
    if not _JOB_ID_RE.match(job_id):
        return None
    with _JOBS_LOCK:
        job = JOB_CACHE.get(job_id)
    if job is not None:
        return job
    meta = _meta_path(job_id)
    if meta.exists():
        try:
            job = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        with _JOBS_LOCK:
            JOB_CACHE[job_id] = job
        return job
    return None


def _update_job(job_id: str, **fields) -> None:
    with _JOBS_LOCK:
        job = JOB_CACHE[job_id]
        job.update(fields, updated_at=time.time())


def _persist_job(job_id: str) -> None:
    """Saves job metadata so the job survives backend restarts (resumed or still downloadable)."""
    with _JOBS_LOCK:
        snapshot = json.dumps(JOB_CACHE[job_id], ensure_ascii=False)
    try:
        tmp = _meta_path(job_id).with_suffix(".tmp")
        tmp.write_text(snapshot, encoding="utf-8")
        tmp.replace(_meta_path(job_id))
    except OSError as e:
        logger.warning(f"Could not persist job metadata for {job_id}: {e}")


def _text_path(job_id: str) -> Path:
    return OUTPUTS_DIR / f"translated_text_{job_id}.txt"


def _compact_result(job_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Keeps the status payload small for big documents: the full translated text goes to its own
    file (served by /api/text), and the preview keeps only the first chunks/characters."""
    try:
        _text_path(job_id).write_text(result["full_translated"], encoding="utf-8")
    except OSError as e:
        logger.warning(f"Could not save full text for {job_id}: {e}")
    truncated = (len(result["full_original"]) > MAX_PREVIEW_CHARS
                 or len(result["full_translated"]) > MAX_PREVIEW_CHARS)
    return {
        **result,
        "chunks": result["chunks"][:MAX_PREVIEW_CHUNKS],
        "chunks_truncated": len(result["chunks"]) > MAX_PREVIEW_CHUNKS,
        "full_original": result["full_original"][:MAX_PREVIEW_CHARS],
        "full_translated": result["full_translated"][:MAX_PREVIEW_CHARS],
        "text_truncated": truncated,
    }


def _queue_position(job_id: str) -> int:
    with _JOBS_LOCK:
        queued = sorted((j["created_at"], j["job_id"]) for j in JOB_CACHE.values() if j["status"] == "queued")
    for i, (_, jid) in enumerate(queued):
        if jid == job_id:
            return i + 1
    return 0


def _run_job(job_id: str) -> None:
    job = JOB_CACHE[job_id]
    if job_id in _CANCELLED or job["status"] == "cancelled":
        return
    _update_job(job_id, status="processing", stage=1, progress=1, message="Starting")

    def progress(stage: int, percent: float, message: str) -> None:
        if job_id in _CANCELLED:
            raise JobCancelled()
        _update_job(job_id, stage=stage, progress=round(min(max(percent, 0), 100), 1), message=message)

    try:
        result = DocumentProcessor.process_document(
            file_path=Path(job["upload_path"]),
            source_lang=job["source_lang"],
            target_lang=job["target_lang"],
            tone=job["tone"],
            job_id=job_id,
            progress=progress,
        )
        result["user_filename"] = job["user_filename"]
        result["upload_path"] = job["upload_path"]
        _update_job(job_id, status="completed", stage=4, progress=100, message="Translation complete",
                    result=_compact_result(job_id, result))
    except JobCancelled:
        _update_job(job_id, status="cancelled", message="Stopped by the user")
        logger.info(f"Job {job_id} stopped by the user")
    except DocumentError as e:
        _update_job(job_id, status="failed", error=str(e), error_type="document")
    except ModelLoadError as e:
        _update_job(job_id, status="failed", error=str(e), error_type="model")
    except TranslationError as e:
        _update_job(job_id, status="failed", error=str(e), error_type="translation")
    except MemoryError:
        _update_job(job_id, status="failed", error_type="memory",
                    error="The machine ran out of memory. Try a smaller document or lower TRANSLATION_BATCH_SIZE.")
    except ValueError as e:
        _update_job(job_id, status="failed", error=str(e), error_type="validation")
    except Exception as e:
        traceback.print_exc()
        _update_job(job_id, status="failed", error=f"Unexpected error: {type(e).__name__}: {e}", error_type="internal")
    finally:
        _persist_job(job_id)


def _public_result(job: Dict[str, Any]) -> Dict[str, Any]:
    result = job["result"]
    job_id = job["job_id"]
    stem = Path(job["user_filename"]).stem or "document"
    output_ext = Path(result["output_path"]).suffix
    chunks = result["chunks"]
    return {
        "success": True,
        "job_id": job_id,
        "filename": job["user_filename"],
        "output_filename": result["output_filename"],
        "output_format": result["output_format"],
        "download_filename": f"translated_{stem}{output_ext}",
        "pages": result["pages"],
        "chunk_count": result["chunk_count"],
        "source_lang": result["source_lang"],
        "target_lang": result["target_lang"],
        "src_code": get_lang_code(result["source_lang"]),
        "tgt_code": get_lang_code(result["target_lang"]),
        "engine": "AI4Bharat IndicTrans2 (local)",
        "api_key_required": False,
        "download_url": f"/api/download/{job_id}",
        "download_original_url": f"/api/download/{job_id}?type=original",
        "original_url": f"/api/document/{job_id}/original",
        "translated_url": f"/api/document/{job_id}/translated",
        "chunks": chunks[:MAX_PREVIEW_CHUNKS],
        "chunks_truncated": result.get("chunks_truncated", len(chunks) > MAX_PREVIEW_CHUNKS),
        "full_original": result["full_original"][:MAX_PREVIEW_CHARS],
        "full_translated": result["full_translated"][:MAX_PREVIEW_CHARS],
        "text_truncated": result.get("text_truncated", False),
        "full_text_url": f"/api/text/{job_id}",
        "warnings": result.get("warnings", []),
    }


def _job_status(job: Dict[str, Any]) -> Dict[str, Any]:
    status = {
        "job_id": job["job_id"],
        "status": job["status"],
        "stage": job.get("stage", 1),
        "progress": job.get("progress", 0),
        "message": job.get("message", ""),
        "filename": job["user_filename"],
        "source_lang": job["source_lang"],
        "target_lang": job["target_lang"],
    }
    if job["status"] == "queued":
        status["queue_position"] = _queue_position(job["job_id"])
    if job["status"] == "failed":
        status["error"] = job.get("error")
        status["error_type"] = job.get("error_type")
    if job["status"] == "completed":
        status["result"] = _public_result(job)
    return status


# ---------------------------------------------------------------------- routes
@app.get("/")
def root():
    return {
        "service": "IndicTrans2 Document Translation Studio API (AI4Bharat)",
        "engine": "IndicTrans2",
        "model": INDICTRANS2_EN_INDIC_MODEL,
        "api_key_required": False,
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
def health_check():
    model_status = agent.status()
    with _JOBS_LOCK:
        active = sum(1 for j in JOB_CACHE.values() if j["status"] in ("queued", "processing"))
    return {
        "status": "healthy",
        "engine": "AI4Bharat IndicTrans2",
        "model": INDICTRANS2_EN_INDIC_MODEL,
        "api_key_required": False,
        "neural_available": agent.neural_available,
        "mode": "local_indictrans2",
        "model_status": model_status,
        # Only an engine-wide failure is a "not ready" error; per-direction problems are in `directions`
        "model_error": model_status["torch_error"],
        "directions": agent.availability,
        "active_jobs": active,
        "max_parallel_jobs": MAX_PARALLEL_JOBS,
        "max_upload_mb": MAX_UPLOAD_MB,
        "supported_formats": [e.lstrip(".") for e in SUPPORTED_EXTENSIONS],
        "notice": "All translation runs locally with AI4Bharat IndicTrans2; no document content leaves this machine.",
    }


@app.get("/api/languages")
def get_languages():
    return {"languages": INDIC_LANGUAGES}


@app.post("/api/translate", status_code=202)
async def translate_document(
    file: UploadFile = File(...),
    source_lang: str = Form("English"),
    target_lang: str = Form("Hindi"),
    tone: str = Form("Professional"),
):
    filename = Path(file.filename or "uploaded_document").name
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext or filename}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        )
    src_code, tgt_code = resolve_lang_code(source_lang), resolve_lang_code(target_lang)
    if src_code is None or tgt_code is None:
        raise HTTPException(status_code=400, detail=f"Unsupported language: '{source_lang if src_code is None else target_lang}'.")
    if src_code == tgt_code:
        raise HTTPException(status_code=400, detail="Source and target languages must be different.")

    job_id = str(uuid.uuid4())
    saved_upload_path = UPLOADS_DIR / f"{job_id}{ext}"
    limit = MAX_UPLOAD_MB * 1024 * 1024
    size = 0
    try:
        with open(saved_upload_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail=f"File is larger than the {MAX_UPLOAD_MB} MB limit.")
                buffer.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    except BaseException:
        saved_upload_path.unlink(missing_ok=True)
        raise

    cleanup_expired_files()
    now = time.time()
    with _JOBS_LOCK:
        JOB_CACHE[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "stage": 1,
            "progress": 0,
            "message": "Waiting in queue",
            "user_filename": filename,
            "upload_path": str(saved_upload_path),
            "source_lang": source_lang,
            "target_lang": target_lang,
            "tone": tone,
            "created_at": now,
            "updated_at": now,
        }
    _persist_job(job_id)  # lets the job resume if the backend restarts before it finishes
    _get_executor().submit(_run_job, job_id)

    return {
        "success": True,
        "job_id": job_id,
        "status": "queued",
        "filename": filename,
        "status_url": f"/api/jobs/{job_id}",
        "queue_position": _queue_position(job_id),
    }


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    job = _get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    return _job_status(job)


@app.delete("/api/jobs/{job_id}")
def cancel_job(job_id: str):
    """Stops a queued or running translation (a running one stops after its current batch)."""
    job = _get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    if job["status"] in ("queued", "processing"):
        _CANCELLED.add(job_id)
        _update_job(job_id, cancel_requested=True)  # persisted, so a restart doesn't resume it
        if job["status"] == "queued":
            _update_job(job_id, status="cancelled", message="Stopped by the user")
        _persist_job(job_id)
    return _job_status(job)


def _resolve_file(job_id: str, doc_type: str) -> Path:
    job = _get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    if doc_type == "original":
        path = Path(job["upload_path"])
    else:
        if job["status"] != "completed":
            raise HTTPException(status_code=409, detail=f"Translation is not ready (status: {job['status']}).")
        path = Path(job["result"]["output_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Document ({doc_type}) not found or expired.")
    return path


@app.get("/api/document/{job_id}/{doc_type}")
def stream_document_for_preview(job_id: str, doc_type: str):
    """Streams document inline for browser preview (PDF viewer / iframe)."""
    if doc_type not in ("translated", "original"):
        raise HTTPException(status_code=404, detail="Unknown document type.")
    target_file = _resolve_file(job_id, doc_type)
    return FileResponse(
        path=str(target_file),
        media_type=get_media_type(target_file.suffix),
        filename=target_file.name,
        content_disposition_type="inline",
    )


@app.get("/api/download/{job_id}")
def download_document_file(job_id: str, type: str = Query("translated", pattern="^(translated|original)$")):
    """Downloads either the translated document or original document with attachment header."""
    target_file = _resolve_file(job_id, type)
    job = _get_job(job_id)
    if type == "translated":
        download_filename = f"translated_{Path(job['user_filename']).stem or 'document'}{target_file.suffix}"
    else:
        download_filename = job["user_filename"]
    # FileResponse emits an RFC 5987 filename* parameter, so non-ASCII names are safe
    return FileResponse(
        path=str(target_file),
        filename=download_filename,
        media_type=get_media_type(target_file.suffix),
    )


@app.get("/api/text/{job_id}")
def get_full_translated_text(job_id: str):
    """Full translated text as plain UTF-8 (the status payload only carries a preview for big documents)."""
    job = _get_job(job_id)
    if job is None or job["status"] != "completed":
        raise HTTPException(status_code=404, detail="Translation not found or not finished.")
    path = _text_path(job_id)
    if not path.exists():  # jobs completed before this file existed
        return PlainTextResponse(job["result"]["full_translated"])
    return FileResponse(path=str(path), media_type="text/plain; charset=utf-8")


@app.get("/api/preview/{job_id}")
def get_job_preview(job_id: str):
    job = _get_job(job_id)
    if job is None or job["status"] != "completed":
        raise HTTPException(status_code=404, detail="Job preview not found.")
    return _public_result(job)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
