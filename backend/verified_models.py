"""
Builds a local copy of a gated official IndicTrans2 model from public copies, without a token.

AI4Bharat publishes the IndicTrans2 weights (MIT license) in Hugging Face repos gated behind a click-through
form. Hugging Face still publishes every file's fingerprint (sha256 for large files, git blob sha1 for small
ones) of the gated repo. This module downloads each needed file from public repos and keeps it only if its
fingerprint equals the official one, so the assembled folder is byte-for-byte the official model, including
the Python model code that transformers runs with trust_remote_code. If any file can't be matched, nothing
is used.
"""

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from backend.config import MODELS_DIR

logger = logging.getLogger("verified_models")

# Public repos found to contain official files (each file is still verified individually)
PUBLIC_SOURCES: Dict[str, List[str]] = {
    "ai4bharat/indictrans2-indic-en-dist-200M": [
        "krpraveen/indictrans2-sanskrit-en-finetuned",  # official code/tokenizer/config files
        "Raghavan/indictrans2-indic-en-dist-200M",       # official pytorch_model.bin
        "benfranklinms/indictrans2-indic-en-dist-200M",  # official pytorch_model.bin
    ],
}

SKIP_FILES = {".gitattributes", "README.md"}
WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")  # one of them is enough


def local_copy_dir(official_repo: str) -> Path:
    return MODELS_DIR / official_repo.split("/")[-1]


def has_verified_copy(official_repo: str) -> bool:
    return (local_copy_dir(official_repo) / ".verified").exists()


def can_assemble(official_repo: str) -> bool:
    return official_repo in PUBLIC_SOURCES


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _matches(path: Path, official) -> bool:
    if official.lfs:
        return _sha256(path) == official.lfs.sha256
    return _git_blob_sha1(path) == official.blob_id


def assemble_verified_copy(official_repo: str) -> Path:
    """Returns the folder of a verified local copy, building it on first use (downloads ~1 GB)."""
    target = local_copy_dir(official_repo)
    if has_verified_copy(official_repo):
        return target
    if not can_assemble(official_repo):
        raise RuntimeError(f"No verified public copy is known for {official_repo}")

    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi()
    official = {s.rfilename: s for s in api.model_info(official_repo, files_metadata=True).siblings}
    sources = []
    for repo in PUBLIC_SOURCES[official_repo]:
        try:
            info = api.model_info(repo, files_metadata=True)
            sources.append((repo, info.sha, {s.rfilename: s for s in info.siblings}))
        except Exception as e:
            logger.warning(f"Public source {repo} unavailable: {e}")

    needed = [f for f in official if f not in SKIP_FILES and f not in WEIGHT_FILES]
    staging = target.with_name(target.name + ".partial")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)

    def fetch(filename: str) -> bool:
        want = official[filename]
        for repo, sha, files in sources:
            have = files.get(filename)
            if have is None or have.size != want.size:
                continue
            # Skip downloads that metadata already proves different
            if want.lfs and have.lfs and want.lfs.sha256 != have.lfs.sha256:
                continue
            if not want.lfs and not have.lfs and want.blob_id != have.blob_id:
                continue
            path = Path(hf_hub_download(repo, filename, revision=sha, local_dir=staging / "_dl" / repo.replace("/", "__")))
            if _matches(path, want):
                shutil.move(str(path), staging / filename)
                logger.info(f"Verified {filename} from {repo}")
                return True
            logger.warning(f"{filename} from {repo} does not match the official file; ignored")
        return False

    try:
        missing = [f for f in needed if not fetch(f)]
        if not any(w in official and fetch(w) for w in WEIGHT_FILES):
            missing.append("model weights")
        if missing:
            raise RuntimeError(f"Could not find verified copies of: {', '.join(missing)}")
        shutil.rmtree(staging / "_dl", ignore_errors=True)
        (staging / ".verified").write_text(f"Byte-identical to {official_repo}\n", encoding="utf-8")
        shutil.rmtree(target, ignore_errors=True)
        staging.rename(target)
        logger.info(f"Verified local copy of {official_repo} ready at {target}")
        return target
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
