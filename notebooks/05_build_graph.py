# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Build the APDI knowledge graph (nodes and edges)
# MAGIC
# MAGIC Reshapes the curated `explore` tables into a property graph for graph visualisation and analytics.
# MAGIC Nothing new is inferred here: every node and edge comes from a table built by the earlier steps.
# MAGIC
# MAGIC | Table | Grain | Use |
# MAGIC |---|---|---|
# MAGIC | `graph_nodes` | one row per node | Agents, workflows, tools, MCP servers/tools, knowledge bases, guardrails, processes, models, org units, customers and taxonomy values (industry, SDLC phase, tech, business function, archetype) |
# MAGIC | `graph_edges` | one row per relationship | Composition, usage, ownership, labels, clone lineage and derived co-occurrence, each with a weight |
# MAGIC | `graph_summary_edges` | one row per pair of dimension values | Pre-aggregated "meta graph" (e.g. Healthcare → Testing: 12 agents) for overview and Sankey views |
# MAGIC
# MAGIC **Node ids** are readable and stable across runs:
# MAGIC * artifacts: `AGENT:<deployment>:<id>`, `WORKFLOW:<deployment>:<id>`, …
# MAGIC * org units: `TEAM:<deployment>:<lower-cased name>` (also `PROJECT`, `BUSINESS_UNIT`, `ORGANIZATION`), and `DEPLOYMENT:<deployment>`
# MAGIC * shared values: `INDUSTRY:healthcare`, `SDLC_PHASE:testing`, `TECH:jira`, `BUSINESS_FUNCTION:…`, `ARCHETYPE:…`, `MODEL:gpt-4o`
# MAGIC
# MAGIC Shared-value nodes have no deployment, so they connect artifacts across customers once more deployments are loaded.
# MAGIC Every edge is kept only when both of its nodes exist.

# COMMAND ----------

dbutils.widgets.text("catalog", "apdi", "Catalog")

# COMMAND ----------

CATALOG = dbutils.widgets.get("catalog").strip()
spark.sql(f"USE CATALOG `{CATALOG}`")


def run(sql):
    return spark.sql(sql)

# COMMAND ----------

# MAGIC %md ### Nodes

# COMMAND ----------

# Org units referenced anywhere: active units in rbac plus the org columns on artifacts
# (an artifact without a realm can still name its team).
run("""
CREATE OR REPLACE TEMP VIEW g_org_units AS
SELECT DISTINCT _deployment_id, level, name FROM (
  SELECT _deployment_id, 'ORGANIZATION' AS level, organization_name AS name FROM raw_rbac.organization WHERE active
  UNION ALL SELECT _deployment_id, 'BUSINESS_UNIT', domain_name  FROM raw_rbac.domain  WHERE active
  UNION ALL SELECT _deployment_id, 'PROJECT',       project_name FROM raw_rbac.project WHERE active
  UNION ALL SELECT _deployment_id, 'TEAM',          team_name    FROM raw_rbac.team    WHERE active
  UNION ALL SELECT _deployment_id, 'ORGANIZATION',  organization_name FROM explore.artifact_catalog
  UNION ALL SELECT _deployment_id, 'BUSINESS_UNIT', domain_name       FROM explore.artifact_catalog
  UNION ALL SELECT _deployment_id, 'PROJECT',       project_name      FROM explore.artifact_catalog
  UNION ALL SELECT _deployment_id, 'TEAM',          team_name         FROM explore.artifact_catalog
) WHERE name IS NOT NULL
""")

# Parent of each org unit, from the rbac foreign keys (team > project > domain > organization > deployment).
run("""
CREATE OR REPLACE TEMP VIEW g_org_parents AS
SELECT t._deployment_id, 'TEAM' AS level, t.team_name AS name,
       CASE WHEN p.id IS NOT NULL THEN 'PROJECT' END AS parent_level, p.project_name AS parent_name
FROM raw_rbac.team t
LEFT JOIN raw_rbac.project p ON p._deployment_id = t._deployment_id AND p.id = t.project_id
UNION ALL
SELECT p._deployment_id, 'PROJECT', p.project_name, CASE WHEN d.id IS NOT NULL THEN 'BUSINESS_UNIT' END, d.domain_name
FROM raw_rbac.project p
LEFT JOIN raw_rbac.domain d ON d._deployment_id = p._deployment_id AND d.id = p.domain_id
UNION ALL
SELECT d._deployment_id, 'BUSINESS_UNIT', d.domain_name, CASE WHEN o.id IS NOT NULL THEN 'ORGANIZATION' END, o.organization_name
FROM raw_rbac.domain d
LEFT JOIN raw_rbac.organization o ON o._deployment_id = d._deployment_id AND o.id = d.organization_id
UNION ALL
SELECT _deployment_id, 'ORGANIZATION', organization_name, CAST(NULL AS STRING), CAST(NULL AS STRING)
FROM raw_rbac.organization
""")

run("""
CREATE OR REPLACE TEMP VIEW g_nodes_raw AS
WITH deployments AS (
  SELECT d._deployment_id, COALESCE(max(l.customer_name), d._deployment_id) AS customer_name
  FROM (SELECT DISTINCT _deployment_id FROM explore.artifact_catalog) d
  LEFT JOIN raw_core.customer_license_mst l ON l._deployment_id = d._deployment_id
  GROUP BY d._deployment_id
),
org_units AS (SELECT * FROM g_org_units),
taxonomy AS (
  SELECT CASE dimension
           WHEN 'TECH_STACK' THEN 'TECH'
           WHEN 'AGENT_ARCHETYPE' THEN 'ARCHETYPE'
           ELSE dimension END AS node_type,
         label, max(category) AS category
  FROM explore.artifact_labels GROUP BY 1, 2
  UNION
  SELECT 'INDUSTRY', industry_manual, CAST(NULL AS STRING)
  FROM explore.org_hierarchy WHERE industry_manual IS NOT NULL
)
SELECT concat('DEPLOYMENT:', _deployment_id) AS node_id, 'DEPLOYMENT' AS node_type, 'ORG' AS node_group,
       customer_name AS label, _deployment_id, CAST(NULL AS BIGINT) AS artifact_id,
       CAST(NULL AS STRING) AS description, CAST(NULL AS STRING) AS status,
       CAST(NULL AS BIGINT) AS run_count, CAST(NULL AS DOUBLE) AS avg_user_rating,
       CAST(NULL AS BOOLEAN) AS is_golden, CAST(NULL AS TIMESTAMP) AS created_at,
       CAST(NULL AS STRING) AS properties
FROM deployments
UNION ALL
SELECT concat(level, ':', _deployment_id, ':', lower(trim(name))), level, 'ORG', name, _deployment_id,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
FROM org_units
UNION ALL
SELECT concat(artifact_type, ':', _deployment_id, ':', artifact_id), artifact_type, 'ARTIFACT', artifact_name,
       _deployment_id, artifact_id, description, status, run_count, avg_user_rating, is_golden, created_at,
       to_json(named_struct(
         'organization', organization_name, 'business_unit', domain_name, 'project', project_name,
         'team', team_name, 'practice_area', practice_area, 'tags', tags,
         'industries', industries, 'industry_source', industry_source, 'sdlc_phases', sdlc_phases,
         'tech_stack', tech_stack, 'business_functions', business_functions, 'archetypes', archetypes,
         'run_count_30d', run_count_30d))
FROM explore.artifact_catalog
UNION ALL
SELECT concat('MODEL:', lower(trim(model_name))), 'MODEL', 'MODEL', max(model_name), NULL, NULL,
       NULL, NULL, NULL, NULL, NULL, NULL,
       to_json(named_struct('provider', max(model_provider)))
FROM explore.agents WHERE model_name IS NOT NULL
GROUP BY lower(trim(model_name))
UNION ALL
SELECT concat(node_type, ':', lower(trim(label))), node_type, 'TAXONOMY', max(label), NULL, NULL,
       NULL, NULL, NULL, NULL, NULL, NULL,
       to_json(named_struct('category', max(category)))
FROM taxonomy WHERE label IS NOT NULL
GROUP BY node_type, lower(trim(label))
""")

# COMMAND ----------

# MAGIC %md ### Edges

# COMMAND ----------

ART = "concat('{t}:', {dep}, ':', {id})"


def art(node_type, dep="_deployment_id", id_col="artifact_id"):
    return ART.format(t=node_type, dep=dep, id=id_col)


def org(level, name_col, dep="_deployment_id"):
    return f"concat('{level}:', {dep}, ':', lower(trim({name_col})))"


# Most specific org unit an artifact (or org path row) belongs to.
OWNER = f"""CASE WHEN team_name IS NOT NULL THEN {org('TEAM', 'team_name')}
                 WHEN project_name IS NOT NULL THEN {org('PROJECT', 'project_name')}
                 WHEN domain_name IS NOT NULL THEN {org('BUSINESS_UNIT', 'domain_name')}
                 WHEN organization_name IS NOT NULL THEN {org('ORGANIZATION', 'organization_name')} END"""

LABEL_EDGE = """CASE dimension WHEN 'INDUSTRY' THEN 'IN_INDUSTRY' WHEN 'SDLC_PHASE' THEN 'SUPPORTS_PHASE'
                 WHEN 'TECH_STACK' THEN 'USES_TECH' WHEN 'BUSINESS_FUNCTION' THEN 'SERVES_FUNCTION'
                 WHEN 'AGENT_ARCHETYPE' THEN 'HAS_ARCHETYPE' END"""
LABEL_NODE = """concat(CASE dimension WHEN 'TECH_STACK' THEN 'TECH' WHEN 'AGENT_ARCHETYPE' THEN 'ARCHETYPE'
                 ELSE dimension END, ':', lower(trim(label)))"""

NO_PROPS = "CAST(NULL AS STRING)"

edge_selects = [
    # --- composition (design time) ---
    f"""SELECT {art('WORKFLOW', id_col='workflow_id')} AS src, {art('AGENT', id_col='agent_id')} AS dst,
               'CONTAINS' AS edge_type, 'DESIGN' AS source, 1.0 AS weight, _deployment_id,
               to_json(named_struct('step_order', step_order)) AS properties
        FROM explore.workflow_agents""",
    f"""SELECT DISTINCT {art('AGENT', id_col='agent_id')}, {art('TOOL', id_col='tool_id')},
               'USES_TOOL', 'DESIGN', 1.0, _deployment_id, {NO_PROPS}
        FROM explore.agent_tools""",
    f"""SELECT DISTINCT {art('AGENT', id_col='agent_id')}, {art('KNOWLEDGE_BASE', id_col='knowledge_base_id')},
               'USES_KNOWLEDGE_BASE', 'DESIGN', 1.0, _deployment_id, {NO_PROPS}
        FROM explore.agent_knowledge_bases""",
    f"""SELECT DISTINCT {art('AGENT', id_col='agent_id')}, {art('GUARDRAIL', id_col='guardrail_id')},
               'HAS_GUARDRAIL', 'DESIGN', 1.0, _deployment_id, {NO_PROPS}
        FROM explore.agent_guardrails""",
    f"""SELECT {art('AGENT', id_col='agent_id')}, concat('MODEL:', lower(trim(model_name))),
               'USES_MODEL', 'DESIGN', 1.0, _deployment_id, {NO_PROPS}
        FROM explore.agents WHERE model_name IS NOT NULL""",
    f"""SELECT {art('MCP_SERVER', id_col='server_id')}, {art('MCP_TOOL', id_col='mcp_tool_id')},
               'EXPOSES', 'DESIGN', 1.0, _deployment_id, {NO_PROPS}
        FROM explore.mcp_tools WHERE server_id IS NOT NULL""",
    f"""SELECT {art('PROCESS', id_col='process_id')}, concat(node_kind, ':', _deployment_id, ':', artifact_id),
               'INCLUDES', 'DESIGN', 1.0, _deployment_id, to_json(named_struct('node_id', node_id))
        FROM (SELECT *, CASE WHEN artifact_type LIKE 'AGENT%' THEN 'AGENT'
                             WHEN artifact_type LIKE 'WORKFLOW%' OR artifact_type LIKE 'PIPELINE%' THEN 'WORKFLOW'
                             WHEN artifact_type LIKE 'TOOL%' THEN 'TOOL' END AS node_kind
              FROM explore.process_nodes)""",
    # --- runtime: who actually calls which MCP tool ---
    f"""SELECT {art('AGENT', id_col='agent_id')}, {art('MCP_TOOL', id_col='mcp_tool_id')},
               'CALLS', 'RUNTIME', CAST(sum(call_count) AS DOUBLE), _deployment_id,
               to_json(named_struct('success_count', sum(success_count), 'failure_count', sum(failure_count)))
        FROM explore.mcp_tool_usage_daily WHERE agent_id IS NOT NULL AND mcp_tool_id IS NOT NULL
        GROUP BY _deployment_id, agent_id, mcp_tool_id""",
    f"""SELECT {art('WORKFLOW', id_col='workflow_id')}, {art('MCP_TOOL', id_col='mcp_tool_id')},
               'CALLS', 'RUNTIME', CAST(sum(call_count) AS DOUBLE), _deployment_id,
               to_json(named_struct('success_count', sum(success_count), 'failure_count', sum(failure_count)))
        FROM explore.mcp_tool_usage_daily WHERE workflow_id IS NOT NULL AND mcp_tool_id IS NOT NULL
        GROUP BY _deployment_id, workflow_id, mcp_tool_id""",
    # --- ownership and org hierarchy ---
    f"""SELECT concat(artifact_type, ':', _deployment_id, ':', artifact_id), {OWNER},
               'OWNED_BY', 'DESIGN', 1.0, _deployment_id, {NO_PROPS}
        FROM explore.artifact_catalog""",
    # parent is the next level up; units without a parent hang off the deployment node
    """SELECT concat(level, ':', _deployment_id, ':', lower(trim(name))),
              CASE WHEN parent_level IS NOT NULL
                   THEN concat(parent_level, ':', _deployment_id, ':', lower(trim(parent_name)))
                   ELSE concat('DEPLOYMENT:', _deployment_id) END,
              'PART_OF', 'DESIGN', 1.0, _deployment_id, CAST(NULL AS STRING)
       FROM g_org_parents WHERE name IS NOT NULL""",
    # --- labels (keyword-inferred or steward-mapped) ---
    f"""SELECT concat(artifact_type, ':', _deployment_id, ':', artifact_id), {LABEL_NODE},
               {LABEL_EDGE}, concat('LABEL_', source), 1.0, _deployment_id,
               to_json(named_struct('matched_keyword', matched_keyword))
        FROM explore.artifact_labels""",
    # steward industry mapping on org units: attach it to the mapped level
    f"""SELECT DISTINCT
               CASE industry_manual_scope
                    WHEN 'DEPLOYMENT' THEN concat('DEPLOYMENT:', _deployment_id)
                    WHEN 'ORGANIZATION' THEN {org('ORGANIZATION', 'organization_name')}
                    WHEN 'DOMAIN' THEN {org('BUSINESS_UNIT', 'domain_name')}
                    WHEN 'PROJECT' THEN {org('PROJECT', 'project_name')}
                    ELSE {OWNER} END,
               concat('INDUSTRY:', lower(trim(industry_manual))),
               'IN_INDUSTRY', 'LABEL_MANUAL', 1.0, _deployment_id, {NO_PROPS}
        FROM explore.org_hierarchy WHERE industry_manual IS NOT NULL""",
    # --- clone lineage ---
    f"""SELECT {art('AGENT', id_col='agent_id')}, {art('AGENT', id_col='cloned_from_agent_id')},
               'CLONED_FROM', 'DESIGN', 1.0, _deployment_id, {NO_PROPS}
        FROM explore.agents WHERE cloned_from_agent_id IS NOT NULL""",
    f"""SELECT {art('WORKFLOW', id_col='workflow_id')}, {art('WORKFLOW', id_col='cloned_from_workflow_id')},
               'CLONED_FROM', 'DESIGN', 1.0, _deployment_id, {NO_PROPS}
        FROM explore.workflows WHERE cloned_from_workflow_id IS NOT NULL""",
    f"""SELECT {art('TOOL', id_col='tool_id')}, {art('TOOL', id_col='cloned_from_tool_id')},
               'CLONED_FROM', 'DESIGN', 1.0, _deployment_id, {NO_PROPS}
        FROM explore.tools WHERE cloned_from_tool_id IS NOT NULL""",
    f"""SELECT {art('KNOWLEDGE_BASE', id_col='knowledge_base_id')},
               {art('KNOWLEDGE_BASE', id_col='cloned_from_knowledge_base_id')},
               'CLONED_FROM', 'DESIGN', 1.0, _deployment_id, {NO_PROPS}
        FROM explore.knowledge_bases WHERE cloned_from_knowledge_base_id IS NOT NULL""",
    # --- derived co-occurrence (undirected: stored once with src < dst) ---
    # technologies that appear together in the same agent, counted across all deployments
    """SELECT concat('TECH:', lower(trim(a.label))), concat('TECH:', lower(trim(b.label))),
              'CO_OCCURS', 'DERIVED', CAST(count(DISTINCT a._deployment_id, a.artifact_id) AS DOUBLE),
              CAST(NULL AS STRING),
              to_json(named_struct('artifact_type', 'AGENT',
                                   'deployments', count(DISTINCT a._deployment_id)))
       FROM explore.artifact_labels a
       JOIN explore.artifact_labels b
         ON a._deployment_id = b._deployment_id AND a.artifact_type = b.artifact_type
        AND a.artifact_id = b.artifact_id AND lower(trim(a.label)) < lower(trim(b.label))
       WHERE a.artifact_type = 'AGENT' AND a.dimension = 'TECH_STACK' AND b.dimension = 'TECH_STACK'
       GROUP BY lower(trim(a.label)), lower(trim(b.label))""",
    # tools attached to the same agent
    f"""SELECT {art('TOOL', dep='a._deployment_id', id_col='a.tool_id')},
               {art('TOOL', dep='a._deployment_id', id_col='b.tool_id')},
               'CO_OCCURS', 'DERIVED', CAST(count(DISTINCT a.agent_id) AS DOUBLE), a._deployment_id,
               to_json(named_struct('artifact_type', 'AGENT'))
        FROM explore.agent_tools a
        JOIN explore.agent_tools b
          ON a._deployment_id = b._deployment_id AND a.agent_id = b.agent_id AND a.tool_id < b.tool_id
        GROUP BY a._deployment_id, a.tool_id, b.tool_id""",
]

run("CREATE OR REPLACE TEMP VIEW g_edges_raw AS\n" + "\nUNION ALL\n".join(edge_selects))

# COMMAND ----------

# MAGIC %md ### Write nodes and edges

# COMMAND ----------

run("""
CREATE OR REPLACE TABLE explore.graph_nodes AS
SELECT * FROM g_nodes_raw
""")

run("""
CREATE OR REPLACE TABLE explore.graph_edges AS
WITH e AS (
  SELECT src, dst, edge_type, source, _deployment_id,
         sum(weight) AS weight, max(properties) AS properties
  FROM g_edges_raw
  WHERE src IS NOT NULL AND dst IS NOT NULL AND src <> dst
  GROUP BY src, dst, edge_type, source, _deployment_id
)
SELECT substr(sha2(concat_ws('|', e.edge_type, e.source, e.src, e.dst), 256), 1, 20) AS edge_id,
       e.src, e.dst, e.edge_type, e.source, e.weight, e._deployment_id, e.properties,
       s.node_type AS src_type, d.node_type AS dst_type
FROM e
JOIN explore.graph_nodes s ON s.node_id = e.src
JOIN explore.graph_nodes d ON d.node_id = e.dst
""")

# COMMAND ----------

# MAGIC %md ### Summary ("meta") edges between dimension values

# COMMAND ----------

# Pairs of dimensions shown in the overview. Each row counts agents or workflows that carry both values.
PAIRS = [
    ("INDUSTRY", "SDLC_PHASE"), ("INDUSTRY", "TECH"), ("INDUSTRY", "ARCHETYPE"), ("INDUSTRY", "BUSINESS_FUNCTION"),
    ("BUSINESS_UNIT", "SDLC_PHASE"), ("BUSINESS_UNIT", "TECH"), ("BUSINESS_UNIT", "ARCHETYPE"),
    ("SDLC_PHASE", "TECH"), ("SDLC_PHASE", "ARCHETYPE"), ("BUSINESS_FUNCTION", "ARCHETYPE"),
    ("BUSINESS_FUNCTION", "TECH"), ("ARCHETYPE", "TECH"),
]
pairs_sql = " UNION ALL ".join(f"SELECT '{a}' AS src_type, '{b}' AS dst_type" for a, b in PAIRS)

run(f"""
CREATE OR REPLACE TABLE explore.graph_summary_edges AS
WITH vals AS (
  SELECT _deployment_id, artifact_type, artifact_id, run_count, 'INDUSTRY' AS value_type, v AS value
  FROM explore.artifact_catalog LATERAL VIEW explode(industries) x AS v
  UNION ALL SELECT _deployment_id, artifact_type, artifact_id, run_count, 'SDLC_PHASE', v
  FROM explore.artifact_catalog LATERAL VIEW explode(sdlc_phases) x AS v
  UNION ALL SELECT _deployment_id, artifact_type, artifact_id, run_count, 'TECH', v
  FROM explore.artifact_catalog LATERAL VIEW explode(tech_stack) x AS v
  UNION ALL SELECT _deployment_id, artifact_type, artifact_id, run_count, 'BUSINESS_FUNCTION', v
  FROM explore.artifact_catalog LATERAL VIEW explode(business_functions) x AS v
  UNION ALL SELECT _deployment_id, artifact_type, artifact_id, run_count, 'ARCHETYPE', v
  FROM explore.artifact_catalog LATERAL VIEW explode(archetypes) x AS v
  UNION ALL SELECT _deployment_id, artifact_type, artifact_id, run_count, 'BUSINESS_UNIT', domain_name
  FROM explore.artifact_catalog WHERE domain_name IS NOT NULL
),
v AS (SELECT * FROM vals WHERE artifact_type IN ('AGENT', 'WORKFLOW')),
pairs AS ({pairs_sql})
SELECT a._deployment_id, a.artifact_type,
       p.src_type, a.value AS src_label,
       CASE WHEN p.src_type = 'BUSINESS_UNIT' THEN concat('BUSINESS_UNIT:', a._deployment_id, ':', lower(trim(a.value)))
            ELSE concat(p.src_type, ':', lower(trim(a.value))) END AS src_node_id,
       p.dst_type, b.value AS dst_label,
       CASE WHEN p.dst_type = 'BUSINESS_UNIT' THEN concat('BUSINESS_UNIT:', a._deployment_id, ':', lower(trim(b.value)))
            ELSE concat(p.dst_type, ':', lower(trim(b.value))) END AS dst_node_id,
       count(DISTINCT a.artifact_id) AS artifact_count,
       sum(a.run_count) AS run_count
FROM pairs p
JOIN v a ON a.value_type = p.src_type
JOIN v b ON b.value_type = p.dst_type AND b._deployment_id = a._deployment_id
        AND b.artifact_type = a.artifact_type AND b.artifact_id = a.artifact_id
GROUP BY a._deployment_id, a.artifact_type, p.src_type, a.value, p.dst_type, b.value
""")

# COMMAND ----------

display(spark.sql("""
  SELECT 'node' AS kind, node_type AS type, count(*) AS n FROM explore.graph_nodes GROUP BY node_type
  UNION ALL
  SELECT 'edge', edge_type, count(*) FROM explore.graph_edges GROUP BY edge_type
  UNION ALL
  SELECT 'summary', concat(src_type, ' -> ', dst_type), count(*) FROM explore.graph_summary_edges GROUP BY 2
  ORDER BY kind, n DESC
"""))
