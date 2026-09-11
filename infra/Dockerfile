# GAUNTLET — one image, two roles (SRS 34.3). Build context: repository root.
#   API + dashboard: python -m gauntlet.serve --host 0.0.0.0   (default CMD)
#   worker:          python -m gauntlet.worker.main
# With no DATABASE_URL / REDIS_URL the API runs in single-container mode (SQLite on /data, in-process
# queue, worker inside the API). Point DATABASE_URL at PostgreSQL and REDIS_URL at Redis to split roles.

FROM node:22-slim AS dashboard
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# same origin: the API serves the dashboard, so the client uses relative URLs
ENV VITE_API_BASE_URL=""
RUN npx vite build

FROM python:3.12-slim AS runtime
# espeak-ng: intelligible local fallback voice when no synthesis provider is configured
RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng libsndfile1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 gauntlet
WORKDIR /app
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/gauntlet backend/gauntlet
RUN pip install --no-cache-dir "./backend[storage]"
COPY fixtures fixtures
COPY suites suites
COPY config config
COPY calibration calibration
COPY docs docs
COPY --from=dashboard /web/dist /app/dashboard
ENV GAUNTLET_ROOT=/app \
    GAUNTLET_DATA_DIR=/data \
    GAUNTLET_CACHE_DIR=/data/cache \
    STATIC_DIR=/app/dashboard \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PORT=8000
RUN mkdir -p /data && chown -R gauntlet:gauntlet /data /app
# Runs as root because managed platforms (Render) mount persistent disks root-owned and the SQLite file
# lives on that disk. The unprivileged `gauntlet` user exists for deployments that set `user:` on a
# volume it owns. See DECISIONS D-27.
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/healthz',timeout=4)"
CMD ["sh", "-c", "python -m gauntlet.serve --host 0.0.0.0 --port ${PORT}"]
