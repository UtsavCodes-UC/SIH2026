from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import benchmark, graph, optimize
from app.core.vrp_formulation import UnreachableStopError
from app.data.osm_loader import CityLoadError
from app.services.problem_builder import InvalidProblemError

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
async def unprocessable(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(CityLoadError)
async def city_unavailable(_: Request, exc: CityLoadError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


api = APIRouter(prefix="/api")
api.include_router(graph.router)
api.include_router(optimize.router)
api.include_router(benchmark.router)


@api.get("/health")
def api_health() -> dict:
    return {"status": "ok"}


app.include_router(api)

# One-process deployment: if the frontend has been built (npm run build), serve it from here too.
_frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
