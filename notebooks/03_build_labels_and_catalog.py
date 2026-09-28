# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Keyword labels and the unified artifact catalog
# MAGIC
# MAGIC Builds three tables in `<catalog>.explore` from the curated tables created by `sql/10_explore_tables.sql`:
# MAGIC
# MAGIC | Table | Grain | Purpose |
# MAGIC |---|---|---|
# MAGIC | `artifact_text` | one row per artifact | All descriptive text of an artifact in one lower-cased field. Input for labelling now, and for embeddings and LLM classification later |
# MAGIC | `artifact_labels` | one row per artifact × dimension × label | SDLC phase, tech stack, industry, business function and archetype labels. `source` is `KEYWORD` or `MANUAL` |
# MAGIC | `artifact_catalog` | one row per artifact | Every agent, workflow, tool, MCP server, MCP tool, knowledge base, guardrail and process with org context, usage and label arrays. The main Genie table |
# MAGIC
# MAGIC Industry resolution: a manual mapping (`ref.industry_mapping`) always wins over keyword-inferred industries.
# MAGIC The overridden keyword industries remain visible in `artifact_catalog.industries_inferred`.

# COMMAND ----------

dbutils.widgets.text("catalog", "apdi", "Catalog")
dbutils.widgets.text("taxonomy_path", "../config/keyword_taxonomy.yml", "Keyword taxonomy (relative to this notebook)")

# COMMAND ----------

import hashlib
import os
import re

import yaml
from pyspark.sql import functions as F

CATALOG = dbutils.widgets.get("catalog").strip()
TAXONOMY_PATH = os.path.abspath(dbutils.widgets.get("taxonomy_path").strip())
spark.sql(f"USE CATALOG `{CATALOG}`")

with open(TAXONOMY_PATH, "rb") as fh:
    raw = fh.read()
TAXONOMY = yaml.safe_load(raw)
TAXONOMY_VERSION = hashlib.sha1(raw).hexdigest()[:12]


def keyword_to_regex(keyword):
    """Whole-word, case-insensitive (text is lower-cased) Java regex for one taxonomy keyword."""
    kw = keyword.strip().lower()
    wildcard = kw.endswith("*")
    kw = kw.rstrip("*")
    parts = [re.escape(p) for p in re.split(r"[\s_\-]+", kw) if p]
    body = r"[\s_\-]*".join(parts) + (r"[a-z0-9]*" if wildcard else "")
    return r"(?<![a-z0-9])" + body + r"(?![a-z0-9])"


taxonomy_rows = []
for dimension, spec in TAXONOMY["dimensions"].items():
    for item in spec["labels"]:
        alternatives = [keyword_to_regex(k) for k in item.get("keywords", [])] + list(item.get("patterns", []))
        pattern = "(" + "|".join(alternatives) + ")"
        taxonomy_rows.append((dimension, item["label"], item.get("category"), pattern, TAXONOMY_VERSION))

taxonomy_df = spark.createDataFrame(
    taxonomy_rows, "dimension string, label string, category string, pattern string, taxonomy_version string"
)
taxonomy_df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("ref.keyword_taxonomy")
print(f"taxonomy {TAXONOMY_VERSION}: {len(taxonomy_rows)} labels")

# COMMAND ----------

# MAGIC %md ### Artifact text

# COMMAND ----------

spark.sql("""
CREATE OR REPLACE TABLE explore.artifact_text AS
SELECT _deployment_id, 'AGENT' AS artifact_type, CAST(agent_id AS BIGINT) AS artifact_id, agent_name AS artifact_name,
       lower(concat_ws(' | ', agent_name, role, goal, description, expected_output, backstory, tags, agent_category,
                       array_join(tool_names, ', '), array_join(knowledge_base_names, ', '))) AS text
FROM explore.agents
UNION ALL
SELECT _deployment_id, 'WORKFLOW', CAST(workflow_id AS BIGINT), workflow_name,
       lower(concat_ws(' | ', workflow_name, description, tags, agent_chain, array_join(agent_roles, ', '),
                       array_join(tool_names, ', '), array_join(knowledge_base_names, ', ')))
FROM explore.workflows
UNION ALL
SELECT _deployment_id, 'TOOL', CAST(tool_id AS BIGINT), tool_name,
       lower(concat_ws(' | ', tool_name, tool_description, tags, tool_type, function_type, methodology,
                       array_join(parameter_names, ', ')))
FROM explore.tools
UNION ALL
SELECT _deployment_id, 'MCP_SERVER', CAST(server_id AS BIGINT), server_name,
       lower(concat_ws(' | ', server_name, display_name, description, category, tags, array_join(tool_names, ', ')))
FROM explore.mcp_servers
UNION ALL
SELECT _deployment_id, 'MCP_TOOL', CAST(mcp_tool_id AS BIGINT), tool_name,
       lower(concat_ws(' | ', tool_name, display_name, description, category, subcategory, tags, server_name))
FROM explore.mcp_tools
UNION ALL
SELECT _deployment_id, 'KNOWLEDGE_BASE', CAST(knowledge_base_id AS BIGINT), knowledge_base_name,
       lower(concat_ws(' | ', knowledge_base_name, description, kb_type, function_type, methodology, tags,
                       array_join(file_types, ', ')))
FROM explore.knowledge_bases
UNION ALL
SELECT _deployment_id, 'GUARDRAIL', CAST(guardrail_id AS BIGINT), guardrail_name,
       lower(concat_ws(' | ', guardrail_name, description, guardrail_type, tags))
FROM explore.guardrails
UNION ALL
SELECT _deployment_id, 'PROCESS', CAST(process_id AS BIGINT), process_name,
       lower(concat_ws(' | ', process_name, description, practice_area, array_join(linked_artifact_names, ', ')))
FROM explore.processes
WHERE is_latest_version
""")

# COMMAND ----------

# MAGIC %md ### Base catalog rows (common columns for every artifact type)

# COMMAND ----------

spark.sql("""
CREATE OR REPLACE TEMP VIEW catalog_base AS
WITH base AS (
  SELECT _deployment_id, 'AGENT' AS artifact_type, CAST(agent_id AS BIGINT) AS artifact_id, agent_name AS artifact_name,
         COALESCE(description, goal) AS description, status, is_golden, tags,
         organization_name, domain_name, project_name, team_name, realm_name, practice_area, industry_manual,
         concat(COALESCE(tool_names, array()), COALESCE(knowledge_base_names, array())) AS related_names,
         CAST(run_count AS BIGINT) AS run_count, CAST(run_count_30d AS BIGINT) AS run_count_30d,
         CAST(avg_user_rating AS DOUBLE) AS avg_user_rating, created_at, created_by_user_id
  FROM explore.agents
  UNION ALL
  SELECT _deployment_id, 'WORKFLOW', CAST(workflow_id AS BIGINT), workflow_name,
         description, status, is_golden, tags,
         organization_name, domain_name, project_name, team_name, realm_name, practice_area, industry_manual,
         CASE WHEN agent_chain IS NULL THEN array() ELSE split(agent_chain, ' -> ') END,
         run_count, run_count_30d, avg_user_rating, created_at, created_by_user_id
  FROM explore.workflows
  UNION ALL
  SELECT _deployment_id, 'TOOL', CAST(tool_id AS BIGINT), tool_name,
         tool_description, status, CAST(NULL AS BOOLEAN), tags,
         organization_name, domain_name, project_name, team_name, realm_name, practice_area, industry_manual,
         COALESCE(agent_names, array()),
         run_count, run_count_30d, avg_user_rating, created_at, created_by_user_id
  FROM explore.tools
  UNION ALL
  SELECT _deployment_id, 'MCP_SERVER', CAST(server_id AS BIGINT), server_name,
         description, status, CAST(NULL AS BOOLEAN), tags,
         CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), team_name, CAST(NULL AS STRING),
         CAST(NULL AS STRING), CAST(NULL AS STRING),
         COALESCE(tool_names, array()),
         call_count, CAST(NULL AS BIGINT), CAST(NULL AS DOUBLE), created_at, CAST(NULL AS INT)
  FROM explore.mcp_servers
  UNION ALL
  SELECT _deployment_id, 'MCP_TOOL', CAST(mcp_tool_id AS BIGINT), tool_name,
         description, CASE WHEN is_deprecated THEN 'DEPRECATED' WHEN is_active THEN 'ACTIVE' ELSE 'INACTIVE' END,
         CAST(NULL AS BOOLEAN), tags,
         CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING),
         CAST(NULL AS STRING), CAST(NULL AS STRING),
         CASE WHEN server_name IS NULL THEN array() ELSE array(server_name) END,
         call_count, CAST(NULL AS BIGINT), CAST(NULL AS DOUBLE), created_at, CAST(NULL AS INT)
  FROM explore.mcp_tools
  UNION ALL
  SELECT _deployment_id, 'KNOWLEDGE_BASE', CAST(knowledge_base_id AS BIGINT), knowledge_base_name,
         description, status, CAST(NULL AS BOOLEAN), tags,
         organization_name, domain_name, project_name, team_name, realm_name, practice_area, industry_manual,
         COALESCE(agent_names, array()),
         CAST(NULL AS BIGINT), CAST(NULL AS BIGINT), CAST(NULL AS DOUBLE), created_at, created_by_user_id
  FROM explore.knowledge_bases
  UNION ALL
  SELECT _deployment_id, 'GUARDRAIL', CAST(guardrail_id AS BIGINT), guardrail_name,
         description, status, CAST(NULL AS BOOLEAN), tags,
         organization_name, domain_name, CAST(NULL AS STRING), team_name, realm_name, practice_area,
         CAST(NULL AS STRING),
         COALESCE(agent_names, array()),
         CAST(NULL AS BIGINT), CAST(NULL AS BIGINT), CAST(NULL AS DOUBLE), created_at, CAST(NULL AS INT)
  FROM explore.guardrails
  UNION ALL
  SELECT _deployment_id, 'PROCESS', CAST(process_id AS BIGINT), process_name,
         description, CAST(status_code AS STRING), CAST(NULL AS BOOLEAN), CAST(NULL AS STRING),
         CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), realm,
         practice_area, CAST(NULL AS STRING),
         COALESCE(linked_artifact_names, array()),
         run_count, CAST(NULL AS BIGINT), CAST(NULL AS DOUBLE), created_at, CAST(NULL AS INT)
  FROM explore.processes
  WHERE is_latest_version
)
SELECT b._deployment_id, b.artifact_type, b.artifact_id, b.artifact_name, b.description, b.status, b.is_golden,
       b.tags, b.organization_name, b.domain_name, b.project_name, b.team_name, b.realm_name, b.practice_area,
       COALESCE(b.industry_manual, od.industry_manual) AS industry_manual,
       b.related_names, b.run_count, b.run_count_30d, b.avg_user_rating, b.created_at, b.created_by_user_id
FROM base b
LEFT JOIN explore.org_hierarchy od ON od._deployment_id = b._deployment_id AND od.realm_id IS NULL
""")

# COMMAND ----------

# MAGIC %md ### Labels

# COMMAND ----------

keyword_labels = (
    spark.table("explore.artifact_text").alias("t")
    .join(F.broadcast(spark.table("ref.keyword_taxonomy")).alias("k"), F.expr("t.text RLIKE k.pattern"))
    .select(
        "t._deployment_id", "t.artifact_type", "t.artifact_id", "t.artifact_name",
        "k.dimension", "k.label", "k.category",
        F.expr("regexp_extract(t.text, k.pattern, 1)").alias("matched_keyword"),
        F.lit("KEYWORD").alias("source"),
        "k.taxonomy_version",
    )
)
keyword_labels.createOrReplaceTempView("keyword_labels")

spark.sql("""
CREATE OR REPLACE TABLE explore.artifact_labels AS
SELECT kl.*
FROM keyword_labels kl
LEFT JOIN catalog_base b
  ON b._deployment_id = kl._deployment_id AND b.artifact_type = kl.artifact_type AND b.artifact_id = kl.artifact_id
WHERE kl.dimension <> 'INDUSTRY' OR b.industry_manual IS NULL
UNION ALL
SELECT b._deployment_id, b.artifact_type, b.artifact_id, b.artifact_name,
       'INDUSTRY' AS dimension, b.industry_manual AS label, CAST(NULL AS STRING) AS category,
       CAST(NULL AS STRING) AS matched_keyword, 'MANUAL' AS source, CAST(NULL AS STRING) AS taxonomy_version
FROM catalog_base b
WHERE b.industry_manual IS NOT NULL
""")

# COMMAND ----------

# MAGIC %md ### Unified catalog

# COMMAND ----------

spark.sql("""
CREATE OR REPLACE TABLE explore.artifact_catalog AS
WITH lab AS (
  SELECT _deployment_id, artifact_type, artifact_id,
         array_sort(collect_set(CASE WHEN dimension = 'SDLC_PHASE'        THEN label END)) AS sdlc_phases,
         array_sort(collect_set(CASE WHEN dimension = 'TECH_STACK'        THEN label END)) AS tech_stack,
         array_sort(collect_set(CASE WHEN dimension = 'TECH_STACK'        THEN category END)) AS tech_categories,
         array_sort(collect_set(CASE WHEN dimension = 'BUSINESS_FUNCTION' THEN label END)) AS business_functions,
         array_sort(collect_set(CASE WHEN dimension = 'AGENT_ARCHETYPE'   THEN label END)) AS archetypes
  FROM explore.artifact_labels
  GROUP BY _deployment_id, artifact_type, artifact_id
),
ind AS (
  SELECT _deployment_id, artifact_type, artifact_id, array_sort(collect_set(label)) AS industries_inferred
  FROM keyword_labels WHERE dimension = 'INDUSTRY'
  GROUP BY _deployment_id, artifact_type, artifact_id
)
SELECT
  b._deployment_id, b.artifact_type, b.artifact_id, b.artifact_name, b.description, b.status, b.is_golden, b.tags,
  b.organization_name, b.domain_name, b.project_name, b.team_name, b.realm_name, b.practice_area,
  CASE WHEN b.industry_manual IS NOT NULL THEN array(b.industry_manual)
       ELSE COALESCE(ind.industries_inferred, array()) END AS industries,
  CASE WHEN b.industry_manual IS NOT NULL THEN 'MANUAL'
       WHEN size(ind.industries_inferred) > 0 THEN 'INFERRED_KEYWORD'
       ELSE 'UNCLASSIFIED' END AS industry_source,
  COALESCE(ind.industries_inferred, array()) AS industries_inferred,
  COALESCE(lab.sdlc_phases, array())        AS sdlc_phases,
  COALESCE(lab.tech_stack, array())         AS tech_stack,
  COALESCE(lab.tech_categories, array())    AS tech_categories,
  COALESCE(lab.business_functions, array()) AS business_functions,
  COALESCE(lab.archetypes, array())         AS archetypes,
  b.related_names,
  size(b.related_names) AS related_count,
  b.run_count, b.run_count_30d, b.avg_user_rating,
  b.created_by_user_id, b.created_at
FROM catalog_base b
LEFT JOIN lab ON lab._deployment_id = b._deployment_id AND lab.artifact_type = b.artifact_type AND lab.artifact_id = b.artifact_id
LEFT JOIN ind ON ind._deployment_id = b._deployment_id AND ind.artifact_type = b.artifact_type AND ind.artifact_id = b.artifact_id
""")

display(spark.sql("""
  SELECT artifact_type, count(*) AS artifacts,
         count_if(size(sdlc_phases) > 0)   AS with_sdlc_phase,
         count_if(size(tech_stack) > 0)    AS with_tech_stack,
         count_if(industry_source <> 'UNCLASSIFIED') AS with_industry,
         count_if(size(business_functions) > 0) AS with_business_function
  FROM explore.artifact_catalog GROUP BY artifact_type ORDER BY artifacts DESC
"""))
