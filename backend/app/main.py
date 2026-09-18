from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="SIH26137 — Quantum-Inspired Traffic Route Optimization",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Day 2: mount routers here, e.g.
# from app.api import graph, optimize, benchmark
# app.include_router(graph.router, prefix="/graph", tags=["graph"])
# app.include_router(optimize.router, prefix="/optimize", tags=["optimize"])
# app.include_router(benchmark.router, prefix="/benchmark", tags=["benchmark"])
