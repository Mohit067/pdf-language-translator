"""
Local IndicTrans2 translation engine.

All inference runs on this machine with AI4Bharat IndicTrans2 weights loaded through
Hugging Face transformers. Nothing is sent to external translation services: if the
model cannot be loaded or inference fails, a TranslationError / ModelLoadError with an
actionable message is raised instead of silently returning untranslated text.
"""

import gc
import logging
import os
import re
import sys
import threading
from pathlib import Path
from collections import OrderedDict, deque
from typing import Callable, Dict, List, Optional, Tuple

from backend.config import (
    INDICTRANS2_EN_INDIC_MODEL,
    INDICTRANS2_EN_INDIC_REVISION,
    INDICTRANS2_INDIC_EN_MODEL,
    INDICTRANS2_INDIC_EN_REVISION,
    INDICTRANS2_INDIC_INDIC_MODEL,
    INDICTRANS2_INDIC_INDIC_REVISION,
    MAX_LOADED_MODELS,
    QUANTIZE_CPU_MODELS,
    TORCH_NUM_THREADS,
    TRANSLATION_BATCH_SIZE,
    TRANSLATION_NUM_BEAMS,
    get_lang_code,
)

logger = logging.getLogger("indictrans2_translator")
logging.basicConfig(level=logging.INFO)

ENGLISH = "eng_Latn"
MODEL_MAX_TOKENS = 256          # IndicTrans2 max source/target positions
MAX_SEGMENT_CHARS = 350         # sentences longer than this are split at clause/word boundaries
CACHE_MAX_ENTRIES = 50_000

ProgressCallback = Callable[[int, int], None]


class ModelLoadError(RuntimeError):
    """The local IndicTrans2 model (or its runtime) could not be loaded."""


class TranslationError(RuntimeError):
    """Inference failed for a segment even after retrying with smaller batches."""


# Text with no letters (numbers, dates, currency, symbols) is kept verbatim
_HAS_LETTER = re.compile(r"[^\W\d_]")
_URL_OR_EMAIL_ONLY = re.compile(r"^(?:(?:https?|ftp)://\S+|www\.\S+|[\w.+-]+@[\w-]+\.[\w.-]+)$", re.IGNORECASE)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?।॥۔؟])\s+")
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g", "i.e", "no", "inc",
    "ltd", "co", "corp", "fig", "approx", "dept", "est", "govt", "pvt", "rs", "u.s", "a.m", "p.m",
}


class FairLock:
    """FIFO lock: waiting threads get the lock in arrival order. Used for model inference so parallel
    jobs alternate batch-by-batch (each batch still gets every CPU core) instead of one job starving others."""

    def __init__(self):
        self._mutex = threading.Lock()
        self._waiters: "deque[threading.Event]" = deque()
        self._locked = False

    def __enter__(self):
        with self._mutex:
            if not self._locked and not self._waiters:
                self._locked = True
                return self
            turn = threading.Event()
            self._waiters.append(turn)
        turn.wait()  # ownership is handed over directly by __exit__
        return self

    def __exit__(self, *exc):
        with self._mutex:
            if self._waiters:
                self._waiters.popleft().set()
            else:
                self._locked = False


def use_app_local_vc_runtime() -> Optional[str]:
    """Windows only: current PyTorch needs a newer Visual C++ runtime (incl. vcruntime140_threads.dll)
    than many machines have. The `msvc-runtime` wheel ships Microsoft's runtime DLLs into the venv;
    preloading them lets torch import without an admin install of the redistributable."""
    if sys.platform != "win32":
        return None
    import ctypes
    for d in (Path(sys.prefix) / "Scripts", Path(sys.prefix)):
        if (d / "vcruntime140_threads.dll").exists() and (d / "msvcp140.dll").exists():
            os.add_dll_directory(str(d))
            for name in ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "vcruntime140_threads.dll"):
                if (d / name).exists():
                    ctypes.WinDLL(str(d / name))
            return str(d)
    return None


def needs_translation(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and bool(_HAS_LETTER.search(stripped)) and not _URL_OR_EMAIL_ONLY.match(stripped)


def split_sentences(text: str) -> List[str]:
    """Sentence-split a single line, avoiding breaks after common abbreviations and initials."""
    pieces = _SENTENCE_BOUNDARY.split(text.strip())
    sentences: List[str] = []
    for piece in pieces:
        if sentences:
            last_word = sentences[-1].rsplit(None, 1)[-1].rstrip(".").lower()
            if last_word in _ABBREVIATIONS or (len(last_word) == 1 and last_word.isalpha()):
                sentences[-1] = f"{sentences[-1]} {piece}"
                continue
        sentences.append(piece)
    result: List[str] = []
    for s in sentences:
        result.extend(_split_long(s))
    return [s for s in result if s.strip()]


def _split_long(sentence: str, limit: int = MAX_SEGMENT_CHARS) -> List[str]:
    """Split an over-long sentence at clause punctuation, then at word boundaries."""
    if len(sentence) <= limit:
        return [sentence]
    for sep in ("; ", ": ", ", "):
        parts = sentence.split(sep)
        if len(parts) > 1:
            chunks, current = [], ""
            for i, part in enumerate(parts):
                piece = part + (sep.rstrip() if i < len(parts) - 1 else "")
                if current and len(current) + len(piece) + 1 > limit:
                    chunks.append(current)
                    current = piece
                else:
                    current = f"{current} {piece}".strip()
            chunks.append(current)
            if all(len(c) <= limit for c in chunks):
                return chunks
            return [sub for c in chunks for sub in _split_long(c, limit)]
    words, chunks, current = sentence.split(), [], ""
    for word in words:
        if current and len(current) + len(word) + 1 > limit:
            chunks.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        chunks.append(current)
    return chunks


def model_direction(src_code: str, tgt_code: str) -> str:
    if src_code == ENGLISH:
        return "en-indic"
    if tgt_code == ENGLISH:
        return "indic-en"
    return "indic-indic"


MODEL_NAMES = {
    "en-indic": INDICTRANS2_EN_INDIC_MODEL,
    "indic-en": INDICTRANS2_INDIC_EN_MODEL,
    "indic-indic": INDICTRANS2_INDIC_INDIC_MODEL,
}
MODEL_REVISIONS = {
    "en-indic": INDICTRANS2_EN_INDIC_REVISION,
    "indic-en": INDICTRANS2_INDIC_EN_REVISION,
    "indic-indic": INDICTRANS2_INDIC_INDIC_REVISION,
}


class IndicTrans2Agent:
    """Lazily loads one IndicTrans2 model per direction and runs batched local inference."""

    def __init__(self):
        self.device = "cpu"
        self._models: "OrderedDict[str, Tuple[object, object]]" = OrderedDict()
        self._load_errors: Dict[str, str] = {}
        self._torch_error: Optional[str] = None
        self._processor = None
        self.processor_impl: Optional[str] = None
        self._load_lock = threading.RLock()   # model loading / eviction
        self._infer_lock = FairLock()         # one batch at a time, fair across parallel jobs
        self._cache: "OrderedDict[Tuple[str, str, str], str]" = OrderedDict()
        self._cache_lock = threading.Lock()   # the LRU cache is shared by parallel jobs
        # Per-direction KV-cache use; disabled if the transformers version is incompatible with the model code
        self._use_kv_cache: Dict[str, bool] = {}

    # ------------------------------------------------------------------ status
    @property
    def neural_available(self) -> bool:
        return bool(self._models)

    def status(self) -> Dict[str, object]:
        return {
            "device": self.device,
            "loaded_models": {d: MODEL_NAMES[d] for d in self._models},
            "configured_models": dict(MODEL_NAMES),
            "processor": self.processor_impl,
            "torch_error": self._torch_error,
            "load_errors": dict(self._load_errors),
            "batch_size": TRANSLATION_BATCH_SIZE,
            "num_beams": TRANSLATION_NUM_BEAMS,
            "kv_cache_disabled": [d for d, on in self._use_kv_cache.items() if not on],
        }

    # ------------------------------------------------------------------ loading
    def _import_torch(self):
        try:
            if "torch" not in sys.modules:
                runtime_dir = use_app_local_vc_runtime()
                if runtime_dir:
                    logger.info(f"Using app-local Visual C++ runtime from {runtime_dir}")
            import torch
        except Exception as e:  # OSError on Windows when the VC++ runtime is too old
            hint = ""
            if isinstance(e, OSError) and "dll" in str(e).lower():
                hint = (" On Windows this means the Visual C++ runtime is too old: run `pip install msvc-runtime` "
                        "in the backend venv (no admin needed), or install the latest redistributable from "
                        "https://aka.ms/vs/17/release/vc_redist.x64.exe.")
            self._torch_error = f"PyTorch could not be loaded: {e}.{hint}"
            raise ModelLoadError(self._torch_error) from e
        self._torch_error = None
        if TORCH_NUM_THREADS > 0:
            torch.set_num_threads(TORCH_NUM_THREADS)
        return torch

    def _cache_get(self, key: Tuple[str, str, str]) -> Optional[str]:
        with self._cache_lock:
            value = self._cache.get(key)
            if value is not None:
                self._cache.move_to_end(key)
            return value

    def _cache_put(self, src_code: str, tgt_code: str, pairs: Dict[str, str]) -> None:
        with self._cache_lock:
            for src, out in pairs.items():
                self._cache[(src_code, tgt_code, src)] = out
            while len(self._cache) > CACHE_MAX_ENTRIES:
                self._cache.popitem(last=False)

    def _get_processor(self):
        with self._load_lock:
            if self._processor is not None:
                return self._processor
            from backend.indic_processor import create_processor
            self._processor, self.processor_impl = create_processor()
            logger.info(f"IndicTrans2 pre/post-processor: {self.processor_impl}")
        return self._processor

    def load_model(self, direction: str):
        """Returns (tokenizer, model) for a direction, loading it (and evicting LRU models) if needed."""
        with self._load_lock:
            if direction in self._models:
                self._models.move_to_end(direction)
                return self._models[direction]

            torch = self._import_torch()
            import transformers
            from packaging.version import Version
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            # transformers renamed `torch_dtype` to `dtype` in 4.56
            dtype_kw = "dtype" if Version(transformers.__version__) >= Version("4.56") else "torch_dtype"
            name = MODEL_NAMES[direction]
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            while len(self._models) >= MAX_LOADED_MODELS:
                evicted, _ = self._models.popitem(last=False)
                logger.info(f"Unloading model for {evicted} to stay within MAX_LOADED_MODELS={MAX_LOADED_MODELS}")
                gc.collect()
                if self.device == "cuda":
                    torch.cuda.empty_cache()

            revision = MODEL_REVISIONS.get(direction)
            logger.info(f"Loading IndicTrans2 {direction} model '{name}'"
                        f"{f' @ {revision[:10]}' if revision else ''} on {self.device}...")
            try:
                tokenizer = AutoTokenizer.from_pretrained(name, revision=revision, trust_remote_code=True)
                model = AutoModelForSeq2SeqLM.from_pretrained(
                    name,
                    revision=revision,
                    trust_remote_code=True,
                    **{dtype_kw: torch.float16 if self.device == "cuda" else torch.float32},
                ).to(self.device)
            except Exception as e:
                message = self._explain_load_error(name, e)
                self._load_errors[direction] = message
                logger.error(message)
                raise ModelLoadError(message) from e

            model.eval()
            if QUANTIZE_CPU_MODELS and self.device == "cpu":
                model = torch.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
                logger.info("Applied dynamic int8 quantization to linear layers")
            self._load_errors.pop(direction, None)
            self._models[direction] = (tokenizer, model)
            self._get_processor()
            logger.info(f"IndicTrans2 {direction} model ready.")
            return tokenizer, model

    @staticmethod
    def _explain_load_error(name: str, e: Exception) -> str:
        text = f"{type(e).__name__}: {e}"
        if "gated" in text.lower() or "403" in text or "401" in text:
            return (f"Model '{name}' is gated on Hugging Face and this machine has no access. Request access at "
                    f"https://huggingface.co/{name}, then run `huggingface-cli login` (or set HF_TOKEN) once to "
                    f"download the weights. Inference afterwards runs fully offline.")
        if any(k in text.lower() for k in ("connection", "resolve", "offline", "timed out", "couldn't connect")):
            return (f"Could not download model '{name}' (no network?). Connect once to cache the weights, or point "
                    f"the INDICTRANS2_*_MODEL setting to a local directory containing them. Details: {text}")
        return f"Failed to load model '{name}': {text}"

    # ------------------------------------------------------------------ inference
    def _decode(self, tokenizer, generated) -> List[str]:
        kwargs = dict(skip_special_tokens=True, clean_up_tokenization_spaces=True)
        as_target = getattr(tokenizer, "as_target_tokenizer", None)
        if callable(as_target):
            with as_target():
                return tokenizer.batch_decode(generated, **kwargs)
        to_target = getattr(tokenizer, "_switch_to_target_mode", None)
        to_input = getattr(tokenizer, "_switch_to_input_mode", None)
        if callable(to_target) and callable(to_input):
            to_target()
            try:
                return tokenizer.batch_decode(generated, **kwargs)
            finally:
                to_input()
        return tokenizer.batch_decode(generated, **kwargs)

    def _infer(self, sentences: List[str], src_code: str, tgt_code: str, direction: str) -> List[str]:
        torch = self._import_torch()
        tokenizer, model = self.load_model(direction)
        processor = self._get_processor()
        with self._infer_lock:
            preprocessed, entity_maps = processor.preprocess(sentences, src_code, tgt_code)
            inputs = tokenizer(
                preprocessed,
                truncation=True,
                padding="longest",
                max_length=MODEL_MAX_TOKENS,
                return_tensors="pt",
                return_attention_mask=True,
            ).to(self.device)
            if int(inputs["attention_mask"].sum(dim=1).max()) >= MODEL_MAX_TOKENS:
                logger.warning("A segment reached the 256-token model limit and was truncated.")
            with torch.inference_mode():
                generated = model.generate(
                    **inputs,
                    use_cache=self._use_kv_cache.get(direction, True),
                    min_length=0,
                    max_length=MODEL_MAX_TOKENS,
                    num_beams=TRANSLATION_NUM_BEAMS,
                    num_return_sequences=1,
                )
            decoded = self._decode(tokenizer, generated)
            return processor.postprocess(decoded, tgt_code, entity_maps)

    def _infer_with_retry(self, sentences: List[str], src_code: str, tgt_code: str, direction: str) -> List[str]:
        """Runs a batch; on memory/runtime errors retries in halves so one bad batch doesn't fail the job."""
        try:
            return self._infer(sentences, src_code, tgt_code, direction)
        except ModelLoadError:
            raise
        except (AttributeError, KeyError) as e:
            # Newer transformers pass Cache objects the IndicTrans2 remote code cannot read; decoding
            # without the KV-cache is slower but correct, so switch once and retry the same batch.
            if ("shape" in str(e) or "Cache only has" in str(e)) and self._use_kv_cache.get(direction, True):
                logger.warning(f"KV-cache incompatible with installed transformers ({e}); "
                               f"disabling it for {direction}. Install transformers<4.47 for full speed.")
                self._use_kv_cache[direction] = False
                return self._infer_with_retry(sentences, src_code, tgt_code, direction)
            if len(sentences) == 1:
                raise TranslationError(f"Local model failed to translate a segment ({type(e).__name__}: {e})") from e
            return self._split_retry(sentences, src_code, tgt_code, direction, e)
        except Exception as e:
            if len(sentences) == 1:
                raise TranslationError(f"Local model failed to translate a segment ({type(e).__name__}: {e})") from e
            return self._split_retry(sentences, src_code, tgt_code, direction, e)

    def _split_retry(self, sentences: List[str], src_code: str, tgt_code: str, direction: str, error: Exception) -> List[str]:
        logger.warning(f"Batch of {len(sentences)} failed ({error}); retrying in smaller batches")
        gc.collect()
        mid = len(sentences) // 2
        return (self._infer_with_retry(sentences[:mid], src_code, tgt_code, direction)
                + self._infer_with_retry(sentences[mid:], src_code, tgt_code, direction))

    def _translate_sentences(
        self,
        sentences: List[str],
        src_code: str,
        tgt_code: str,
        progress: Optional[ProgressCallback] = None,
        progress_offset: int = 0,
        progress_total: Optional[int] = None,
        known: Optional[Dict[str, str]] = None,
        on_batch: Optional[Callable[[Dict[str, str]], None]] = None,
    ) -> Dict[str, str]:
        """Translates unique sentences (cache-aware, length-sorted batches). Returns sentence -> translation.
        `known` holds translations already finished (e.g. a resumed job's checkpoint); `on_batch` receives
        each newly translated batch so callers can checkpoint progress."""
        results: Dict[str, str] = {}
        pending: List[str] = []
        for s in dict.fromkeys(sentences):
            key = (src_code, tgt_code, s)
            if known and s in known:
                results[s] = known[s]
            elif self._cache_get(key) is not None:
                results[s] = self._cache_get(key)
            else:
                pending.append(s)

        total = progress_total if progress_total is not None else len(pending)
        if progress_total is not None:
            progress_offset += len(results)  # cache hits count as done
        if not pending:
            return results

        direction = model_direction(src_code, tgt_code)
        if direction == "indic-indic":
            try:
                self.load_model(direction)
            except ModelLoadError as e:
                logger.warning(f"Indic-Indic model unavailable ({e}); pivoting through English")
                pivoted = self._pivot(pending, src_code, tgt_code, progress, progress_offset, total)
                if on_batch:
                    on_batch(pivoted)
                return {**results, **pivoted}

        pending.sort(key=len)  # similar lengths per batch -> less padding, faster generation
        done = 0
        for i in range(0, len(pending), TRANSLATION_BATCH_SIZE):
            batch = pending[i:i + TRANSLATION_BATCH_SIZE]
            batch_results: Dict[str, str] = {}
            for src, out in zip(batch, self._infer_with_retry(batch, src_code, tgt_code, direction)):
                out = out.strip()
                if not out:
                    raise TranslationError(f"Local model returned an empty translation for: {src[:80]!r}")
                batch_results[src] = out
            self._cache_put(src_code, tgt_code, batch_results)
            results.update(batch_results)
            if on_batch:
                on_batch(batch_results)
            done += len(batch)
            if progress:
                progress(progress_offset + done, total)
        return results

    def _pivot(self, sentences, src_code, tgt_code, progress, offset, total) -> Dict[str, str]:
        half = lambda done, _t: progress(offset + done // 2, total) if progress else None
        to_en = self._translate_sentences(sentences, src_code, ENGLISH, half)
        english = [to_en[s] for s in sentences]
        second = lambda done, _t: progress(offset + (len(sentences) + done) // 2, total) if progress else None
        from_en = self._translate_sentences(english, ENGLISH, tgt_code, second)
        return {s: from_en[e] for s, e in zip(sentences, english)}

    # ------------------------------------------------------------------ public API
    def translate_texts(
        self,
        texts: List[str],
        source_lang: str,
        target_lang: str,
        progress: Optional[ProgressCallback] = None,
        known: Optional[Dict[str, str]] = None,
        on_batch: Optional[Callable[[Dict[str, str]], None]] = None,
    ) -> List[str]:
        """Translates a list of texts, returning one translation per input (same order, same length).
        Line breaks, blank lines and indentation are preserved; text without letters is kept verbatim.
        `known`/`on_batch` support checkpointing (see _translate_sentences)."""
        src_code, tgt_code = get_lang_code(source_lang), get_lang_code(target_lang)
        if src_code == tgt_code:
            raise ValueError("Source and target languages must be different.")

        # Plan: text -> lines -> sentences
        plans: List[List[Tuple[str, str, Optional[List[str]]]]] = []
        all_sentences: List[str] = []
        for text in texts:
            line_plans = []
            for line in (text or "").split("\n"):
                stripped = line.strip()
                if not needs_translation(stripped):
                    line_plans.append((line, "", None))
                    continue
                indent = line[: len(line) - len(line.lstrip())]
                sentences = [s for s in split_sentences(stripped) if needs_translation(s)] or [stripped]
                all_sentences.extend(sentences)
                line_plans.append((stripped, indent, sentences))
            plans.append(line_plans)

        unique = dict.fromkeys(all_sentences)
        unique_count = len(unique)
        if progress:  # a resumed job starts from what its checkpoint already has
            progress(sum(1 for s in unique if known and s in known), unique_count)
        translated = self._translate_sentences(all_sentences, src_code, tgt_code, progress, 0, unique_count,
                                               known=known, on_batch=on_batch)

        outputs: List[str] = []
        for line_plans in plans:
            lines = []
            for original, indent, sentences in line_plans:
                lines.append(original if sentences is None else indent + " ".join(translated[s] for s in sentences))
            outputs.append("\n".join(lines))
        return outputs

    def translate_chunk(self, text: str, source_lang: str, target_lang: str, tone: str = "Professional") -> str:
        """Translates a single (possibly multi-line) block of text."""
        return self.translate_texts([text], source_lang, target_lang)[0]


# Singleton instance (models load lazily on first use)
agent = IndicTrans2Agent()
