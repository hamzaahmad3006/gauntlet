# GAUNTLET on Hugging Face Spaces (Docker SDK). Same image as infra/Dockerfile with the platform's rules:
# the container listens on 7860, runs as uid 1000, and writes only where that user may write, because a
# free Space has no persistent disk. Runs are therefore kept in SQLite under /tmp and are lost on a restart;
# the workspace reseeds itself with the bundled agents and suite on the next sign-in.

FROM node:22-slim AS dashboard
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ENV VITE_API_BASE_URL=""
RUN npx vite build

FROM python:3.12-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng libsndfile1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 1000 user
WORKDIR /app
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/gauntlet backend/gauntlet
RUN pip install --no-cache-dir "./backend[storage]"
COPY fixtures fixtures
COPY suites suites
COPY config config
COPY calibration calibration
COPY benchmarks benchmarks
COPY docs docs
COPY --from=dashboard /web/dist /app/dashboard
ENV GAUNTLET_ROOT=/app \
    GAUNTLET_DATA_DIR=/tmp/gauntlet \
    GAUNTLET_CACHE_DIR=/tmp/gauntlet/cache \
    STATIC_DIR=/app/dashboard \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    ENVIRONMENT=production \
    ALLOW_GUEST=true \
    MAX_CALLS_PER_WORKER=2 \
    MAX_CONCURRENT_CALLS=2 \
    CALLER_LLM_TIMEOUT_MS=1200
RUN mkdir -p /tmp/gauntlet && chown -R user:user /tmp/gauntlet /app
USER user
EXPOSE 7860
CMD ["sh", "-c", "python -m gauntlet.serve --host 0.0.0.0 --port ${PORT}"]
