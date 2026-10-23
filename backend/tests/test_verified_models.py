"""Fingerprint checks used to accept public copies of gated models (no network needed)."""

import hashlib
import subprocess
from types import SimpleNamespace

from backend import verified_models as vm


def test_git_blob_sha1_matches_git_hash_object(tmp_path):
    f = tmp_path / "modeling.py"
    f.write_bytes(b"print('IndicTrans2')\n")
    expected = subprocess.run(["git", "hash-object", str(f)], capture_output=True, text=True).stdout.strip()
    assert vm._git_blob_sha1(f) == expected


def test_only_byte_identical_files_are_accepted(tmp_path):
    f = tmp_path / "weights.bin"
    f.write_bytes(b"official weights")
    official_lfs = SimpleNamespace(lfs=SimpleNamespace(sha256=hashlib.sha256(b"official weights").hexdigest()), blob_id=None)
    assert vm._matches(f, official_lfs)
    f.write_bytes(b"fine-tuned weights")
    assert not vm._matches(f, official_lfs)

    small = tmp_path / "config.json"
    small.write_bytes(b"{}")
    official_git = SimpleNamespace(lfs=None, blob_id=vm._git_blob_sha1(small))
    assert vm._matches(small, official_git)
    small.write_bytes(b"{ }")
    assert not vm._matches(small, official_git)


def test_unknown_official_repo_has_no_public_copy():
    assert vm.can_assemble("ai4bharat/indictrans2-indic-en-dist-200M")
    assert not vm.can_assemble("ai4bharat/indictrans2-indic-indic-dist-320M")
