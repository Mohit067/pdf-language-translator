"""
Pure-Python port of IndicTransToolkit's IndicProcessor (MIT License, (c) Varun Gumma / AI4Bharat).
Source: https://github.com/VarunGumma/IndicTransToolkit (processor.pyx, v1.1.1)

IndicTrans2 models require this pre/post-processing: language tags on the input,
punctuation/numeral normalization, placeholder protection for URLs/emails/numbers,
and script unification (Indic scripts are transliterated to Devanagari before the
model and back to the target script afterwards).

The upstream package is a Cython extension with no Windows wheels, so this port is
used whenever `IndicTransToolkit` cannot be imported. Unlike upstream, it is
stateless: placeholder maps are returned to the caller instead of being kept in a
shared queue, which makes it safe to call from multiple threads.
"""

from typing import Dict, List, Optional, Tuple

import regex as re
from indicnlp.normalize.indic_normalize import IndicNormalizerFactory
from indicnlp.tokenize import indic_detokenize, indic_tokenize
from indicnlp.transliterate.unicode_transliterate import UnicodeIndicTransliterator
from sacremoses import MosesDetokenizer, MosesPunctNormalizer, MosesTokenizer

FLORES_TO_ISO = {
    "asm_Beng": "as", "awa_Deva": "hi", "ben_Beng": "bn", "bho_Deva": "hi",
    "brx_Deva": "hi", "doi_Deva": "hi", "eng_Latn": "en", "gom_Deva": "kK",
    "gon_Deva": "hi", "guj_Gujr": "gu", "hin_Deva": "hi", "hne_Deva": "hi",
    "kan_Knda": "kn", "kas_Arab": "ur", "kas_Deva": "hi", "kha_Latn": "en",
    "lus_Latn": "en", "mag_Deva": "hi", "mai_Deva": "hi", "mal_Mlym": "ml",
    "mar_Deva": "mr", "mni_Beng": "bn", "mni_Mtei": "hi", "npi_Deva": "ne",
    "ory_Orya": "or", "pan_Guru": "pa", "san_Deva": "hi", "sat_Olck": "or",
    "snd_Arab": "ur", "snd_Deva": "hi", "tam_Taml": "ta", "tel_Telu": "te",
    "urd_Arab": "ur", "unr_Deva": "hi",
}

# Indic/Arabic-Indic digits -> ASCII digits (zero..nine across scripts)
_DIGIT_BLOCKS = [0x09E6, 0x0AE6, 0x0CE6, 0x0966, 0x0660, 0xABF0, 0x0B66, 0x0A66, 0x1C50, 0x06F0, 0x0C66]
_DIGITS_TABLE = {base + i: str(i) for base in _DIGIT_BLOCKS for i in range(10)}

_MULTISPACE = re.compile(r"[ ]{2,}")
_DIGIT_SPACE_PERCENT = re.compile(r"(\d) %")
_DOUBLE_QUOT_PUNC = re.compile(r"\"([,\.]+)")
_DIGIT_NBSP_DIGIT = re.compile(r"(\d) (\d)")
_END_BRACKET_SPACE_PUNC = re.compile(r"\) ([\.!:?;,])")

_URL_PATTERN = re.compile(
    r"\b(?<![\w/.])(?:(?:https?|ftp)://)?(?:(?:[\w-]+\.)+(?!\.))(?:[\w/\-?#&=%.]+)+(?!\.\w+)\b"
)
_NUMERAL_PATTERN = re.compile(
    r"(~?\d+\.?\d*\s?%?\s?-?\s?~?\d+\.?\d*\s?%|~?\d+%|\d+[-\/.,:']\d+[-\/.,:'+]\d+(?:\.\d+)?|\d+[-\/.:'+]\d+(?:\.\d+)?)"
)
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}")
_OTHER_PATTERN = re.compile(r"[A-Za-z0-9]*[#|@]\w+")

_PUNC_REPLACEMENTS = [
    (re.compile(r"\r"), ""),
    (re.compile(r"\(\s*"), "("),
    (re.compile(r"\s*\)"), ")"),
    (re.compile(r"\s:\s?"), ":"),
    (re.compile(r"\s;\s?"), ";"),
    (re.compile(r"[`´‘‚’]"), "'"),
    (re.compile(r"[„“”«»]"), '"'),
    (re.compile(r"[–—]"), "-"),
    (re.compile(r"\.\.\."), "..."),
    (re.compile(r" %"), "%"),
    (re.compile(r"nº "), "nº "),
    (re.compile(r" ºC"), " ºC"),
    (re.compile(r" [?!;]"), lambda m: m.group(0).strip()),
    (re.compile(r", "), ", "),
]

# Ways the model is known to mangle "<ID1>" placeholders in Indic outputs
_INDIC_FAILURE_CASES = [
    "آی ڈی ", "ꯑꯥꯏꯗꯤ", "आईडी", "आई . डी . ", "आई . डी .", "आई. डी. ", "आई. डी.",
    "आय. डी. ", "आय. डी.", "आय . डी . ",
    "आय . डी .आइ . डी . ",  # upstream has a missing comma here; kept for parity
    "आइ . डी .", "आइ. डी. ", "आइ. डी.", "ऐटि", "آئی ڈی ", "ᱟᱭᱰᱤ ᱾", "आयडी", "ऐडि", "आइडि", "ᱟᱭᱰᱤ",
]

_NO_TRANSLITERATION_SCRIPTS = {"Arab", "Aran", "Olck", "Mtei", "Latn"}


class IndicProcessor:
    """Drop-in equivalent of IndicTransToolkit.IndicProcessor(inference=True), stateless."""

    def __init__(self):
        self._en_tok = MosesTokenizer(lang="en")
        self._en_normalizer = MosesPunctNormalizer()
        self._en_detok = MosesDetokenizer(lang="en")
        self._xliterator = UnicodeIndicTransliterator()
        self._normalizers: Dict[str, object] = {}

    def _normalizer(self, iso: str):
        if iso not in self._normalizers:
            self._normalizers[iso] = IndicNormalizerFactory().get_normalizer(iso)
        return self._normalizers[iso]

    @staticmethod
    def _punc_norm(text: str) -> str:
        for pattern, repl in _PUNC_REPLACEMENTS:
            text = pattern.sub(repl, text)
        text = _MULTISPACE.sub(" ", text)
        text = _END_BRACKET_SPACE_PUNC.sub(r")\1", text)
        text = _DIGIT_SPACE_PERCENT.sub(r"\1%", text)
        text = _DOUBLE_QUOT_PUNC.sub(r'\1"', text)
        text = _DIGIT_NBSP_DIGIT.sub(r"\1.\2", text)
        return text.strip()

    @staticmethod
    def _wrap_with_placeholders(text: str) -> Tuple[str, Dict[str, str]]:
        serial_no = 1
        entity_map: Dict[str, str] = {}
        for pattern in (_EMAIL_PATTERN, _URL_PATTERN, _NUMERAL_PATTERN, _OTHER_PATTERN):
            for match in set(pattern.findall(text)):
                if pattern is _URL_PATTERN and len(match.replace(".", "")) < 4:
                    continue
                if pattern is _NUMERAL_PATTERN and len(match.replace(" ", "").replace(".", "").replace(":", "")) < 4:
                    continue
                n = serial_no
                for tag in ("ID", "id"):
                    for fmt in ("<{t}{n}>", "< {t}{n} >", "[{t}{n}]", "[ {t}{n} ]", "[{t} {n}]",
                                "<{t}{n}]", "< {t}{n}]", "<{t}{n} ]"):
                        entity_map[fmt.format(t=tag, n=n)] = match
                for case in _INDIC_FAILURE_CASES:
                    for fmt in ("<{c}{n}>", "< {c}{n} >", "< {c} {n} >", "<{c} {n}]", "< {c} {n} ]",
                                "[{c}{n}]", "[{c} {n}]", "[ {c}{n} ]", "[ {c} {n} ]", "{c} {n}", "{c}{n}"):
                        entity_map[fmt.format(c=case, n=n)] = match
                text = text.replace(match, f"<ID{n}>")
                serial_no += 1
        text = re.sub(r"\s+", " ", text).replace(">/", ">").replace("]/", "]")
        return text, entity_map

    def _preprocess(self, sent: str, src_lang: str, tgt_lang: str) -> Tuple[str, Dict[str, str]]:
        iso = FLORES_TO_ISO.get(src_lang, "hi")
        script = src_lang.split("_")[1]
        sent = self._punc_norm(sent)
        sent = sent.translate(_DIGITS_TABLE)
        sent, entity_map = self._wrap_with_placeholders(sent)

        if iso == "en":
            normed = self._en_normalizer.normalize(sent.strip())
            processed = " ".join(self._en_tok.tokenize(normed, escape=False))
        else:
            normed = self._normalizer(iso).normalize(sent.strip())
            processed = " ".join(indic_tokenize.trivial_tokenize(normed, iso))
            if script not in _NO_TRANSLITERATION_SCRIPTS:
                processed = self._xliterator.transliterate(processed, iso, "hi").replace(" ् ", "्")
        return f"{src_lang} {tgt_lang} {processed.strip()}", entity_map

    def _postprocess(self, sent: str, lang: str, entity_map: Dict[str, str]) -> str:
        lang_code, script = lang.split("_", 1)
        iso = FLORES_TO_ISO.get(lang, "hi")
        if script in ("Arab", "Aran"):
            sent = sent.replace(" ؟", "؟").replace(" ۔", "۔").replace(" ،", "،").replace("ٮ۪", "ؠ")
        if lang_code == "ory":
            sent = sent.replace("ଯ଼", "ୟ")
        for k, v in entity_map.items():
            sent = sent.replace(k, v)
        if lang == "eng_Latn":
            return self._en_detok.detokenize(sent.split(" "))
        xlated = self._xliterator.transliterate(sent, "hi", iso)
        return indic_detokenize.trivial_detokenize(xlated, iso)

    def preprocess(self, batch: List[str], src_lang: str, tgt_lang: str) -> Tuple[List[str], List[Dict[str, str]]]:
        pairs = [self._preprocess(s, src_lang, tgt_lang) for s in batch]
        return [p[0] for p in pairs], [p[1] for p in pairs]

    def postprocess(self, sents: List[str], lang: str, entity_maps: List[Dict[str, str]]) -> List[str]:
        return [self._postprocess(s, lang, m) for s, m in zip(sents, entity_maps)]


class ToolkitProcessorAdapter:
    """Wraps the official (queue-based) IndicTransToolkit processor behind the stateless API.
    Callers must serialize preprocess/postprocess pairs (the agent holds an inference lock)."""

    def __init__(self, ip):
        self._ip = ip

    def preprocess(self, batch: List[str], src_lang: str, tgt_lang: str) -> Tuple[List[str], List[Optional[dict]]]:
        return self._ip.preprocess_batch(batch, src_lang=src_lang, tgt_lang=tgt_lang), [None] * len(batch)

    def postprocess(self, sents: List[str], lang: str, entity_maps) -> List[str]:
        return self._ip.postprocess_batch(sents, lang=lang)


def create_processor():
    """Returns (processor, implementation_name). Prefers the official compiled toolkit."""
    try:
        try:
            from IndicTransToolkit.processor import IndicProcessor as ToolkitIP
        except ImportError:
            from IndicTransToolkit import IndicProcessor as ToolkitIP
        return ToolkitProcessorAdapter(ToolkitIP(inference=True)), "IndicTransToolkit"
    except Exception:
        return IndicProcessor(), "builtin-port"
