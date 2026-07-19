FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

RUN python -m pip install --upgrade pip \
    && python -m pip install ".[audio]" \
    && apt-get update \
    && apt-get install --yes --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser

CMD ["sh", "-c", "mkdir -p /data/b2-speaking-storage && chown -R appuser:appuser /data && exec gosu appuser python -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
