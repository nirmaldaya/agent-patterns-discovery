"""Graph queries behind the explorer API. All user input goes through bound parameters."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Iterable

from .db import Database, parse_json

CODE = re.compile(r"^[A-Z][A-Z_]*$")
CHUNK = 400


def codes(values: Iterable[str] | None) -> list[str]:
    """Node or edge type codes, validated so they can never carry SQL."""
    return [v for v in (values or []) if CODE.match(v)]


def in_list(prefix: str, values: list[Any], params: dict[str, Any]) -> str:
    """`(:prefix0, :prefix1, ...)` with the values bound into params."""
    names = []
    for i, v in enumerate(values):
        params[f"{prefix}{i}"] = v
        names.append(f":{prefix}{i}")
    return "(" + ", ".join(names) + ")"


def chunks(values: list[str], size: int = CHUNK) -> Iterable[list[str]]:
    for i in range(0, len(values), size):
        yield values[i:i + size]


def _num(v: Any) -> Any:
    """Plain JSON-friendly Python value: Decimal to float, numpy scalars and arrays to Python."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if hasattr(v, "tolist"):  # numpy array or scalar (returned by the Databricks SQL connector)
        return _num(v.tolist())
    if isinstance(v, (list, tuple)):
        return [_num(x) for x in v]
    if isinstance(v, dict):
        return {k: _num(x) for k, x in v.items()}
    return v


def node_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r["node_id"],
        "type": r["node_type"],
        "group": r["node_group"],
        "label": r["label"] if r.get("label") is not None else r["node_id"],
        "deployment": r.get("_deployment_id"),
        "description": r.get("description"),
        "status": r.get("status"),
        "run_count": _num(r.get("run_count")),
        "properties": parse_json(r.get("properties")),
        "degree": _num(r.get("degree")),
        "pagerank": _num(r.get("pagerank")),
        "betweenness": _num(r.get("betweenness")),
        "community_id": _num(r.get("community_id")),
        "is_isolated": r.get("is_isolated"),
    }


def edge_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r["edge_id"],
        "source": r["src"],
        "target": r["dst"],
        "type": r["edge_type"],
        "origin": r["source"],
        "weight": _num(r["weight"]),
        "properties": parse_json(r.get("properties")),
    }


NODE_COLUMNS = ("n.node_id, n.node_type, n.node_group, n.label, n._deployment_id, n.description, n.status, "
                "n.run_count, n.properties")
EDGE_COLUMNS = "e.edge_id, e.src, e.dst, e.edge_type, e.source, e.weight, e.properties"


def _node_select(db: Database) -> str:
    if db.has_table("metrics"):
        return (f"SELECT {NODE_COLUMNS}, m.degree, m.pagerank, m.betweenness, m.community_id, m.is_isolated "
                "FROM {nodes} n LEFT JOIN {metrics} m ON m.node_id = n.node_id")
    return f"SELECT {NODE_COLUMNS} FROM {{nodes}} n"


def nodes_by_id(db: Database, ids: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for part in chunks(list(dict.fromkeys(ids))):
        params: dict[str, Any] = {}
        sql = f"{_node_select(db)} WHERE n.node_id IN {in_list('id', part, params)}"
        out.extend(node_row(r) for r in db.query(sql, params))
    return out


def meta(db: Database) -> dict[str, Any]:
    node_types = db.query(
        "SELECT node_type, node_group, count(*) AS n FROM {nodes} GROUP BY node_type, node_group ORDER BY n DESC")
    edge_types = db.query("SELECT edge_type, count(*) AS n FROM {edges} GROUP BY edge_type ORDER BY n DESC")
    deployments = db.query("SELECT node_id, label FROM {nodes} WHERE node_type = 'DEPLOYMENT' ORDER BY label")
    maxima = {"max_pagerank": None, "max_degree": None}
    if db.has_table("metrics"):
        row = db.query("SELECT max(pagerank) AS max_pagerank, max(degree) AS max_degree FROM {metrics}")
        if row:
            maxima = {k: _num(v) for k, v in row[0].items()}
    return {
        "node_types": [{"type": r["node_type"], "group": r["node_group"], "count": int(r["n"])} for r in node_types],
        "edge_types": [{"type": r["edge_type"], "count": int(r["n"])} for r in edge_types],
        "deployments": [{"id": r["node_id"], "label": r["label"]} for r in deployments],
        "has_metrics": db.has_table("metrics"),
        "has_communities": db.has_table("communities"),
        **maxima,
    }


def search(db: Database, q: str, types: list[str], limit: int) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"q": f"%{q.strip().lower()}%"}
    where = "lower(n.label) LIKE :q"
    types = codes(types)
    if types:
        where += f" AND n.node_type IN {in_list('t', types, params)}"
    order = "m.pagerank DESC NULLS LAST, n.label" if db.has_table("metrics") else "n.label"
    sql = f"{_node_select(db)} WHERE {where} ORDER BY {order} LIMIT {int(limit)}"
    return [node_row(r) for r in db.query(sql, params)]


def edges_touching(db: Database, ids: list[str], edge_types: list[str], cap: int = 5000) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for part in chunks(ids):
        params: dict[str, Any] = {}
        ids_sql = in_list("id", part, params)
        where = f"(e.src IN {ids_sql} OR e.dst IN {ids_sql})"
        if edge_types:
            where += f" AND e.edge_type IN {in_list('et', edge_types, params)}"
        sql = f"SELECT {EDGE_COLUMNS} FROM {{edges}} e WHERE {where} ORDER BY e.weight DESC LIMIT {int(cap)}"
        out.extend(edge_row(r) for r in db.query(sql, params))
    return out


def edges_among(db: Database, ids: list[str], edge_types: list[str]) -> list[dict[str, Any]]:
    """All edges whose two ends are both in ids (filtered on both ends in SQL, so hubs stay cheap)."""
    ids = list(dict.fromkeys(ids))
    edge_types = codes(edge_types)
    out: dict[str, dict[str, Any]] = {}
    parts = list(chunks(ids))
    for a in parts:
        for b in parts:
            params: dict[str, Any] = {}
            where = f"e.src IN {in_list('a', a, params)} AND e.dst IN {in_list('b', b, params)}"
            if edge_types:
                where += f" AND e.edge_type IN {in_list('et', edge_types, params)}"
            for r in db.query(f"SELECT {EDGE_COLUMNS} FROM {{edges}} e WHERE {where}", params):
                out[r["edge_id"]] = edge_row(r)
    return list(out.values())


def expand(db: Database, ids: list[str], edge_types: list[str], node_types: list[str], limit: int,
           exclude: list[str]) -> dict[str, Any]:
    """Neighbours of ids (one hop), ranked by edge weight then pagerank, capped at limit new nodes."""
    ids = list(dict.fromkeys(ids))
    seeds = set(ids)
    already = set(exclude) | seeds
    edge_types, node_types = codes(edge_types), codes(node_types)
    touching = edges_touching(db, ids, edge_types)

    best_weight: dict[str, float] = {}
    for e in touching:
        other = e["target"] if e["source"] in seeds else e["source"]
        if other not in already:
            best_weight[other] = max(best_weight.get(other, 0.0), float(e["weight"] or 0))

    candidates = nodes_by_id(db, list(best_weight))
    if node_types:
        candidates = [n for n in candidates if n["type"] in node_types]
    candidates.sort(key=lambda n: (-best_weight[n["id"]], -(n["pagerank"] or 0), n["label"]))
    kept = candidates[:limit]

    # Every link between the new nodes, the seeds and whatever is already on the canvas, of any type.
    edges = edges_among(db, list(seeds | {n["id"] for n in kept} | set(exclude)), [])
    return {"nodes": kept, "edges": edges, "truncated": len(candidates) > len(kept),
            "available": len(candidates)}


def node_detail(db: Database, node_id: str) -> dict[str, Any] | None:
    found = nodes_by_id(db, [node_id])
    if not found:
        return None
    node = found[0]
    rel = db.query(
        """SELECT e.edge_type,
                  CASE WHEN e.src = :id THEN 'out' ELSE 'in' END AS direction,
                  CASE WHEN e.src = :id THEN e.dst_type ELSE e.src_type END AS other_type,
                  count(*) AS n
           FROM {edges} e WHERE e.src = :id OR e.dst = :id
           GROUP BY 1, 2, 3 ORDER BY n DESC""",
        {"id": node_id},
    )
    community = None
    if node.get("community_id") is not None and db.has_table("communities"):
        rows = db.query("SELECT community_id, community_name, size FROM {communities} WHERE community_id = :c",
                        {"c": int(node["community_id"])})
        community = rows[0] if rows else None
    return {
        "node": node,
        "relations": [{"edge_type": r["edge_type"], "direction": r["direction"], "other_type": r["other_type"],
                       "count": int(r["n"])} for r in rel],
        "community": community,
    }


def overview(db: Database, artifact_type: str, src_type: str, dst_type: str, min_count: int,
             limit: int) -> dict[str, Any]:
    rows = db.query(
        """SELECT src_node_id, max(src_label) AS src_label, dst_node_id, max(dst_label) AS dst_label,
                  sum(artifact_count) AS artifact_count
           FROM {summary}
           WHERE artifact_type = :at AND src_type = :st AND dst_type = :dt
           GROUP BY src_node_id, dst_node_id
           HAVING sum(artifact_count) >= :mc
           ORDER BY artifact_count DESC""" + f" LIMIT {int(limit)}",
        {"at": artifact_type, "st": src_type, "dt": dst_type, "mc": int(min_count)},
    )
    node_ids = list(dict.fromkeys([r["src_node_id"] for r in rows] + [r["dst_node_id"] for r in rows]))
    nodes = {n["id"]: n for n in nodes_by_id(db, node_ids)}
    for r in rows:  # summary values always have a node, but be safe if a table is stale
        for key, label, typ in ((r["src_node_id"], r["src_label"], src_type), (r["dst_node_id"], r["dst_label"], dst_type)):
            nodes.setdefault(key, {"id": key, "type": typ, "group": "TAXONOMY", "label": label, "properties": None})
    edges = [{
        "id": f"SUMMARY|{artifact_type}|{r['src_node_id']}|{r['dst_node_id']}",
        "source": r["src_node_id"], "target": r["dst_node_id"],
        "type": "SUMMARY", "origin": "SUMMARY", "weight": _num(r["artifact_count"]),
        "properties": {"artifact_type": artifact_type, "artifact_count": _num(r["artifact_count"])},
    } for r in rows]
    return {"nodes": list(nodes.values()), "edges": edges, "truncated": len(rows) >= limit}


def communities(db: Database) -> list[dict[str, Any]]:
    if not db.has_table("communities"):
        return []
    rows = db.query(
        """SELECT community_id, community_name, size, artifact_count, top_artifacts, top_industries,
                  top_sdlc_phases, top_tech, top_archetypes, deployments
           FROM {communities} ORDER BY size DESC LIMIT 200""")
    return [{k: _num(v) for k, v in r.items()} for r in rows]


def community_graph(db: Database, community_id: int, limit: int) -> dict[str, Any]:
    if not db.has_table("metrics"):
        return {"nodes": [], "edges": [], "truncated": False}
    ids = [r["node_id"] for r in db.query(
        "SELECT node_id FROM {metrics} WHERE community_id = :c ORDER BY pagerank DESC NULLS LAST, degree DESC "
        f"LIMIT {int(limit) + 1}", {"c": int(community_id)})]
    truncated = len(ids) > limit
    ids = ids[:limit]
    return {"nodes": nodes_by_id(db, ids), "edges": edges_among(db, ids, []), "truncated": truncated}


def cooccurrence(db: Database, kind: str, min_weight: float, limit: int) -> dict[str, Any]:
    edges = [edge_row(r) for r in db.query(
        f"SELECT {EDGE_COLUMNS} FROM {{edges}} e "
        "WHERE e.edge_type = 'CO_OCCURS' AND e.src_type = :k AND e.weight >= :w "
        f"ORDER BY e.weight DESC LIMIT {int(limit)}",
        {"k": kind, "w": float(min_weight)})]
    ids = list(dict.fromkeys([e["source"] for e in edges] + [e["target"] for e in edges]))
    return {"nodes": nodes_by_id(db, ids), "edges": edges, "truncated": len(edges) >= limit}


def insights(db: Database, limit: int) -> dict[str, Any]:
    if not db.has_table("metrics"):
        return {"hubs": [], "bridges": [], "islands": []}

    def pick(where: str, order: str) -> list[dict[str, Any]]:
        ids = [r["node_id"] for r in db.query(
            f"SELECT node_id FROM {{metrics}} WHERE {where} ORDER BY {order} LIMIT {int(limit)}")]
        by_id = {n["id"]: n for n in nodes_by_id(db, ids)}
        return [by_id[i] for i in ids if i in by_id]

    return {
        "hubs": pick("node_type IN ('TOOL', 'MCP_TOOL', 'KNOWLEDGE_BASE', 'MODEL', 'GUARDRAIL') AND pagerank IS NOT NULL",
                     "pagerank DESC"),
        "bridges": pick("node_group = 'ARTIFACT' AND betweenness > 0", "betweenness DESC"),
        "islands": pick("is_isolated", "node_type, label"),
    }
