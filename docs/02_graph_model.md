# APDI knowledge graph

The graph turns the curated `explore` tables into nodes and relationships, so the platform can be explored
visually (who builds what, with which tools, for which industry and SDLC phase) and analysed as a network
(which components are load-bearing, which solution patterns exist, what is isolated).

| Step | Notebook | Output (`<catalog>.explore`) |
|---|---|---|
| Build | [`notebooks/04_build_graph.py`](../notebooks/04_build_graph.py) | `graph_nodes`, `graph_edges`, `graph_summary_edges` |
| Analyse | [`notebooks/05_graph_analytics.py`](../notebooks/05_graph_analytics.py) | `graph_node_metrics`, `graph_communities` |

Both run in the `apdi-refresh` job after the labels step. The tables are plain Delta tables. Any front end
(the planned FastAPI + React app, a notebook, Genie) reads them through a SQL warehouse.

## Nodes

`node_id` is readable and stable across runs.

| node_type | node_group | node_id pattern | Source |
|---|---|---|---|
| AGENT, WORKFLOW, TOOL, MCP_SERVER, MCP_TOOL, KNOWLEDGE_BASE, GUARDRAIL, PROCESS | ARTIFACT | `AGENT:<deployment>:<id>` | `artifact_catalog` |
| MODEL | MODEL | `MODEL:<lower-cased name>` | `agents.model_name` |
| DEPLOYMENT | ORG | `DEPLOYMENT:<deployment>` (label = customer name) | ingested deployments |
| ORGANIZATION, BUSINESS_UNIT, PROJECT, TEAM | ORG | `TEAM:<deployment>:<lower-cased name>` | `rbac` hierarchy and artifact org columns |
| INDUSTRY, SDLC_PHASE, TECH, BUSINESS_FUNCTION, ARCHETYPE | TAXONOMY | `TECH:jira`, `INDUSTRY:healthcare` | `artifact_labels`, steward industry mapping |

Model and taxonomy nodes have no deployment. They are shared, so when more customers are loaded, the same
`TECH:jira` node connects artifacts across customers.

`properties` (JSON) carries extra attributes: for artifacts the org path, tags and all label arrays, for models
the provider, for tech nodes the category (Cloud, ALM & DevOps, Data ...).

## Edges

| edge_type | From → to | source | weight |
|---|---|---|---|
| CONTAINS | WORKFLOW → AGENT | DESIGN | 1, `properties.step_order` |
| USES_TOOL | AGENT → TOOL | DESIGN | 1 |
| USES_KNOWLEDGE_BASE | AGENT → KNOWLEDGE_BASE | DESIGN | 1 |
| HAS_GUARDRAIL | AGENT → GUARDRAIL | DESIGN | 1 |
| USES_MODEL | AGENT → MODEL | DESIGN | 1 |
| EXPOSES | MCP_SERVER → MCP_TOOL | DESIGN | 1 |
| INCLUDES | PROCESS → AGENT / WORKFLOW / TOOL | DESIGN | 1 |
| CALLS | AGENT / WORKFLOW → MCP_TOOL | RUNTIME | number of calls, `properties` has success and failure counts |
| OWNED_BY | artifact → most specific org unit (TEAM, else PROJECT, BUSINESS_UNIT, ORGANIZATION) | DESIGN | 1 |
| PART_OF | TEAM → PROJECT → BUSINESS_UNIT → ORGANIZATION → DEPLOYMENT | DESIGN | 1 |
| IN_INDUSTRY | artifact or org unit → INDUSTRY | LABEL_KEYWORD / LABEL_MANUAL | 1 |
| SUPPORTS_PHASE, USES_TECH, SERVES_FUNCTION, HAS_ARCHETYPE | artifact → taxonomy value | LABEL_KEYWORD | 1, `properties.matched_keyword` |
| CLONED_FROM | artifact → artifact it was copied from | DESIGN | 1 |
| CO_OCCURS | TECH ↔ TECH (same agent, all deployments), TOOL ↔ TOOL (same agent) | DERIVED | number of agents sharing both. Undirected, stored once with `src < dst` |

Every edge is kept only when both nodes exist. `graph_edges` also carries `src_type` and `dst_type` so a
front end can style edges without a join.

## Summary edges (the "meta graph")

`graph_summary_edges` pre-counts how often two dimension values appear on the same agent or workflow, for
example `INDUSTRY Healthcare → SDLC_PHASE Testing: 12 agents`. It covers these pairs:
Industry→SDLC phase, Industry→Tech, Industry→Archetype, Industry→Business function, Business unit→SDLC phase,
Business unit→Tech, Business unit→Archetype, SDLC phase→Tech, SDLC phase→Archetype, Business function→Archetype,
Business function→Tech, Archetype→Tech.

This is the table behind an overview graph or a Sankey (Industry → SDLC phase → Archetype), and it stays
small however many artifacts exist.

## Metrics and communities

| Column (`graph_node_metrics`) | Meaning | Typical use |
|---|---|---|
| `degree`, `weighted_degree` | How connected the node is | Node size |
| `pagerank`, `pagerank_rank_in_type` | Importance in the composition graph: tools, KBs and models many things depend on | "Load-bearing components", node size |
| `betweenness` | How often the node bridges otherwise separate parts | Integration hubs, single points of failure |
| `community_id` | Solution pattern the node belongs to | Node colour, pattern filter |
| `component_id`, `component_size`, `is_isolated` | Islands of artifacts not wired to anything else | "Orphan" agents and tools |

`graph_communities` describes each pattern: size, member mix, most central members, dominant industries, SDLC
phases, tech, archetypes and business functions, and a readable `community_name` such as
"Testing · Jira · Azure DevOps · Generator". `deployments` lists the customers whose artifacts are in it. More
than one means a cross-customer pattern, which is a strong template candidate.

How it is computed (details in the notebook): PageRank and betweenness run on the composition edges. Communities
(Louvain) run on composition plus label edges, without ownership, models and co-occurrence, so they reflect *what*
is built rather than *who* built it. Runtime call counts are log-scaled. The `resolution` widget controls
community granularity.

## Query recipes for the app

These are the queries behind the graph views discussed for the FastAPI + React app. They use named parameters
(`:node_id`), which the Databricks SQL Connector for Python supports, and run with the catalog selected.

**Overview / Sankey: how two dimensions relate**

```sql
SELECT src_label, dst_label, sum(artifact_count) AS artifact_count
FROM explore.graph_summary_edges
WHERE artifact_type = :artifact_type          -- 'AGENT' or 'WORKFLOW'
  AND src_type = :src_type AND dst_type = :dst_type   -- e.g. 'INDUSTRY', 'SDLC_PHASE'
GROUP BY src_label, dst_label
ORDER BY artifact_count DESC;
```

**Ego network: everything around one node** (1 hop, and a second hop that skips shared hubs)

```sql
WITH hop1 AS (
  SELECT * FROM explore.graph_edges
  WHERE (src = :node_id OR dst = :node_id) AND edge_type <> 'CO_OCCURS'
),
neighbours AS (
  SELECT DISTINCT CASE WHEN src = :node_id THEN dst ELSE src END AS node_id FROM hop1
),
hop2 AS (
  -- expand only through artifacts, so a hub like TECH:python does not pull in half the graph
  SELECT e.* FROM explore.graph_edges e
  JOIN neighbours n ON e.src = n.node_id OR e.dst = n.node_id
  JOIN explore.graph_nodes nn ON nn.node_id = n.node_id AND nn.node_group = 'ARTIFACT'
  WHERE :hops >= 2 AND e.edge_type NOT IN ('CO_OCCURS', 'PART_OF')
)
SELECT DISTINCT edge_id, src, dst, edge_type, source, weight, src_type, dst_type
FROM (SELECT * FROM hop1 UNION ALL SELECT * FROM hop2);
```

Then fetch the nodes for those edges, with metrics for size and colour:

```sql
SELECT n.node_id, n.node_type, n.node_group, n.label, n.properties,
       m.degree, m.pagerank, m.community_id, m.is_isolated
FROM explore.graph_nodes n
LEFT JOIN explore.graph_node_metrics m ON m.node_id = n.node_id
WHERE n.node_id IN (<ids from the edge query>);
```

**Technology co-occurrence map**

```sql
SELECT e.src, e.dst, e.weight AS shared_agents, s.label AS src_label, d.label AS dst_label,
       get_json_object(s.properties, '$.category') AS src_category
FROM explore.graph_edges e
JOIN explore.graph_nodes s ON s.node_id = e.src
JOIN explore.graph_nodes d ON d.node_id = e.dst
WHERE e.edge_type = 'CO_OCCURS' AND e.src_type = 'TECH' AND e.weight >= :min_shared
ORDER BY e.weight DESC;
```

**One solution pattern (community)**

```sql
SELECT e.*
FROM explore.graph_edges e
JOIN explore.graph_node_metrics a ON a.node_id = e.src AND a.community_id = :community_id
JOIN explore.graph_node_metrics b ON b.node_id = e.dst AND b.community_id = :community_id;
```

**Workflow anatomy: agents in order, with their tools and knowledge bases**

```sql
SELECT c.dst AS agent_node, CAST(get_json_object(c.properties, '$.step_order') AS INT) AS step_order,
       u.edge_type, u.dst AS component_node, n.label AS component
FROM explore.graph_edges c
LEFT JOIN explore.graph_edges u
  ON u.src = c.dst AND u.edge_type IN ('USES_TOOL', 'USES_KNOWLEDGE_BASE', 'HAS_GUARDRAIL', 'USES_MODEL')
LEFT JOIN explore.graph_nodes n ON n.node_id = u.dst
WHERE c.src = :workflow_node AND c.edge_type = 'CONTAINS'
ORDER BY step_order;
```

**Search, hubs and islands**

```sql
-- search box
SELECT node_id, node_type, label FROM explore.graph_nodes
WHERE lower(label) LIKE concat('%', lower(:q), '%') ORDER BY node_group, label LIMIT 20;

-- most load-bearing tools, knowledge bases and models
SELECT node_type, label, pagerank, degree FROM explore.graph_node_metrics
WHERE node_type IN ('TOOL', 'KNOWLEDGE_BASE', 'MODEL', 'MCP_TOOL') ORDER BY pagerank DESC LIMIT 20;

-- artifacts wired to nothing
SELECT node_type, label FROM explore.graph_node_metrics WHERE is_isolated ORDER BY node_type, label;
```

## Keeping graphs readable

A full platform graph becomes a "hairball" beyond a few hundred nodes. The app should start from the overview
or a search, then expand. Cap each response (for example the top 300 nodes by `pagerank`), let users filter
by node type, industry, business unit and minimum edge weight, and colour by `community_id` or `node_group`.

## Scale

Graph building is Spark SQL and scales with the explore tables. The analytics run NetworkX on the driver, which
is comfortable up to a few hundred thousand edges. Beyond that, the same metrics are available in GraphFrames
(`pageRank`, `labelPropagation`, `connectedComponents`) running on the cluster.
