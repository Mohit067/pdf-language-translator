"""Parsing, segmentation and pre/post-processing tests (no model required)."""

import io

import docx
import pymupdf
import pytest

from backend.agent_pipeline import needs_translation, split_sentences, model_direction
from backend.config import get_lang_code, resolve_lang_code
from backend.document_processors import (
    DocumentError,
    _extract_pdf_units,
    _iter_docx_paragraphs,
    _own_text_elements,
    _read_text_file,
)
from backend.indic_processor import IndicProcessor
from tests.conftest import make_docx, make_pdf


def test_language_resolution_is_strict():
    assert get_lang_code("Hindi") == "hin_Deva"
    assert get_lang_code("தமிழ்") == "tam_Taml"
    assert get_lang_code("kok_Deva") == "gom_Deva"  # legacy code maps to the real IndicTrans2 tag
    assert resolve_lang_code("Spanish") is None
    with pytest.raises(ValueError):
        get_lang_code("Klingon")


def test_model_direction():
    assert model_direction("eng_Latn", "hin_Deva") == "en-indic"
    assert model_direction("tam_Taml", "eng_Latn") == "indic-en"
    assert model_direction("tam_Taml", "hin_Deva") == "indic-indic"


def test_sentence_split_keeps_abbreviations_and_limits_length():
    assert split_sentences("Dr. Rao met Mr. Singh. They agreed!") == ["Dr. Rao met Mr. Singh.", "They agreed!"]
    assert split_sentences("यह पहला वाक्य है। यह दूसरा है।") == ["यह पहला वाक्य है।", "यह दूसरा है।"]
    long = ", ".join(["the committee reviewed every detailed item"] * 20)
    parts = split_sentences(long)
    assert len(parts) > 1 and all(len(p) <= 350 for p in parts)
    assert " ".join(parts).replace(" ,", ",").split() == long.split()


@pytest.mark.parametrize("text,expected", [
    ("Invoice total", True), ("12,500.00", False), ("24/10/2026", False),
    ("https://example.com/a", False), ("a@b.com", False), ("₹ 4,500", False), ("   ", False),
])
def test_needs_translation(text, expected):
    assert needs_translation(text) is expected


def test_processor_port_tags_protects_entities_and_round_trips_script():
    p = IndicProcessor()
    pre, maps = p.preprocess(["Email a@b.com by 24/10/2026."], "eng_Latn", "tam_Taml")
    assert pre[0].startswith("eng_Latn tam_Taml ")
    assert "a@b.com" not in pre[0] and "24/10/2026" not in pre[0]
    # Model output is script-unified Devanagari; postprocess restores entities and Tamil script
    out = p.postprocess(["नमस्ते <ID1> <ID2>"], "tam_Taml", maps)[0]
    assert "a@b.com" in out and "24/10/2026" in out
    assert any("஀" <= ch <= "௿" for ch in out)
    # Indic source in a non-Devanagari script is transliterated to Devanagari for the model
    pre2, _ = p.preprocess(["வணக்கம்"], "tam_Taml", "eng_Latn")
    assert pre2[0].startswith("tam_Taml eng_Latn ") and any("ऀ" <= ch <= "ॿ" for ch in pre2[0])


def test_pdf_units_group_paragraphs_and_keep_lines_separate():
    doc = pymupdf.open(stream=make_pdf(), filetype="pdf")
    units = _extract_pdf_units(doc[0])
    texts = [u.text for u in units]
    assert "Quarterly Business Report" in texts
    assert any(t.startswith("The company expanded") and t.endswith("this quarter.") for t in texts)
    assert "Total amount" in texts and "4,500.00" in texts  # far-apart spans become separate units


def test_docx_iteration_visits_merged_cells_once_and_includes_header():
    d = docx.Document(io.BytesIO(make_docx()))
    texts = ["".join(t.text for t in _own_text_elements(p)) for p in _iter_docx_paragraphs(d)]
    assert texts.count("Customer feedback") == 1      # merged cell appears twice in row.cells
    assert "Confidential company report" in texts      # header
    assert "The project was completed on time and within budget." in texts


def test_text_decoding_handles_bom_utf16_and_cp1252(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes("﻿hello\r\nworld".encode("utf-8"))
    assert _read_text_file(f) == ("hello\nworld", True, "\r\n")
    f.write_bytes("café नमस्ते".encode("utf-16"))
    assert _read_text_file(f)[0] == "café नमस्ते"
    f.write_bytes("caf\xe9 \x93quoted\x94".encode("latin-1"))
    assert _read_text_file(f)[0] == "café “quoted”"
    f.write_bytes(b"PK\x03\x04\x00\x00binary")
    with pytest.raises(DocumentError):
        _read_text_file(f)
