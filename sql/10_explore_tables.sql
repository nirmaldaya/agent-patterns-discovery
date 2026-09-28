-- APDI quick solution - curated exploration tables (explore schema)
--
-- Rebuilt from the raw_* schemas on every run by notebooks/run_sql_file.py
-- (USE CATALOG <catalog> is issued first, so names here are schema-qualified only).
-- Every table carries _deployment_id and every join matches on it, so data from
-- further customer deployments can be loaded into the same tables later.
--
-- Conventions
--   * soft-deleted rows are excluded
--   * org hierarchy (organization > domain > project > team) is resolved from realm_id,
--     falling back to the artifact's own team_id / domain_id
--   * industry_manual comes from ref.industry_mapping (see sql/00_setup.sql)
--   * platform_*_counter columns are the counters stored on the source row, while
--     run_* columns are recomputed from the execution tables
--
-- Keep every statement free of semicolons inside comments or literals: the runner
-- splits this file on semicolons.


-- =============================================================================
-- Organisation hierarchy per realm, plus one row per deployment (realm_id NULL)
-- carrying the deployment-wide industry mapping
-- =============================================================================
CREATE OR REPLACE TABLE explore.org_hierarchy AS
WITH realms AS (
  SELECT r._deployment_id, r.id AS realm_id, r.realm_name,
         o.id AS organization_id, o.organization_name,
         d.id AS domain_id, d.domain_name,
         p.id AS project_id, p.project_name,
         t.id AS team_id, t.team_name
  FROM raw_rbac.realm r
  LEFT JOIN raw_rbac.team t         ON t._deployment_id = r._deployment_id AND t.id = r.team_id
  LEFT JOIN raw_rbac.project p      ON p._deployment_id = r._deployment_id AND p.id = COALESCE(r.project_id, t.project_id)
  LEFT JOIN raw_rbac.domain d       ON d._deployment_id = r._deployment_id AND d.id = COALESCE(r.domain_id, p.domain_id)
  LEFT JOIN raw_rbac.organization o ON o._deployment_id = r._deployment_id AND o.id = COALESCE(r.organization_id, d.organization_id)
  WHERE NOT COALESCE(r.is_deleted, false)
),
deployments AS (
  SELECT _deployment_id FROM raw_core.agents
  UNION SELECT _deployment_id FROM raw_core.workflows
  UNION SELECT _deployment_id FROM raw_core.tools
  UNION SELECT _deployment_id FROM raw_rbac.realm
),
scopes AS (
  SELECT * FROM realms
  UNION ALL
  SELECT _deployment_id, CAST(NULL AS INT), CAST(NULL AS STRING),
         CAST(NULL AS INT), CAST(NULL AS STRING), CAST(NULL AS INT), CAST(NULL AS STRING),
         CAST(NULL AS INT), CAST(NULL AS STRING), CAST(NULL AS INT), CAST(NULL AS STRING)
  FROM deployments
),
candidates AS (
  SELECT s._deployment_id, s.realm_id, m.industry, upper(m.scope_level) AS scope_level,
         CASE upper(m.scope_level)
           WHEN 'REALM' THEN 1 WHEN 'TEAM' THEN 2 WHEN 'PROJECT' THEN 3
           WHEN 'DOMAIN' THEN 4 WHEN 'ORGANIZATION' THEN 5 ELSE 6 END AS specificity,
         CASE WHEN m.deployment_id IS NULL THEN 1 ELSE 0 END AS is_global,
         m.mapped_at
  FROM scopes s
  JOIN ref.industry_mapping m
    ON (m.deployment_id IS NULL OR m.deployment_id = s._deployment_id)
   AND (   (upper(m.scope_level) = 'REALM'        AND lower(m.scope_name) = lower(s.realm_name))
        OR (upper(m.scope_level) = 'TEAM'         AND lower(m.scope_name) = lower(s.team_name))
        OR (upper(m.scope_level) = 'PROJECT'      AND lower(m.scope_name) = lower(s.project_name))
        OR (upper(m.scope_level) = 'DOMAIN'       AND lower(m.scope_name) = lower(s.domain_name))
        OR (upper(m.scope_level) = 'ORGANIZATION' AND lower(m.scope_name) = lower(s.organization_name))
        OR  upper(m.scope_level) = 'DEPLOYMENT')
),
best AS (
  SELECT * FROM (
    SELECT c.*, row_number() OVER (PARTITION BY _deployment_id, realm_id
                                   ORDER BY specificity, is_global, mapped_at DESC) AS rn
    FROM candidates c
  ) WHERE rn = 1
)
SELECT s.*, b.industry AS industry_manual, b.scope_level AS industry_manual_scope
FROM scopes s
LEFT JOIN best b ON b._deployment_id = s._deployment_id AND b.realm_id <=> s.realm_id;


-- =============================================================================
-- Composition bridges
-- =============================================================================
CREATE OR REPLACE TABLE explore.agent_tools AS
SELECT lnk._deployment_id, lnk.agent_id, a.name AS agent_name,
       lnk.tool_id, t.tool_name, t.tool_type, t.function_type, t.status AS tool_status,
       lnk.created_at AS linked_at
FROM raw_core.agents_tools lnk
JOIN raw_core.agents a     ON a._deployment_id = lnk._deployment_id AND a.id = lnk.agent_id
                          AND NOT COALESCE(a.is_deleted, false)
LEFT JOIN raw_core.tools t ON t._deployment_id = lnk._deployment_id AND t.id = lnk.tool_id;

CREATE OR REPLACE TABLE explore.agent_knowledge_bases AS
SELECT lnk._deployment_id, lnk.agent_id, a.name AS agent_name,
       lnk.knowledge_base_id, kb.collection_name AS knowledge_base_name,
       kb.type AS kb_type, kb.vector_db, lnk.created_at AS linked_at
FROM raw_core.agents_knowledge_bases lnk
JOIN raw_core.agents a ON a._deployment_id = lnk._deployment_id AND a.id = lnk.agent_id
                      AND NOT COALESCE(a.is_deleted, false)
LEFT JOIN raw_core.knowledgebase_collection_mst kb
       ON kb._deployment_id = lnk._deployment_id AND kb.id = lnk.knowledge_base_id;

CREATE OR REPLACE TABLE explore.agent_guardrails AS
SELECT lnk._deployment_id, CAST(lnk.agent_id AS INT) AS agent_id, a.name AS agent_name,
       CAST(lnk.guardrail_id AS INT) AS guardrail_id, g.name AS guardrail_name, g.guardrail_type
FROM raw_core.agent_guardrails lnk
JOIN raw_core.agents a ON a._deployment_id = lnk._deployment_id AND a.id = lnk.agent_id
                      AND NOT COALESCE(a.is_deleted, false)
LEFT JOIN raw_core.guardrail_mst g ON g._deployment_id = lnk._deployment_id AND g.id = lnk.guardrail_id;

CREATE OR REPLACE TABLE explore.workflow_agents AS
SELECT wa._deployment_id, wa.workflow_id, w.name AS workflow_name,
       wa.serial AS step_order, wa.agent_id, a.name AS agent_name, a.role AS agent_role
FROM raw_core.workflow_agents wa
JOIN raw_core.workflows w ON w._deployment_id = wa._deployment_id AND w.id = wa.workflow_id
                         AND NOT COALESCE(w.isdeleted, false)
LEFT JOIN raw_core.agents a ON a._deployment_id = wa._deployment_id AND a.id = wa.agent_id;


-- =============================================================================
-- Agents
-- =============================================================================
CREATE OR REPLACE TABLE explore.agents AS
WITH tool_agg AS (
  SELECT _deployment_id, agent_id, count(DISTINCT tool_id) AS tool_count,
         array_sort(collect_set(tool_name)) AS tool_names
  FROM explore.agent_tools GROUP BY _deployment_id, agent_id
),
kb_agg AS (
  SELECT _deployment_id, agent_id, count(DISTINCT knowledge_base_id) AS knowledge_base_count,
         array_sort(collect_set(knowledge_base_name)) AS knowledge_base_names
  FROM explore.agent_knowledge_bases GROUP BY _deployment_id, agent_id
),
gr_agg AS (
  SELECT _deployment_id, agent_id, count(DISTINCT guardrail_id) AS guardrail_count,
         array_sort(collect_set(guardrail_name)) AS guardrail_names
  FROM explore.agent_guardrails GROUP BY _deployment_id, agent_id
),
wf_agg AS (
  SELECT _deployment_id, agent_id, count(DISTINCT workflow_id) AS workflow_count,
         array_sort(collect_set(workflow_name)) AS workflow_names
  FROM explore.workflow_agents GROUP BY _deployment_id, agent_id
),
rating_agg AS (
  SELECT _deployment_id, CAST(agent_id AS INT) AS agent_id,
         round(avg(rating), 2) AS avg_user_rating, count(rating) AS rating_count
  FROM raw_core.agent_user_ratings GROUP BY _deployment_id, agent_id
),
fav_agg AS (
  SELECT _deployment_id, agent_id, count(*) AS favourite_count
  FROM raw_core.agent_favourites GROUP BY _deployment_id, agent_id
),
run_agg AS (
  SELECT _deployment_id, artifact_id AS agent_id,
         count(*) AS run_count,
         count_if(start_time >= current_timestamp() - INTERVAL 30 DAYS) AS run_count_30d,
         count(DISTINCT executor_id) AS distinct_runner_count,
         max(start_time) AS last_run_at,
         sum(tokens_used) AS total_tokens,
         sum(compute_cost) AS total_cost,
         round(avg(rating), 2) AS avg_run_rating
  FROM raw_core.artifact_executions
  WHERE upper(artifact_type) = 'AGENT'
  GROUP BY _deployment_id, artifact_id
),
job_agg AS (
  SELECT _deployment_id, agent_id,
         count(*) AS job_count,
         count_if(upper(status) = 'SUCCESS') AS job_success_count,
         count_if(upper(status) = 'FAILED') AS job_failed_count
  FROM raw_core.agent_execution_job GROUP BY _deployment_id, agent_id
)
SELECT
  a._deployment_id,
  a.id                  AS agent_id,
  a.name                AS agent_name,
  a.role, a.goal, a.description, a.expected_output, a.backstory,
  a.status, a.agent_type,
  a.isgolden            AS is_golden,
  a.version,
  a.parent_id           AS cloned_from_agent_id,
  cat.name              AS agent_category,
  pa.name               AS practice_area,
  a.tags,
  COALESCE(gm.display_name, gm.model_key, m.model) AS model_name,
  COALESCE(mp.name, m.ai_engine)                   AS model_provider,
  oh.organization_name,
  COALESCE(oh.domain_name, dm.domain_name) AS domain_name,
  oh.project_name,
  COALESCE(oh.team_name, tm.team_name)     AS team_name,
  oh.realm_name,
  COALESCE(oh.industry_manual, od.industry_manual) AS industry_manual,
  COALESCE(ta.tool_count, 0)           AS tool_count,           ta.tool_names,
  COALESCE(ka.knowledge_base_count, 0) AS knowledge_base_count, ka.knowledge_base_names,
  COALESCE(ga.guardrail_count, 0)      AS guardrail_count,      ga.guardrail_names,
  COALESCE(wa.workflow_count, 0)       AS workflow_count,       wa.workflow_names,
  COALESCE(ra.run_count, 0)             AS run_count,
  COALESCE(ra.run_count_30d, 0)         AS run_count_30d,
  COALESCE(ra.distinct_runner_count, 0) AS distinct_runner_count,
  ra.last_run_at, ra.total_tokens, ra.total_cost, ra.avg_run_rating,
  COALESCE(ja.job_count, 0)         AS job_count,
  COALESCE(ja.job_success_count, 0) AS job_success_count,
  COALESCE(ja.job_failed_count, 0)  AS job_failed_count,
  rt.avg_user_rating,
  COALESCE(rt.rating_count, 0)    AS rating_count,
  COALESCE(fa.favourite_count, 0) AS favourite_count,
  a.executions          AS platform_execution_counter,
  a.views               AS platform_view_counter,
  a.unique_users_count  AS platform_unique_users_counter,
  a.success_rate        AS platform_success_rate,
  a.efficiency_rating, a.trending_score,
  a.created_by          AS created_by_user_id,
  u.department          AS creator_department,
  u.job_title           AS creator_job_title,
  a.created_at, a.approved_at, a.modified_at, a.last_executed_at
FROM raw_core.agents a
LEFT JOIN raw_core.agent_categories cat ON cat._deployment_id = a._deployment_id AND cat.id = a.category_id
LEFT JOIN raw_rbac.practice_area pa     ON pa._deployment_id = a._deployment_id AND pa.id = a.practice_area
LEFT JOIN raw_core.model m              ON m._deployment_id = a._deployment_id AND m.id = a.model_id
LEFT JOIN raw_core.models gm            ON gm._deployment_id = a._deployment_id AND gm.model_id = a.gateway_model_id
LEFT JOIN raw_core.model_providers mp   ON mp._deployment_id = gm._deployment_id AND mp.provider_id = gm.provider_id
LEFT JOIN explore.org_hierarchy oh      ON oh._deployment_id = a._deployment_id AND oh.realm_id = a.realm_id
LEFT JOIN explore.org_hierarchy od      ON od._deployment_id = a._deployment_id AND od.realm_id IS NULL
LEFT JOIN raw_rbac.team tm              ON tm._deployment_id = a._deployment_id AND tm.id = a.team_id
LEFT JOIN raw_rbac.domain dm            ON dm._deployment_id = a._deployment_id AND dm.id = a.domain_id
LEFT JOIN raw_rbac.users u              ON u._deployment_id = a._deployment_id AND u.user_id = a.created_by
LEFT JOIN tool_agg ta   ON ta._deployment_id = a._deployment_id AND ta.agent_id = a.id
LEFT JOIN kb_agg ka     ON ka._deployment_id = a._deployment_id AND ka.agent_id = a.id
LEFT JOIN gr_agg ga     ON ga._deployment_id = a._deployment_id AND ga.agent_id = a.id
LEFT JOIN wf_agg wa     ON wa._deployment_id = a._deployment_id AND wa.agent_id = a.id
LEFT JOIN rating_agg rt ON rt._deployment_id = a._deployment_id AND rt.agent_id = a.id
LEFT JOIN fav_agg fa    ON fa._deployment_id = a._deployment_id AND fa.agent_id = a.id
LEFT JOIN run_agg ra    ON ra._deployment_id = a._deployment_id AND ra.agent_id = a.id
LEFT JOIN job_agg ja    ON ja._deployment_id = a._deployment_id AND ja.agent_id = a.id
WHERE NOT COALESCE(a.is_deleted, false);


-- =============================================================================
-- Workflows (crewAI crews / pipelines)
-- =============================================================================
CREATE OR REPLACE TABLE explore.workflows AS
WITH steps AS (
  SELECT _deployment_id, workflow_id,
         count(*) AS agent_count,
         array_join(transform(array_sort(collect_list(struct(COALESCE(step_order, 0) AS step_order, agent_name))),
                              s -> s.agent_name), ' -> ') AS agent_chain,
         array_sort(collect_set(agent_role)) AS agent_roles
  FROM explore.workflow_agents GROUP BY _deployment_id, workflow_id
),
wf_tools AS (
  SELECT wa._deployment_id, wa.workflow_id,
         count(DISTINCT t.tool_id) AS tool_count,
         array_sort(collect_set(t.tool_name)) AS tool_names
  FROM explore.workflow_agents wa
  JOIN explore.agent_tools t ON t._deployment_id = wa._deployment_id AND t.agent_id = wa.agent_id
  GROUP BY wa._deployment_id, wa.workflow_id
),
wf_kbs AS (
  SELECT wa._deployment_id, wa.workflow_id,
         count(DISTINCT k.knowledge_base_id) AS knowledge_base_count,
         array_sort(collect_set(k.knowledge_base_name)) AS knowledge_base_names
  FROM explore.workflow_agents wa
  JOIN explore.agent_knowledge_bases k ON k._deployment_id = wa._deployment_id AND k.agent_id = wa.agent_id
  GROUP BY wa._deployment_id, wa.workflow_id
),
rating_agg AS (
  SELECT _deployment_id, CAST(workflow_id AS INT) AS workflow_id,
         round(avg(rating), 2) AS avg_user_rating, count(rating) AS rating_count
  FROM raw_core.workflow_user_ratings GROUP BY _deployment_id, workflow_id
),
fav_agg AS (
  SELECT _deployment_id, workflow_id, count(*) AS favourite_count
  FROM raw_core.workflow_favourites GROUP BY _deployment_id, workflow_id
),
run_agg AS (
  SELECT _deployment_id, artifact_id AS workflow_id,
         count(*) AS run_count,
         count_if(start_time >= current_timestamp() - INTERVAL 30 DAYS) AS run_count_30d,
         count(DISTINCT executor_id) AS distinct_runner_count,
         max(start_time) AS last_run_at,
         sum(tokens_used) AS total_tokens,
         sum(compute_cost) AS total_cost,
         round(avg(rating), 2) AS avg_run_rating
  FROM raw_core.artifact_executions
  WHERE upper(artifact_type) IN ('WORKFLOW', 'PIPELINE')
  GROUP BY _deployment_id, artifact_id
),
job_agg AS (
  SELECT _deployment_id, pipelineid AS workflow_id,
         count(*) AS job_count,
         count_if(upper(status) = 'SUCCESS') AS job_success_count,
         count_if(upper(status) = 'FAILED') AS job_failed_count
  FROM raw_core.workflow_execution_job GROUP BY _deployment_id, pipelineid
)
SELECT
  w._deployment_id,
  w.id              AS workflow_id,
  w.name            AS workflow_name,
  w.description,
  w.status,
  w.isgolden        AS is_golden,
  w.version,
  w.parent_id       AS cloned_from_workflow_id,
  pa.name           AS practice_area,
  w.tags,
  oh.organization_name,
  COALESCE(oh.domain_name, dm.domain_name) AS domain_name,
  oh.project_name,
  COALESCE(oh.team_name, tm.team_name)     AS team_name,
  oh.realm_name,
  COALESCE(oh.industry_manual, od.industry_manual) AS industry_manual,
  COALESCE(st.agent_count, 0)          AS agent_count,
  st.agent_chain, st.agent_roles,
  COALESCE(wt.tool_count, 0)           AS tool_count,           wt.tool_names,
  COALESCE(wk.knowledge_base_count, 0) AS knowledge_base_count, wk.knowledge_base_names,
  CASE WHEN COALESCE(st.agent_count, 0) <= 1 THEN 'SINGLE_AGENT'
       WHEN st.agent_count <= 3 THEN 'SHORT_CHAIN'
       ELSE 'LONG_CHAIN' END AS workflow_shape,
  COALESCE(ra.run_count, 0)             AS run_count,
  COALESCE(ra.run_count_30d, 0)         AS run_count_30d,
  COALESCE(ra.distinct_runner_count, 0) AS distinct_runner_count,
  ra.last_run_at, ra.total_tokens, ra.total_cost, ra.avg_run_rating,
  COALESCE(ja.job_count, 0)         AS job_count,
  COALESCE(ja.job_success_count, 0) AS job_success_count,
  COALESCE(ja.job_failed_count, 0)  AS job_failed_count,
  rt.avg_user_rating,
  COALESCE(rt.rating_count, 0)    AS rating_count,
  COALESCE(fa.favourite_count, 0) AS favourite_count,
  w.executions          AS platform_execution_counter,
  w.views               AS platform_view_counter,
  w.unique_users_count  AS platform_unique_users_counter,
  w.success_rate        AS platform_success_rate,
  w.efficiency_rating, w.trending_score,
  w.created_by          AS created_by_user_id,
  u.department          AS creator_department,
  u.job_title           AS creator_job_title,
  w.created_at, w.approved_at, w.modified_at, w.last_executed_at
FROM raw_core.workflows w
LEFT JOIN raw_rbac.practice_area pa ON pa._deployment_id = w._deployment_id AND pa.id = w.practice_area
LEFT JOIN explore.org_hierarchy oh  ON oh._deployment_id = w._deployment_id AND oh.realm_id = w.realm_id
LEFT JOIN explore.org_hierarchy od  ON od._deployment_id = w._deployment_id AND od.realm_id IS NULL
LEFT JOIN raw_rbac.team tm          ON tm._deployment_id = w._deployment_id AND tm.id = w.team_id
LEFT JOIN raw_rbac.domain dm        ON dm._deployment_id = w._deployment_id AND dm.id = w.domain_id
LEFT JOIN raw_rbac.users u          ON u._deployment_id = w._deployment_id AND u.user_id = w.created_by
LEFT JOIN steps st      ON st._deployment_id = w._deployment_id AND st.workflow_id = w.id
LEFT JOIN wf_tools wt   ON wt._deployment_id = w._deployment_id AND wt.workflow_id = w.id
LEFT JOIN wf_kbs wk     ON wk._deployment_id = w._deployment_id AND wk.workflow_id = w.id
LEFT JOIN rating_agg rt ON rt._deployment_id = w._deployment_id AND rt.workflow_id = w.id
LEFT JOIN fav_agg fa    ON fa._deployment_id = w._deployment_id AND fa.workflow_id = w.id
LEFT JOIN run_agg ra    ON ra._deployment_id = w._deployment_id AND ra.workflow_id = w.id
LEFT JOIN job_agg ja    ON ja._deployment_id = w._deployment_id AND ja.workflow_id = w.id
WHERE NOT COALESCE(w.isdeleted, false);


-- =============================================================================
-- Platform tools (core.tools)
-- =============================================================================
CREATE OR REPLACE TABLE explore.tools AS
WITH params AS (
  SELECT _deployment_id, tool_id, count(*) AS parameter_count,
         array_sort(collect_set(parameter_name)) AS parameter_names
  FROM raw_core.tools_parameters GROUP BY _deployment_id, tool_id
),
used AS (
  SELECT _deployment_id, tool_id, count(DISTINCT agent_id) AS agent_count,
         array_sort(collect_set(agent_name)) AS agent_names
  FROM explore.agent_tools GROUP BY _deployment_id, tool_id
),
builtin AS (
  SELECT DISTINCT _deployment_id, lower(trim(tool_name)) AS tool_key FROM raw_core.tools_builtin
),
rating_agg AS (
  SELECT _deployment_id, CAST(tool_id AS INT) AS tool_id,
         round(avg(rating), 2) AS avg_user_rating, count(rating) AS rating_count
  FROM raw_core.tool_user_ratings GROUP BY _deployment_id, tool_id
),
run_agg AS (
  SELECT _deployment_id, artifact_id AS tool_id,
         count(*) AS run_count,
         count_if(start_time >= current_timestamp() - INTERVAL 30 DAYS) AS run_count_30d,
         max(start_time) AS last_run_at
  FROM raw_core.artifact_executions
  WHERE upper(artifact_type) = 'TOOL'
  GROUP BY _deployment_id, artifact_id
)
SELECT
  t._deployment_id,
  t.id               AS tool_id,
  t.tool_name,
  t.tool_description,
  t.tool_type,
  t.function_type,
  t.methodology,
  CASE WHEN lower(t.tool_name) RLIKE '(^|[^a-z])(create|update|delete|add|post|put|set|write|insert|remove|send|assign|close|transition|upload|publish|push|commit|merge)([^a-z]|$)' THEN 'WRITE'
       WHEN lower(t.tool_name) RLIKE '(^|[^a-z])(get|list|search|read|fetch|query|find|describe|retrieve|lookup|download|scrape|browse)([^a-z]|$)' THEN 'READ'
       ELSE 'OTHER' END AS action_type,
  (b.tool_key IS NOT NULL) AS is_builtin,
  t.status,
  t.version,
  t.parent_id        AS cloned_from_tool_id,
  pa.name            AS practice_area,
  t.tags,
  oh.organization_name,
  COALESCE(oh.domain_name, dm.domain_name) AS domain_name,
  oh.project_name,
  COALESCE(oh.team_name, tm.team_name)     AS team_name,
  oh.realm_name,
  COALESCE(oh.industry_manual, od.industry_manual) AS industry_manual,
  COALESCE(pr.parameter_count, 0) AS parameter_count, pr.parameter_names,
  COALESCE(us.agent_count, 0)     AS agent_count,     us.agent_names,
  COALESCE(ra.run_count, 0)       AS run_count,
  COALESCE(ra.run_count_30d, 0)   AS run_count_30d,
  ra.last_run_at,
  rt.avg_user_rating,
  COALESCE(rt.rating_count, 0)    AS rating_count,
  t.executions          AS platform_execution_counter,
  t.views               AS platform_view_counter,
  t.unique_users_count  AS platform_unique_users_counter,
  t.success_rate        AS platform_success_rate,
  t.efficiency_rating, t.trending_score,
  t.created_by          AS created_by_user_id,
  t.created_at, t.approved_at, t.modified_at, t.last_executed_at
FROM raw_core.tools t
LEFT JOIN raw_rbac.practice_area pa ON pa._deployment_id = t._deployment_id AND pa.id = t.practice_area
LEFT JOIN explore.org_hierarchy oh  ON oh._deployment_id = t._deployment_id AND oh.realm_id = t.realm_id
LEFT JOIN explore.org_hierarchy od  ON od._deployment_id = t._deployment_id AND od.realm_id IS NULL
LEFT JOIN raw_rbac.team tm          ON tm._deployment_id = t._deployment_id AND tm.id = t.team_id
LEFT JOIN raw_rbac.domain dm        ON dm._deployment_id = t._deployment_id AND dm.id = t.domain_id
LEFT JOIN builtin b     ON b._deployment_id = t._deployment_id AND b.tool_key = lower(trim(t.tool_name))
LEFT JOIN params pr     ON pr._deployment_id = t._deployment_id AND pr.tool_id = t.id
LEFT JOIN used us       ON us._deployment_id = t._deployment_id AND us.tool_id = t.id
LEFT JOIN rating_agg rt ON rt._deployment_id = t._deployment_id AND rt.tool_id = t.id
LEFT JOIN run_agg ra    ON ra._deployment_id = t._deployment_id AND ra.tool_id = t.id
WHERE NOT COALESCE(t.is_deleted, false);


-- =============================================================================
-- Knowledge bases (RAG collections)
-- =============================================================================
CREATE OR REPLACE TABLE explore.knowledge_bases AS
WITH files AS (
  SELECT _deployment_id, collection_id,
         count(*) AS file_count,
         round(sum(file_size_bytes) / 1048576.0, 2) AS total_size_mb,
         sum(total_embeddings) AS total_embeddings,
         array_sort(collect_set(nullif(lower(regexp_extract(file_name, '\\.([A-Za-z0-9]+)$', 1)), ''))) AS file_types,
         array_sort(collect_set(source)) AS sources
  FROM raw_core.knowledgebase_collection_transaction
  WHERE COALESCE(isactive, true)
  GROUP BY _deployment_id, collection_id
),
used AS (
  SELECT _deployment_id, knowledge_base_id, count(DISTINCT agent_id) AS agent_count,
         array_sort(collect_set(agent_name)) AS agent_names
  FROM explore.agent_knowledge_bases GROUP BY _deployment_id, knowledge_base_id
)
SELECT
  kb._deployment_id,
  kb.id               AS knowledge_base_id,
  kb.collection_name  AS knowledge_base_name,
  kb.description,
  kb.type             AS kb_type,
  kb.vector_db,
  kb.function_type,
  kb.methodology,
  kb.split_size,
  kb.status,
  kb.version,
  kb.parent_id        AS cloned_from_knowledge_base_id,
  pa.name             AS practice_area,
  kb.tags,
  oh.organization_name,
  COALESCE(oh.domain_name, dm.domain_name) AS domain_name,
  oh.project_name,
  COALESCE(oh.team_name, tm.team_name)     AS team_name,
  oh.realm_name,
  COALESCE(oh.industry_manual, od.industry_manual) AS industry_manual,
  COALESCE(f.file_count, 0) AS file_count, f.total_size_mb, f.total_embeddings, f.file_types, f.sources,
  COALESCE(us.agent_count, 0) AS agent_count, us.agent_names,
  kb.executions          AS platform_execution_counter,
  kb.views               AS platform_view_counter,
  kb.efficiency_rating,
  kb.created_by          AS created_by_user_id,
  kb.created_date        AS created_at,
  kb.approved_at, kb.modified_at
FROM raw_core.knowledgebase_collection_mst kb
LEFT JOIN raw_rbac.practice_area pa ON pa._deployment_id = kb._deployment_id AND pa.id = kb.practice_area
LEFT JOIN explore.org_hierarchy oh  ON oh._deployment_id = kb._deployment_id AND oh.realm_id = kb.realm_id
LEFT JOIN explore.org_hierarchy od  ON od._deployment_id = kb._deployment_id AND od.realm_id IS NULL
LEFT JOIN raw_rbac.team tm          ON tm._deployment_id = kb._deployment_id AND tm.id = kb.team_id
LEFT JOIN raw_rbac.domain dm        ON dm._deployment_id = kb._deployment_id AND dm.id = kb.domain_id
LEFT JOIN files f  ON f._deployment_id = kb._deployment_id AND f.collection_id = kb.id
LEFT JOIN used us  ON us._deployment_id = kb._deployment_id AND us.knowledge_base_id = kb.id
WHERE COALESCE(kb.isactive, true);


-- =============================================================================
-- Guardrails
-- =============================================================================
CREATE OR REPLACE TABLE explore.guardrails AS
WITH used AS (
  SELECT _deployment_id, guardrail_id, count(DISTINCT agent_id) AS agent_count,
         array_sort(collect_set(agent_name)) AS agent_names
  FROM explore.agent_guardrails GROUP BY _deployment_id, guardrail_id
)
SELECT
  g._deployment_id,
  g.id              AS guardrail_id,
  g.name            AS guardrail_name,
  g.description,
  g.guardrail_type,
  g.config_key,
  g.chatbot         AS is_chatbot_guardrail,
  g.function_type,
  g.methodology,
  g.status,
  g.version,
  pa.name           AS practice_area,
  g.tags,
  oh.organization_name,
  COALESCE(oh.domain_name, dm.domain_name) AS domain_name,
  COALESCE(oh.team_name, tm.team_name)     AS team_name,
  oh.realm_name,
  COALESCE(us.agent_count, 0) AS agent_count, us.agent_names,
  g.executions      AS platform_execution_counter,
  g.created_at, g.approved_at, g.modified_at
FROM raw_core.guardrail_mst g
LEFT JOIN raw_rbac.practice_area pa ON pa._deployment_id = g._deployment_id AND pa.id = g.practice_area
LEFT JOIN explore.org_hierarchy oh  ON oh._deployment_id = g._deployment_id AND oh.realm_id = g.realm_id
LEFT JOIN raw_rbac.team tm          ON tm._deployment_id = g._deployment_id AND tm.id = g.team_id
LEFT JOIN raw_rbac.domain dm        ON dm._deployment_id = g._deployment_id AND dm.id = g.domain_id
LEFT JOIN used us ON us._deployment_id = g._deployment_id AND us.guardrail_id = g.id
WHERE NOT COALESCE(g.is_deleted, false);


-- =============================================================================
-- MCP servers and MCP tools
-- =============================================================================
CREATE OR REPLACE TABLE explore.mcp_servers AS
WITH tl AS (
  SELECT _deployment_id, server_id, count(*) AS tool_count, array_sort(collect_set(name)) AS tool_names
  FROM raw_mcp.tools WHERE NOT COALESCE(is_deleted, false)
  GROUP BY _deployment_id, server_id
),
ex AS (
  SELECT _deployment_id, server_id,
         count(*) AS call_count,
         count_if(success) AS success_count,
         count(DISTINCT user_id) AS distinct_user_count,
         count(DISTINCT agent_id) AS distinct_agent_count,
         count(DISTINCT workflow_id) AS distinct_workflow_count,
         max(executed_at) AS last_called_at
  FROM raw_mcp.tool_execution_audit GROUP BY _deployment_id, server_id
),
dep AS (
  SELECT _deployment_id, server_id, array_sort(collect_set(deployment_environment)) AS deployment_environments
  FROM raw_mcp.deployments GROUP BY _deployment_id, server_id
)
SELECT
  s._deployment_id,
  s.id               AS server_id,
  s.name             AS server_name,
  s.display_name,
  s.description,
  s.category,
  array_join(s.tags, ', ')            AS tags,
  s.server_type,
  array_join(s.transport_types, ', ') AS transport_types,
  s.authentication_type,
  s.requires_authentication,
  s.status,
  s.health_status,
  s.risk_score,
  s.organization_id,
  s.team_name,
  s.version,
  s.documentation_url,
  d.deployment_environments,
  COALESCE(tl.tool_count, 0) AS tool_count, tl.tool_names,
  COALESCE(ex.call_count, 0) AS call_count,
  COALESCE(ex.success_count, 0) AS success_count,
  round(100.0 * ex.success_count / nullif(ex.call_count, 0), 2) AS success_rate_pct,
  COALESCE(ex.distinct_user_count, 0)     AS distinct_user_count,
  COALESCE(ex.distinct_agent_count, 0)    AS distinct_agent_count,
  COALESCE(ex.distinct_workflow_count, 0) AS distinct_workflow_count,
  ex.last_called_at,
  s.created_at, s.updated_at
FROM raw_mcp.servers s
LEFT JOIN tl ON tl._deployment_id = s._deployment_id AND tl.server_id = s.id
LEFT JOIN ex ON ex._deployment_id = s._deployment_id AND ex.server_id = s.id
LEFT JOIN dep d ON d._deployment_id = s._deployment_id AND d.server_id = s.id
WHERE NOT COALESCE(s.is_deleted, false);

CREATE OR REPLACE TABLE explore.mcp_tools AS
WITH ex AS (
  SELECT _deployment_id, tool_id,
         count(*) AS call_count,
         count_if(success) AS success_count,
         round(avg(execution_time_ms)) AS avg_execution_ms,
         count(DISTINCT user_id) AS distinct_user_count,
         count(DISTINCT agent_id) AS distinct_agent_count,
         count(DISTINCT workflow_id) AS distinct_workflow_count,
         max(executed_at) AS last_called_at
  FROM raw_mcp.tool_execution_audit GROUP BY _deployment_id, tool_id
)
SELECT
  t._deployment_id,
  t.id               AS mcp_tool_id,
  t.name             AS tool_name,
  t.display_name,
  t.description,
  t.category,
  t.subcategory,
  array_join(t.tags, ', ') AS tags,
  CASE WHEN lower(t.name) RLIKE '(^|[^a-z])(create|update|delete|add|post|put|set|write|insert|remove|send|assign|close|transition|upload|publish|push|commit|merge)([^a-z]|$)' THEN 'WRITE'
       WHEN lower(t.name) RLIKE '(^|[^a-z])(get|list|search|read|fetch|query|find|describe|retrieve|lookup|download|scrape|browse)([^a-z]|$)' THEN 'READ'
       ELSE 'OTHER' END AS action_type,
  t.server_id,
  s.name             AS server_name,
  s.category         AS server_category,
  t.requires_authentication, t.requires_credentials, t.admin_only,
  t.async_supported, t.streaming_supported,
  t.is_active, t.is_deprecated,
  COALESCE(ex.call_count, 0)    AS call_count,
  COALESCE(ex.success_count, 0) AS success_count,
  round(100.0 * ex.success_count / nullif(ex.call_count, 0), 2) AS success_rate_pct,
  ex.avg_execution_ms,
  COALESCE(ex.distinct_user_count, 0)     AS distinct_user_count,
  COALESCE(ex.distinct_agent_count, 0)    AS distinct_agent_count,
  COALESCE(ex.distinct_workflow_count, 0) AS distinct_workflow_count,
  ex.last_called_at,
  t.usage_count      AS platform_usage_counter,
  t.success_rate     AS platform_success_rate,
  t.created_at, t.updated_at
FROM raw_mcp.tools t
LEFT JOIN raw_mcp.servers s ON s._deployment_id = t._deployment_id AND s.id = t.server_id
LEFT JOIN ex ON ex._deployment_id = t._deployment_id AND ex.tool_id = t.id
WHERE NOT COALESCE(t.is_deleted, false);


-- =============================================================================
-- Process Studio: process definitions and the artifacts placed in them
-- =============================================================================
CREATE OR REPLACE TABLE explore.process_nodes AS
SELECT
  l._deployment_id,
  l.process_definition_id AS process_id,
  p.name                  AS process_name,
  l.node_id,
  upper(l.artifact_type)  AS artifact_type,
  l.artifact_id,
  CASE WHEN upper(l.artifact_type) LIKE 'AGENT%' THEN a.name
       WHEN upper(l.artifact_type) LIKE 'WORKFLOW%' OR upper(l.artifact_type) LIKE 'PIPELINE%' THEN w.name
       WHEN upper(l.artifact_type) LIKE 'TOOL%' THEN t.tool_name
  END AS artifact_name
FROM raw_process_studio.process_definition_artifact_link l
LEFT JOIN raw_process_studio.process_definition p
       ON p._deployment_id = l._deployment_id AND p.id = l.process_definition_id
LEFT JOIN raw_core.agents a
       ON a._deployment_id = l._deployment_id AND a.id = l.artifact_id AND upper(l.artifact_type) LIKE 'AGENT%'
LEFT JOIN raw_core.workflows w
       ON w._deployment_id = l._deployment_id AND w.id = l.artifact_id
      AND (upper(l.artifact_type) LIKE 'WORKFLOW%' OR upper(l.artifact_type) LIKE 'PIPELINE%')
LEFT JOIN raw_core.tools t
       ON t._deployment_id = l._deployment_id AND t.id = l.artifact_id AND upper(l.artifact_type) LIKE 'TOOL%';

CREATE OR REPLACE TABLE explore.processes AS
WITH nodes AS (
  SELECT _deployment_id, process_id,
         count(*) AS linked_artifact_count,
         count_if(artifact_type LIKE 'AGENT%') AS agent_node_count,
         count_if(artifact_type LIKE 'WORKFLOW%' OR artifact_type LIKE 'PIPELINE%') AS workflow_node_count,
         count_if(artifact_type LIKE 'TOOL%') AS tool_node_count,
         array_sort(collect_set(artifact_name)) AS linked_artifact_names
  FROM explore.process_nodes GROUP BY _deployment_id, process_id
),
ex AS (
  SELECT _deployment_id, process_definition_id,
         count(*) AS run_count,
         count(DISTINCT started_by) AS distinct_runner_count,
         count_if(failure_code IS NOT NULL OR failure_reason IS NOT NULL) AS failed_run_count,
         max(started_at) AS last_run_at,
         round(avg(timestampdiff(SECOND, started_at, ended_at))) AS avg_duration_seconds
  FROM raw_process_studio.process_execution GROUP BY _deployment_id, process_definition_id
),
ht AS (
  SELECT pe._deployment_id, pe.process_definition_id,
         count(*) AS human_task_count,
         array_sort(collect_set(h.decision)) AS human_decisions
  FROM raw_process_studio.human_task h
  JOIN raw_process_studio.process_execution pe
    ON pe._deployment_id = h._deployment_id AND pe.id = h.process_execution_id
  GROUP BY pe._deployment_id, pe.process_definition_id
),
latest AS (
  SELECT _deployment_id, id,
         row_number() OVER (PARTITION BY _deployment_id, tenant_id, process_key ORDER BY version DESC) AS rn
  FROM raw_process_studio.process_definition
)
SELECT
  p._deployment_id,
  p.id              AS process_id,
  p.process_key,
  p.name            AS process_name,
  p.description,
  p.version,
  (l.rn = 1)        AS is_latest_version,
  p.status          AS status_code,
  p.approval_status AS approval_status_code,
  p.practice_area,
  p.realm,
  p.execution_input_mode,
  p.source_process_id AS cloned_from_process_id,
  COALESCE(n.linked_artifact_count, 0) AS linked_artifact_count,
  COALESCE(n.agent_node_count, 0)      AS agent_node_count,
  COALESCE(n.workflow_node_count, 0)   AS workflow_node_count,
  COALESCE(n.tool_node_count, 0)       AS tool_node_count,
  n.linked_artifact_names,
  (COALESCE(ht.human_task_count, 0) > 0) AS has_human_in_the_loop,
  COALESCE(ht.human_task_count, 0)       AS human_task_count,
  ht.human_decisions,
  COALESCE(ex.run_count, 0)             AS run_count,
  COALESCE(ex.distinct_runner_count, 0) AS distinct_runner_count,
  COALESCE(ex.failed_run_count, 0)      AS failed_run_count,
  ex.avg_duration_seconds,
  ex.last_run_at,
  p.created_at, p.published_at
FROM raw_process_studio.process_definition p
LEFT JOIN latest l ON l._deployment_id = p._deployment_id AND l.id = p.id
LEFT JOIN nodes n  ON n._deployment_id = p._deployment_id AND n.process_id = p.id
LEFT JOIN ex       ON ex._deployment_id = p._deployment_id AND ex.process_definition_id = p.id
LEFT JOIN ht       ON ht._deployment_id = p._deployment_id AND ht.process_definition_id = p.id;


-- =============================================================================
-- Executions of agents, workflows and tools (one row per run)
-- =============================================================================
CREATE OR REPLACE TABLE explore.executions AS
WITH agent_jobs AS (
  SELECT _deployment_id, execution_id, max_by(status, COALESCE(modified_at, created_at)) AS status
  FROM raw_core.agent_execution_job GROUP BY _deployment_id, execution_id
),
workflow_jobs AS (
  SELECT _deployment_id, executionid AS execution_id, max_by(status, COALESCE(modified_at, created_at)) AS status
  FROM raw_core.workflow_execution_job GROUP BY _deployment_id, executionid
)
SELECT
  e._deployment_id,
  e.execution_id,
  CASE WHEN upper(e.artifact_type) = 'PIPELINE' THEN 'WORKFLOW' ELSE upper(e.artifact_type) END AS artifact_type,
  e.artifact_id,
  CASE WHEN upper(e.artifact_type) = 'AGENT' THEN a.name
       WHEN upper(e.artifact_type) IN ('WORKFLOW', 'PIPELINE') THEN w.name
       WHEN upper(e.artifact_type) = 'TOOL' THEN t.tool_name
  END AS artifact_name,
  e.start_time,
  e.end_time,
  to_date(e.start_time) AS run_date,
  timestampdiff(SECOND, e.start_time, e.end_time) AS duration_seconds,
  upper(COALESCE(aj.status, wj.status)) AS job_status,
  e.executor_id         AS executor_user_id,
  u.department          AS executor_department,
  e.tokens_used,
  e.api_calls_count,
  e.compute_cost,
  e.cost_currency,
  e.rating,
  e.like_dislike,
  e.issue_tags,
  e.comment             AS user_comment,
  m.model               AS model_name,
  oh.organization_name, oh.domain_name, oh.project_name, oh.team_name, oh.realm_name
FROM raw_core.artifact_executions e
LEFT JOIN raw_core.agents a    ON a._deployment_id = e._deployment_id AND a.id = e.artifact_id AND upper(e.artifact_type) = 'AGENT'
LEFT JOIN raw_core.workflows w ON w._deployment_id = e._deployment_id AND w.id = e.artifact_id AND upper(e.artifact_type) IN ('WORKFLOW', 'PIPELINE')
LEFT JOIN raw_core.tools t     ON t._deployment_id = e._deployment_id AND t.id = e.artifact_id AND upper(e.artifact_type) = 'TOOL'
LEFT JOIN agent_jobs aj        ON aj._deployment_id = e._deployment_id AND aj.execution_id = e.execution_id
LEFT JOIN workflow_jobs wj     ON wj._deployment_id = e._deployment_id AND wj.execution_id = e.execution_id
LEFT JOIN raw_rbac.users u     ON u._deployment_id = e._deployment_id AND u.user_id = e.executor_id
LEFT JOIN raw_core.model m     ON m._deployment_id = e._deployment_id AND m.id = e.model_id
LEFT JOIN explore.org_hierarchy oh ON oh._deployment_id = e._deployment_id AND oh.realm_id = e.realm_id;


-- =============================================================================
-- LLM usage through the AI gateway, aggregated per day (prompt/response text is never ingested)
-- =============================================================================
CREATE OR REPLACE TABLE explore.llm_usage_daily AS
SELECT
  g._deployment_id,
  to_date(g.occurred_at)  AS usage_date,
  g.tenant_id,
  g.tenant_tier,
  g.realm_name,
  upper(g.caller_type)    AS caller_type,
  g.agent_id,
  a.name                  AS agent_name,
  g.pipeline_id           AS workflow_id,
  w.name                  AS workflow_name,
  g.pipeline_type,
  g.model_key,
  g.model_type,
  g.provider_name,
  g.request_type,
  count(*)                             AS call_count,
  sum(g.input_tokens)                  AS input_tokens,
  sum(g.output_tokens)                 AS output_tokens,
  sum(g.total_tokens)                  AS total_tokens,
  round(sum(g.cost_usd), 4)            AS cost_usd,
  round(avg(g.latency_ms))             AS avg_latency_ms,
  percentile_approx(g.latency_ms, 0.95) AS p95_latency_ms,
  count_if(g.status_code >= 400)       AS error_count,
  count_if(g.cache_hit)                AS cache_hit_count,
  count_if(g.pii_detected)             AS pii_detected_count,
  count_if(upper(COALESCE(g.guardrail_decision, '')) RLIKE 'BLOCK|DENY|DENIED|REJECT') AS guardrail_blocked_count,
  sum(g.total_violation_count)         AS guardrail_violation_count,
  count(DISTINCT g.user_id)            AS distinct_user_count
FROM raw_core.ai_gateway_audit_log g
LEFT JOIN raw_core.agents a    ON a._deployment_id = g._deployment_id AND a.id = try_cast(g.agent_id AS INT)
LEFT JOIN raw_core.workflows w ON w._deployment_id = g._deployment_id AND w.id = try_cast(g.pipeline_id AS INT)
GROUP BY ALL;


-- =============================================================================
-- MCP tool calls aggregated per day
-- =============================================================================
CREATE OR REPLACE TABLE explore.mcp_tool_usage_daily AS
SELECT
  x._deployment_id,
  x.execution_date                  AS usage_date,
  x.server_id,
  COALESCE(s.name, x.server_name)   AS server_name,
  x.tool_id                         AS mcp_tool_id,
  COALESCE(t.name, x.tool_name)     AS tool_name,
  x.agent_id,
  a.name                            AS agent_name,
  x.workflow_id,
  w.name                            AS workflow_name,
  x.execution_mode,
  count(*)                          AS call_count,
  count_if(x.success)               AS success_count,
  count_if(NOT x.success)           AS failure_count,
  round(avg(x.execution_time_ms))   AS avg_execution_ms,
  count_if(x.security_violation)    AS security_violation_count,
  sum(x.retry_count)                AS retry_count,
  count(DISTINCT x.user_id)         AS distinct_user_count,
  array_sort(collect_set(x.error_code)) AS error_codes
FROM raw_mcp.tool_execution_audit x
LEFT JOIN raw_mcp.servers s    ON s._deployment_id = x._deployment_id AND s.id = x.server_id
LEFT JOIN raw_mcp.tools t      ON t._deployment_id = x._deployment_id AND t.id = x.tool_id
LEFT JOIN raw_core.agents a    ON a._deployment_id = x._deployment_id AND a.id = x.agent_id
LEFT JOIN raw_core.workflows w ON w._deployment_id = x._deployment_id AND w.id = x.workflow_id
GROUP BY ALL;


-- =============================================================================
-- Demand signals: marketplace searches and user feedback
-- =============================================================================
CREATE OR REPLACE TABLE explore.search_queries AS
SELECT
  _deployment_id,
  id                              AS search_id,
  executed_at,
  to_date(executed_at)            AS search_date,
  query_text,
  lower(trim(query_text))         AS query_normalized,
  search_type,
  entity_type,
  strategy_used,
  result_count,
  (COALESCE(result_count, 0) = 0) AS is_zero_result,
  is_conceptual,
  term_count,
  query_confidence,
  response_time_ms,
  has_error,
  user_session_id
FROM raw_core.search_events;

CREATE OR REPLACE TABLE explore.user_feedback AS
SELECT
  f._deployment_id,
  f.id              AS feedback_id,
  f.feedback_type,
  upper(f.context_type) AS context_type,
  f.context_id,
  CASE upper(f.context_type)
       WHEN 'AGENT' THEN a.name
       WHEN 'WORKFLOW' THEN w.name
       WHEN 'TOOL' THEN t.tool_name
  END               AS context_name,
  f.feedback_text,
  f.sentiment_score,
  f.priority,
  f.status,
  u.department      AS user_department,
  f.created_at,
  f.resolved_at
FROM raw_core.user_feedback f
LEFT JOIN raw_core.agents a    ON a._deployment_id = f._deployment_id AND a.id = f.context_id AND upper(f.context_type) = 'AGENT'
LEFT JOIN raw_core.workflows w ON w._deployment_id = f._deployment_id AND w.id = f.context_id AND upper(f.context_type) = 'WORKFLOW'
LEFT JOIN raw_core.tools t     ON t._deployment_id = f._deployment_id AND t.id = f.context_id AND upper(f.context_type) = 'TOOL'
LEFT JOIN raw_rbac.users u     ON u._deployment_id = f._deployment_id AND u.user_id = f.user_id;


-- =============================================================================
-- LLM evaluation scores from TruLens (groundedness, relevance and so on)
-- =============================================================================
CREATE OR REPLACE TABLE explore.quality_scores AS
SELECT
  f._deployment_id,
  f.feedback_result_id,
  f.record_id,
  r.app_id,
  ap.app_name,
  ap.app_version,
  f.name                          AS metric_name,
  f.result                        AS score,
  f.status                        AS evaluation_status,
  timestamp_seconds(f.last_ts)    AS evaluated_at,
  timestamp_seconds(r.ts)         AS record_at
FROM raw_trulens.trulens_feedbacks f
LEFT JOIN raw_trulens.trulens_records r ON r._deployment_id = f._deployment_id AND r.record_id = f.record_id
LEFT JOIN raw_trulens.trulens_apps ap   ON ap._deployment_id = r._deployment_id AND ap.app_id = r.app_id;


-- =============================================================================
-- Third-party integrations (tech stack connected by users)
-- =============================================================================
CREATE OR REPLACE TABLE explore.integrations AS
WITH conn AS (
  SELECT _deployment_id, lower(provider) AS provider_key,
         count(DISTINCT user_id) AS connected_user_count,
         max(connected_at) AS last_connected_at
  FROM raw_rbac.integrations GROUP BY _deployment_id, lower(provider)
),
tl AS (
  SELECT pt._deployment_id, pt.integration_provider_id,
         count(*) AS tool_count,
         array_sort(collect_set(t.tool_name)) AS tool_names
  FROM raw_rbac.integration_provider_tools pt
  LEFT JOIN raw_core.tools t ON t._deployment_id = pt._deployment_id AND t.id = pt.tool_id
  GROUP BY pt._deployment_id, pt.integration_provider_id
)
SELECT
  p._deployment_id,
  p.id            AS provider_id,
  p.provider,
  p.display_name,
  p.description,
  p.auth_type,
  COALESCE(c.connected_user_count, 0) AS connected_user_count,
  c.last_connected_at,
  COALESCE(tl.tool_count, 0) AS tool_count,
  tl.tool_names,
  p.created_at
FROM raw_rbac.integration_providers p
LEFT JOIN conn c ON c._deployment_id = p._deployment_id AND c.provider_key = lower(p.provider)
LEFT JOIN tl     ON tl._deployment_id = p._deployment_id AND tl.integration_provider_id = p.id;
