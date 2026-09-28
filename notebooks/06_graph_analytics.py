# Databricks notebook source
# MAGIC %md
# MAGIC # 06 · Graph analytics: centrality, communities and islands
# MAGIC
# MAGIC Runs network analytics over `explore.graph_nodes` / `graph_edges` and writes:
# MAGIC
# MAGIC | Table | Grain | What it tells you |
# MAGIC |---|---|---|
# MAGIC | `graph_node_metrics` | one row per node | **degree**: how connected; **pagerank**: how load-bearing in the platform's composition graph (tools, KBs, models many things depend on); **betweenness**: bridges between otherwise separate parts; **community_id**: the solution pattern the node belongs to; **component_id** / **is_isolated**: islands of artifacts not wired to anything |
# MAGIC | `graph_communities` | one row per community | Size, member mix, the most central members, and the dominant industry, SDLC phase, tech and archetype, turned into a readable name such as "Testing · Jira · Selenium · Generator" |
# MAGIC
# MAGIC **Which edges feed which metric**
# MAGIC * *Composition graph* (pagerank, betweenness): `CONTAINS`, `USES_TOOL`, `USES_KNOWLEDGE_BASE`, `HAS_GUARDRAIL`,
# MAGIC   `USES_MODEL`, `EXPOSES`, `CALLS`, `INCLUDES`, `CLONED_FROM`.
# MAGIC * *Components* (islands): the composition graph without `USES_MODEL`, because a shared model would otherwise join everything.
# MAGIC * *Pattern graph* (communities): composition plus label edges (industry, SDLC phase, tech, function, archetype), without org
# MAGIC   ownership, models and derived co-occurrence, so communities reflect *what* is built rather than *who* built it.
# MAGIC * Runtime `CALLS` weights are log-scaled so heavy usage informs, but does not swamp, the design structure.
# MAGIC
# MAGIC Uses NetworkX on the driver, which is simple and comfortable up to a few hundred thousand edges. If the graph
# MAGIC outgrows that, the same metrics exist in GraphFrames (`pageRank`, `labelPropagation`, `connectedComponents`).

# COMMAND ----------

# MAGIC %pip install -q "networkx>=3.2"

# COMMAND ----------

dbutils.widgets.text("catalog", "apdi", "Catalog")
dbutils.widgets.text("resolution", "1.0", "Community resolution (higher = more, smaller communities)")
dbutils.widgets.text("betweenness_sample", "500", "Nodes sampled for betweenness (0 = exact)")

# COMMAND ----------

import json
import math
from collections import Counter

import networkx as nx
from pyspark.sql import types as T

CATALOG = dbutils.widgets.get("catalog").strip()
RESOLUTION = float(dbutils.widgets.get("resolution") or 1.0)
BETWEENNESS_SAMPLE = int(dbutils.widgets.get("betweenness_sample") or 0)
SEED = 42
spark.sql(f"USE CATALOG `{CATALOG}`")

COMPOSITION = {"CONTAINS", "USES_TOOL", "USES_KNOWLEDGE_BASE", "HAS_GUARDRAIL", "USES_MODEL",
               "EXPOSES", "CALLS", "INCLUDES", "CLONED_FROM"}
LABELS = {"IN_INDUSTRY", "SUPPORTS_PHASE", "USES_TECH", "SERVES_FUNCTION", "HAS_ARCHETYPE"}
COMPONENT_EDGES = COMPOSITION - {"USES_MODEL"}
PATTERN_EDGES = (COMPOSITION - {"USES_MODEL"}) | LABELS

# pandas/itertuples cannot use names starting with "_", so _deployment_id is renamed while in pandas.
nodes = spark.table("explore.graph_nodes").selectExpr(
    "node_id", "node_type", "node_group", "label", "_deployment_id AS deployment_id", "properties").toPandas()
edges = spark.table("explore.graph_edges").select("src", "dst", "edge_type", "weight").toPandas()
print(f"{len(nodes)} nodes, {len(edges)} edges")


def scaled(weight):
    """1 for a plain design edge, 1 + ln(n) for n runtime calls."""
    return 1.0 + math.log(max(float(weight or 1.0), 1.0))


def build(edge_types, extra_nodes=()):
    g = nx.Graph()
    g.add_nodes_from(extra_nodes)
    for r in edges[edges.edge_type.isin(edge_types)].itertuples(index=False):
        w = scaled(r.weight)
        if g.has_edge(r.src, r.dst):
            g[r.src][r.dst]["weight"] += w
        else:
            g.add_edge(r.src, r.dst, weight=w)
    return g

# COMMAND ----------

# MAGIC %md ### Centrality, components and communities

# COMMAND ----------

full = build(set(edges.edge_type.unique()), nodes.node_id)
composition = build(COMPOSITION)
artifact_ids = nodes.loc[nodes.node_group == "ARTIFACT", "node_id"]
components_graph = build(COMPONENT_EDGES, artifact_ids)
pattern = build(PATTERN_EDGES)

pagerank = nx.pagerank(composition, weight="weight") if composition.number_of_edges() else {}
if composition.number_of_nodes() > 2:
    k = BETWEENNESS_SAMPLE if 0 < BETWEENNESS_SAMPLE < composition.number_of_nodes() else None
    betweenness = nx.betweenness_centrality(composition, k=k, seed=SEED, normalized=True)
else:
    betweenness = {}

component_of, component_size = {}, {}
for i, comp in enumerate(sorted(nx.connected_components(components_graph), key=len, reverse=True), 1):
    for n in comp:
        component_of[n], component_size[n] = i, len(comp)

community_of = {}
if pattern.number_of_edges():
    found = nx.community.louvain_communities(pattern, weight="weight", resolution=RESOLUTION, seed=SEED)
    for i, comm in enumerate(sorted(found, key=len, reverse=True), 1):
        for n in comm:
            community_of[n] = i

# COMMAND ----------

nodes["degree"] = nodes.node_id.map(lambda n: full.degree(n)).astype("int64")
nodes["weighted_degree"] = nodes.node_id.map(lambda n: float(full.degree(n, weight="weight")))
nodes["pagerank"] = nodes.node_id.map(pagerank.get)
nodes["betweenness"] = nodes.node_id.map(betweenness.get)
nodes["community_id"] = nodes.node_id.map(community_of.get)
nodes["component_id"] = nodes.node_id.map(component_of.get)
nodes["component_size"] = nodes.node_id.map(component_size.get)
nodes["is_isolated"] = (nodes.node_group == "ARTIFACT") & (nodes.component_size.fillna(1) <= 1)
nodes["pagerank_rank_in_type"] = (
    nodes.groupby("node_type")["pagerank"].rank(ascending=False, method="min")
)


def nullable_int(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else int(v)


def nullable_float(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


metrics_schema = T.StructType([
    T.StructField("node_id", T.StringType(), False),
    T.StructField("node_type", T.StringType()),
    T.StructField("node_group", T.StringType()),
    T.StructField("label", T.StringType()),
    T.StructField("_deployment_id", T.StringType()),
    T.StructField("degree", T.LongType()),
    T.StructField("weighted_degree", T.DoubleType()),
    T.StructField("pagerank", T.DoubleType()),
    T.StructField("pagerank_rank_in_type", T.LongType()),
    T.StructField("betweenness", T.DoubleType()),
    T.StructField("community_id", T.LongType()),
    T.StructField("component_id", T.LongType()),
    T.StructField("component_size", T.LongType()),
    T.StructField("is_isolated", T.BooleanType()),
])
metrics_rows = [
    (r.node_id, r.node_type, r.node_group, r.label, r.deployment_id, int(r.degree), float(r.weighted_degree),
     nullable_float(r.pagerank), nullable_int(r.pagerank_rank_in_type), nullable_float(r.betweenness),
     nullable_int(r.community_id), nullable_int(r.component_id), nullable_int(r.component_size), bool(r.is_isolated))
    for r in nodes.itertuples(index=False)
]
(spark.createDataFrame(metrics_rows, metrics_schema)
 .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("explore.graph_node_metrics"))

# COMMAND ----------

# MAGIC %md ### Describe each community

# COMMAND ----------

LABEL_KEYS = {"industries": "INDUSTRY", "sdlc_phases": "SDLC_PHASE", "tech_stack": "TECH", "archetypes": "ARCHETYPE",
              "business_functions": "BUSINESS_FUNCTION"}
TAXONOMY_TYPE = {"INDUSTRY", "SDLC_PHASE", "TECH", "ARCHETYPE", "BUSINESS_FUNCTION"}


def top(counter, n):
    return [k for k, _ in counter.most_common(n)]


community_rows = []
members = nodes[nodes.community_id.notna()]
for cid, grp in members.groupby("community_id"):
    grp = grp.sort_values("pagerank", ascending=False, na_position="last")
    artifacts = grp[grp.node_group == "ARTIFACT"]
    dims = {v: Counter() for v in LABEL_KEYS.values()}
    # Labels of the member artifacts, plus taxonomy nodes that ended up in the community.
    for props in artifacts.properties.dropna():
        p = json.loads(props)
        for key, dim in LABEL_KEYS.items():
            dims[dim].update(p.get(key) or [])
    for r in grp[grp.node_type.isin(TAXONOMY_TYPE)].itertuples(index=False):
        dims[r.node_type][r.label] += 1

    name_parts = top(dims["SDLC_PHASE"], 1) + top(dims["TECH"], 2) + top(dims["ARCHETYPE"], 1)
    if not name_parts:
        name_parts = top(dims["INDUSTRY"], 1) + top(dims["BUSINESS_FUNCTION"], 1)
    if not name_parts:
        name_parts = list(grp.label.head(2))
    community_rows.append((
        int(cid),
        " · ".join(name_parts),
        int(len(grp)),
        int(len(artifacts)),
        {k: int(v) for k, v in grp.node_type.value_counts().items()},
        [str(x) for x in artifacts.label.head(10)],
        [str(x) for x in grp.label.head(10)],
        top(dims["INDUSTRY"], 3), top(dims["SDLC_PHASE"], 3), top(dims["TECH"], 5),
        top(dims["ARCHETYPE"], 3), top(dims["BUSINESS_FUNCTION"], 3),
        sorted({d for d in artifacts.deployment_id.dropna()}),
    ))

community_schema = T.StructType([
    T.StructField("community_id", T.LongType(), False),
    T.StructField("community_name", T.StringType()),
    T.StructField("size", T.LongType()),
    T.StructField("artifact_count", T.LongType()),
    T.StructField("node_type_counts", T.MapType(T.StringType(), T.LongType())),
    T.StructField("top_artifacts", T.ArrayType(T.StringType())),
    T.StructField("top_members", T.ArrayType(T.StringType())),
    T.StructField("top_industries", T.ArrayType(T.StringType())),
    T.StructField("top_sdlc_phases", T.ArrayType(T.StringType())),
    T.StructField("top_tech", T.ArrayType(T.StringType())),
    T.StructField("top_archetypes", T.ArrayType(T.StringType())),
    T.StructField("top_business_functions", T.ArrayType(T.StringType())),
    T.StructField("deployments", T.ArrayType(T.StringType())),
])
(spark.createDataFrame(community_rows, community_schema)
 .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("explore.graph_communities"))

# COMMAND ----------

print(f"pagerank on {composition.number_of_nodes()} nodes, {len(set(community_of.values()))} communities, "
      f"{nodes.is_isolated.sum()} isolated artifacts")
display(spark.sql("""
  SELECT community_id, community_name, size, artifact_count, top_artifacts, deployments
  FROM explore.graph_communities ORDER BY size DESC LIMIT 20
"""))
display(spark.sql("""
  SELECT node_type, label, round(pagerank, 4) AS pagerank, degree, round(betweenness, 4) AS betweenness, community_id
  FROM explore.graph_node_metrics WHERE pagerank IS NOT NULL ORDER BY pagerank DESC LIMIT 20
"""))
