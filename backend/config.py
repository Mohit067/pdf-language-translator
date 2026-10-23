import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(ROOT_DIR / ".env")

STORAGE_DIR = BACKEND_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
OUTPUTS_DIR = STORAGE_DIR / "outputs"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# IndicTrans2 AI4Bharat Model Configuration (HF repo ids or local directories with the weights).
# The official ai4bharat repos are gated (one-time, auto-approved "Agree and access" on Hugging Face).
# en->indic defaults to a public copy verified byte-identical to the official repo (every file, incl.
# the 1.1 GB weights and the remote Python code), pinned to that verified commit, so it needs no token.
_VERIFIED_EN_INDIC = ("naklitechie/indictrans2-en-indic-dist-200M", "a814dab1ae6e4ee4c7d785b7e1dcb0ac8e36bcd6")

INDICTRANS2_EN_INDIC_MODEL = os.getenv("INDICTRANS2_EN_INDIC_MODEL") or _VERIFIED_EN_INDIC[0]
INDICTRANS2_INDIC_EN_MODEL = os.getenv("INDICTRANS2_INDIC_EN_MODEL") or "ai4bharat/indictrans2-indic-en-dist-200M"
INDICTRANS2_INDIC_INDIC_MODEL = os.getenv("INDICTRANS2_INDIC_INDIC_MODEL") or "ai4bharat/indictrans2-indic-indic-dist-320M"
# Commit pins (strongly recommended for any non-ai4bharat repo: the model runs remote code)
INDICTRANS2_EN_INDIC_REVISION = os.getenv("INDICTRANS2_EN_INDIC_REVISION") or (
    _VERIFIED_EN_INDIC[1] if INDICTRANS2_EN_INDIC_MODEL == _VERIFIED_EN_INDIC[0] else None)
INDICTRANS2_INDIC_EN_REVISION = os.getenv("INDICTRANS2_INDIC_EN_REVISION") or None
INDICTRANS2_INDIC_INDIC_REVISION = os.getenv("INDICTRANS2_INDIC_INDIC_REVISION") or None

# Local inference tuning
TRANSLATION_BATCH_SIZE = max(1, _env_int("TRANSLATION_BATCH_SIZE", 8))   # sentences per forward pass
TRANSLATION_NUM_BEAMS = max(1, _env_int("TRANSLATION_NUM_BEAMS", 4))     # 1 = greedy (fastest)
TORCH_NUM_THREADS = _env_int("TORCH_NUM_THREADS", 0)                     # 0 = torch default
MAX_LOADED_MODELS = max(1, _env_int("MAX_LOADED_MODELS", 2))             # LRU-evict beyond this
QUANTIZE_CPU_MODELS = os.getenv("QUANTIZE_CPU_MODELS", "0").lower() in ("1", "true", "yes")
# Documents processed at the same time. Model inference takes fair turns batch-by-batch, so all
# running documents advance together without oversubscribing the CPU.
MAX_PARALLEL_JOBS = max(1, _env_int("MAX_PARALLEL_JOBS", 4))
PRELOAD_MODELS = [d.strip() for d in os.getenv("PRELOAD_MODELS", "").split(",")
                  if d.strip() in ("en-indic", "indic-en", "indic-indic")]

# Upload / storage limits
MAX_UPLOAD_MB = max(1, _env_int("MAX_UPLOAD_MB", 50))
MAX_PDF_PAGES = max(1, _env_int("MAX_PDF_PAGES", 300))
JOB_TTL_HOURS = max(1, _env_int("JOB_TTL_HOURS", 24))

SUPPORTED_EXTENSIONS = [".pdf", ".xlsx", ".xls", ".docx", ".txt", ".csv", ".md"]

# IndicTrans2 Language Codes (Flores-200 / BCP-47 script tags)
INDIC_LANGUAGES = [
    {"code": "hin_Deva", "name": "Hindi", "native": "हिन्दी", "flag": "🇮🇳"},
    {"code": "eng_Latn", "name": "English", "native": "English", "flag": "🇬🇧"},
    {"code": "ben_Beng", "name": "Bengali", "native": "বাংলা", "flag": "🇮🇳"},
    {"code": "tam_Taml", "name": "Tamil", "native": "தமிழ்", "flag": "🇮🇳"},
    {"code": "tel_Telu", "name": "Telugu", "native": "తెలుగు", "flag": "🇮🇳"},
    {"code": "mar_Deva", "name": "Marathi", "native": "मराठी", "flag": "🇮🇳"},
    {"code": "guj_Gujr", "name": "Gujarati", "native": "ગુજરાતી", "flag": "🇮🇳"},
    {"code": "kan_Knda", "name": "Kannada", "native": "ಕನ್ನಡ", "flag": "🇮🇳"},
    {"code": "mal_Mlym", "name": "Malayalam", "native": "മലയാളം", "flag": "🇮🇳"},
    {"code": "pan_Guru", "name": "Punjabi", "native": "ਪੰਜਾਬੀ", "flag": "🇮🇳"},
    {"code": "ory_Orya", "name": "Odia", "native": "ଓଡ଼ିଆ", "flag": "🇮🇳"},
    {"code": "urd_Arab", "name": "Urdu", "native": "اردو", "flag": "🇵🇰"},
    {"code": "asm_Beng", "name": "Assamese", "native": "অসমীয়া", "flag": "🇮🇳"},
    {"code": "san_Deva", "name": "Sanskrit", "native": "संस्कृतम्", "flag": "🇮🇳"},
    {"code": "mai_Deva", "name": "Maithili", "native": "मैथिली", "flag": "🇮🇳"},
    {"code": "npi_Deva", "name": "Nepali", "native": "नेपाली", "flag": "🇳🇵"},
    {"code": "gom_Deva", "name": "Konkani", "native": "कोंकणी", "flag": "🇮🇳"},
    {"code": "snd_Arab", "name": "Sindhi", "native": "سنڌي", "flag": "🇵🇰"},
    {"code": "kas_Arab", "name": "Kashmiri", "native": "كٲشُر", "flag": "🇮🇳"},
    {"code": "doi_Deva", "name": "Dogri", "native": "डोगरी", "flag": "🇮🇳"},
    {"code": "brx_Deva", "name": "Bodo", "native": "बड़ो", "flag": "🇮🇳"},
    {"code": "sat_Olck", "name": "Santali", "native": "ᱥᱟᱱᱛᱟᱲᱤ", "flag": "🇮🇳"},
]

# Legacy / ISO aliases. Konkani and Dogri were previously listed as kok_Deva / dgo_Deva,
# which are not IndicTrans2 tags (the model uses gom_Deva / doi_Deva).
_ALIASES = {
    "hi": "hin_Deva", "en": "eng_Latn", "bn": "ben_Beng", "ta": "tam_Taml", "te": "tel_Telu",
    "mr": "mar_Deva", "gu": "guj_Gujr", "kn": "kan_Knda", "ml": "mal_Mlym", "pa": "pan_Guru",
    "or": "ory_Orya", "ur": "urd_Arab", "as": "asm_Beng", "sa": "san_Deva", "ne": "npi_Deva",
    "kok_deva": "gom_Deva", "dgo_deva": "doi_Deva", "oriya": "ory_Orya", "panjabi": "pan_Guru",
}

RTL_LANG_CODES = {"urd_Arab", "snd_Arab", "kas_Arab"}


def resolve_lang_code(lang_str: Optional[str]) -> Optional[str]:
    """Resolve a language name / native name / IndicTrans2 code to an IndicTrans2 code, or None."""
    if not lang_str:
        return None
    cleaned = lang_str.lower().strip()
    for l in INDIC_LANGUAGES:
        if cleaned in (l["name"].lower(), l["code"].lower(), l["native"].lower()):
            return l["code"]
    return _ALIASES.get(cleaned)


def get_lang_code(lang_str: str) -> str:
    """Resolve plain language name to IndicTrans2 code; raises ValueError for unsupported languages."""
    code = resolve_lang_code(lang_str)
    if code is None:
        supported = ", ".join(l["name"] for l in INDIC_LANGUAGES)
        raise ValueError(f"Unsupported language '{lang_str}'. Supported: {supported}")
    return code


def get_lang_name(code: str) -> str:
    for l in INDIC_LANGUAGES:
        if l["code"] == code:
            return l["name"]
    return code
