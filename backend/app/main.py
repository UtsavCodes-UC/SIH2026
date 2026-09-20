import mimetypes
import os
import threading
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import benchmark, graph, optimize, shortest_path, traffic
from app.core.vrp_formulation import UnreachableStopError
from app.data.osm_loader import CityLoadError, UnusablePlaceError, warm_presets
from app.data.tomtom import TrafficProviderError
from app.services.live_traffic_service import TrafficRequestError, TrafficUnavailableError
from app.services.problem_builder import InvalidProblemError
from app.services.snapshots import SnapshotNotFound

app = FastAPI(
    title="SIH26137 — Quantum-Inspired Traffic Route Optimization",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(InvalidProblemError)
@app.exception_handler(UnreachableStopError)
@app.exception_handler(TrafficRequestError)
@app.exception_handler(UnusablePlaceError)
async def unprocessable(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(CityLoadError)
@app.exception_handler(TrafficUnavailableError)
async def unavailable(_: Request, exc: RuntimeError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(TrafficProviderError)
async def provider_failed(_: Request, exc: TrafficProviderError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(SnapshotNotFound)
async def snapshot_missing(_: Request, exc: SnapshotNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": f"unknown snapshot {exc.args[0]!r}"})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


api = APIRouter(prefix="/api")
api.include_router(graph.router)
api.include_router(optimize.router)
api.include_router(benchmark.router)
api.include_router(shortest_path.router)
api.include_router(traffic.router)


@api.get("/health")
def api_health() -> dict:
    return {"status": "ok"}


app.include_router(api)

# On a small free host, converting a city map is slow: WARM_PRESETS=1 loads the four presets in the background at start-up.
if os.environ.get("WARM_PRESETS", "").lower() in ("1", "true", "yes"):
    threading.Thread(target=warm_presets, name="warm-presets", daemon=True).start()

# The in-app Guide uses .webp screenshots; some systems (Windows, slim Docker images) don't know that type by default.
mimetypes.add_type("image/webp", ".webp")

# One-process deployment: if the frontend has been built (npm run build), serve it from here too.
_frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
