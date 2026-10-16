# TrustScore API — standalone container (Render / Railway / Fly / local).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build deps for LightGBM / psycopg2 wheels are shipped as manylinux wheels, so
# no compiler is needed on slim. libgomp is required by LightGBM at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# App code + the bundled model artifact.
COPY app ./app
COPY index.py ./index.py
COPY artifacts ./artifacts

ENV STORAGE_BACKEND=auto \
    LOG_PREDICTIONS=true \
    ENABLE_DOCS=true

EXPOSE 8000

# Render/Railway provide $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
