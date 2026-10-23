# ===============================================================
# Optimized Backend Dockerfile for TransDoc (FastAPI + AI4Bharat)
# Python 3.11 slim + PyTorch CPU, installed with uv and BuildKit caches
# ===============================================================

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    HF_HOME=/root/.cache/huggingface \
    UV_LINK_MODE=copy \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

# uv resolves and installs wheels many times faster than pip
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install "uv>=0.5,<1"

# 1. PyTorch CPU in its own layer: the ~200 MB download is reused even when requirements.txt changes
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install torch --index-url https://download.pytorch.org/whl/cpu

# 2. Remaining dependencies (torch is already satisfied, so it is not re-resolved)
COPY requirements.txt /app/backend/requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -r /app/backend/requirements.txt

# 3. Backend source last, so code edits only rebuild this small layer
COPY . /app/backend/

RUN mkdir -p /app/backend/storage/uploads /app/backend/storage/outputs

EXPOSE 8000

# Health check with Python's stdlib (no apt-get/curl layer needed)
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --start-interval=2s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=4)"

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
