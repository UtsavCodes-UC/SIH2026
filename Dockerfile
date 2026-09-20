# One image, one port: the backend serves the built UI itself (see the end of backend/app/main.py).
#
#   docker compose up --build        # then open http://localhost:8000
#
# Layers are ordered so that a UI-only change rebuilds in seconds: the npm and pip installs are cached
# and only the source copy + `npm run build` (and the final copy of dist/) run again.

# ---- 1. build the UI ------------------------------------------------------------------------
FROM node:20-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2. the app -----------------------------------------------------------------------------
FROM python:3.11-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# main.py looks for the UI at <two levels above app/>/frontend/dist, i.e. /app/frontend/dist
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/ ./
COPY --from=ui /ui/dist /app/frontend/dist

# Downloaded maps and recorded traffic live here; docker-compose.yml mounts them from the host so they survive rebuilds.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p data/cache data/traffic_snapshots \
    && chown -R app:app /app
USER app

# The port comes from $PORT when the host sets one (Google Cloud Run, Render and similar do); 8000 otherwise.
# WARM_PRESETS=1 loads the four preset cities in the background at start-up, so a slow host does not make the first visitor wait.
ENV PORT=8000 \
    WARM_PRESETS=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '8000'), timeout=4)"]

# One worker on purpose: loaded maps and their traffic are kept in this process's memory (services/graph_store.py).
# `exec` makes uvicorn the main process, so it receives the stop signal and shuts down cleanly.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
