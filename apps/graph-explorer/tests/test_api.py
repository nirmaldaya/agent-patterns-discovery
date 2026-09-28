"""API tests against the bundled sample graph (DuckDB mode). Run: APDI_LOCAL_DATA=sample_data pytest"""

import os
from pathlib import Path

os.environ.setdefault("APDI_LOCAL_DATA", str(Path(__file__).resolve().parent.parent / "sample_data"))

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402

client = TestClient(app)


def test_health_and_meta():
    assert client.get("/api/health").json()["mode"] == "local"
    meta = client.get("/api/meta").json()
    types = {t["type"] for t in meta["node_types"]}
    assert {"AGENT", "WORKFLOW", "TOOL", "INDUSTRY", "TECH"} <= types
    assert meta["has_metrics"] and meta["max_pagerank"] > 0


def test_search_ranks_and_filters():
    hits = client.get("/api/search", params={"q": "jira"}).json()
    assert hits and all("jira" in h["label"].lower() for h in hits)
    tools = client.get("/api/search", params={"q": "jira", "types": "TOOL"}).json()
    assert tools and {h["type"] for h in tools} == {"TOOL"}
    assert client.get("/api/search", params={"q": "x' OR '1'='1"}).json() == []


def test_expand_respects_types_limit_and_links_existing_nodes():
    agent = "AGENT:dep_001:3"
    full = client.post("/api/expand", json={"ids": [agent]}).json()
    assert full["nodes"] and all(n["id"] != agent for n in full["nodes"])
    only_tools = client.post("/api/expand", json={"ids": [agent], "node_types": ["TOOL"]}).json()
    assert only_tools["nodes"] and {n["type"] for n in only_tools["nodes"]} == {"TOOL"}
    capped = client.post("/api/expand", json={"ids": [agent], "limit": 2}).json()
    assert len(capped["nodes"]) == 2 and capped["truncated"]
    # a node already on the canvas is not returned again, but its links are
    existing = only_tools["nodes"][0]["id"]
    again = client.post("/api/expand", json={"ids": [agent], "exclude": [existing]}).json()
    assert existing not in {n["id"] for n in again["nodes"]}
    assert any(existing in (e["source"], e["target"]) for e in again["edges"])


def test_connect_returns_only_edges_among_ids():
    ids = ["WORKFLOW:dep_001:1", "AGENT:dep_001:3", "AGENT:dep_001:4", "TECH:jira"]
    edges = client.post("/api/connect", json={"ids": ids}).json()
    assert edges and all(e["source"] in ids and e["target"] in ids for e in edges)
    assert {"CONTAINS", "USES_TECH"} <= {e["type"] for e in edges}


def test_node_detail_relations():
    d = client.get("/api/node", params={"id": "WORKFLOW:dep_001:1"}).json()
    assert d["node"]["label"] == "Requirements to Test Automation"
    rel = {(r["edge_type"], r["direction"]) for r in d["relations"]}
    assert ("CONTAINS", "out") in rel
    assert client.get("/api/node", params={"id": "nope"}).status_code == 404


def test_overview_communities_cooccurrence_insights():
    ov = client.get("/api/overview", params={"src_type": "SDLC_PHASE", "dst_type": "TECH"}).json()
    assert ov["edges"] and all(e["type"] == "SUMMARY" for e in ov["edges"])
    ids = {n["id"] for n in ov["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in ov["edges"])
    assert client.get("/api/overview", params={"src_type": "BOGUS"}).status_code == 400

    comms = client.get("/api/communities").json()
    assert comms and comms[0]["community_name"]
    cg = client.get(f"/api/communities/{comms[0]['community_id']}").json()
    assert cg["nodes"] and all(n["community_id"] == comms[0]["community_id"] for n in cg["nodes"])

    co = client.get("/api/cooccurrence", params={"kind": "TECH"}).json()
    assert co["edges"] and all(e["type"] == "CO_OCCURS" for e in co["edges"])

    ins = client.get("/api/insights").json()
    assert ins["hubs"] and any(n["label"] == "Platform Helper" for n in ins["islands"])
