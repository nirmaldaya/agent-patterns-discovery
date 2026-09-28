"""APDI Graph Explorer API (FastAPI). Serves the React build from ../dist when present."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, graph
from .db import get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("apdi.app")

app = FastAPI(title="APDI Graph Explorer", version="1.0.0")

_cache: dict[str, tuple[float, Any]] = {}


def cached(key: str, compute: Callable[[], Any]) -> Any:
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < config.CACHE_SECONDS:
        return hit[1]
    value = compute()
    _cache[key] = (time.time(), value)
    return value


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


class IdsRequest(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=2000)
    edge_types: list[str] = Field(default_factory=list)


class ExpandRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=200)
    edge_types: list[str] = Field(default_factory=list)
    node_types: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list, max_length=2000)
    limit: int = 50


@app.get("/api/health")
def health() -> dict[str, Any]:
    db = get_db()
    return {"status": "ok", "mode": db.mode, "catalog": config.CATALOG, "schema": config.SCHEMA}


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    db = get_db()
    result = cached("meta", lambda: graph.meta(db))
    return {**result, "mode": db.mode, "catalog": config.CATALOG, "schema": config.SCHEMA,
            "max_nodes": config.MAX_NODES}


@app.get("/api/search")
def search(q: str = Query("", max_length=200), types: str = "", limit: int = 25) -> list[dict[str, Any]]:
    if not q.strip():
        return []
    return graph.search(get_db(), q, [t for t in types.split(",") if t], clamp(limit, 1, 100))


@app.post("/api/nodes")
def nodes(req: IdsRequest) -> list[dict[str, Any]]:
    return graph.nodes_by_id(get_db(), req.ids)


@app.post("/api/connect")
def connect(req: IdsRequest) -> list[dict[str, Any]]:
    """Edges between the given nodes, e.g. after dropping a node onto the canvas."""
    return graph.edges_among(get_db(), req.ids, req.edge_types)


@app.post("/api/expand")
def expand(req: ExpandRequest) -> dict[str, Any]:
    return graph.expand(get_db(), req.ids, req.edge_types, req.node_types,
                        clamp(req.limit, 1, config.MAX_NODES), req.exclude)


@app.get("/api/node")
def node(id: str = Query(..., max_length=500)) -> dict[str, Any]:
    detail = graph.node_detail(get_db(), id)
    if detail is None:
        raise HTTPException(status_code=404, detail="node not found")
    return detail


DIMENSIONS = {"INDUSTRY", "BUSINESS_UNIT", "SDLC_PHASE", "TECH", "BUSINESS_FUNCTION", "ARCHETYPE"}


@app.get("/api/overview")
def overview(artifact_type: str = "AGENT", src_type: str = "INDUSTRY", dst_type: str = "SDLC_PHASE",
             min_count: int = 1, limit: int = 200) -> dict[str, Any]:
    if artifact_type not in {"AGENT", "WORKFLOW"} or src_type not in DIMENSIONS or dst_type not in DIMENSIONS:
        raise HTTPException(status_code=400, detail="unsupported dimension")
    db = get_db()
    key = f"overview:{artifact_type}:{src_type}:{dst_type}:{min_count}:{limit}"
    return cached(key, lambda: graph.overview(db, artifact_type, src_type, dst_type, max(1, min_count),
                                              clamp(limit, 1, 1000)))


@app.get("/api/communities")
def communities() -> list[dict[str, Any]]:
    db = get_db()
    return cached("communities", lambda: graph.communities(db))


@app.get("/api/communities/{community_id}")
def community(community_id: int, limit: int = 80) -> dict[str, Any]:
    return graph.community_graph(get_db(), community_id, clamp(limit, 1, config.MAX_NODES))


@app.get("/api/cooccurrence")
def cooccurrence(kind: str = "TECH", min_weight: float = 1, limit: int = 150) -> dict[str, Any]:
    if kind not in {"TECH", "TOOL"}:
        raise HTTPException(status_code=400, detail="kind must be TECH or TOOL")
    return graph.cooccurrence(get_db(), kind, min_weight, clamp(limit, 1, 1000))


@app.get("/api/insights")
def insights(limit: int = 15) -> dict[str, Any]:
    db = get_db()
    n = clamp(limit, 1, 100)
    return cached(f"insights:{n}", lambda: graph.insights(db, n))


# ---- React build -----------------------------------------------------------------------------------------------
DIST = Path(__file__).resolve().parent.parent / "dist"

if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404)
    target = (DIST / path).resolve()
    if path and target.is_file() and DIST in target.parents:
        return FileResponse(target)
    index = DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {"message": "APDI Graph Explorer API. Build the UI with `npm run build` to serve it here."}
