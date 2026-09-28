-- APDI quick solution - Unity Catalog layout (run once, re-runnable)
--
-- Executed by notebooks/run_sql_file.py, which first runs CREATE CATALOG IF NOT EXISTS
-- and USE CATALOG <catalog>. You can also paste this into the SQL editor after
-- selecting the catalog yourself.
--
--   <catalog>
--   ├── raw_core, raw_mcp, raw_process_studio, raw_rbac, raw_trulens   1:1 copies of PostgreSQL tables
--   ├── ref                                                            manually maintained reference data
--   ├── explore                                                        curated tables the Genie space uses
--   └── ops                                                            ingestion run log

CREATE SCHEMA IF NOT EXISTS raw_core           COMMENT 'Raw copy of PostgreSQL schema core (agents, tools, workflows, knowledge bases, executions)';
CREATE SCHEMA IF NOT EXISTS raw_mcp            COMMENT 'Raw copy of PostgreSQL schema mcp (MCP servers, MCP tools, tool execution audit)';
CREATE SCHEMA IF NOT EXISTS raw_process_studio COMMENT 'Raw copy of PostgreSQL schema process_studio (process definitions and executions)';
CREATE SCHEMA IF NOT EXISTS raw_rbac           COMMENT 'Raw copy of PostgreSQL schema rbac (organisation hierarchy, users, integrations)';
CREATE SCHEMA IF NOT EXISTS raw_trulens        COMMENT 'Raw copy of PostgreSQL schema trulens (LLM evaluation results)';
CREATE SCHEMA IF NOT EXISTS ref                COMMENT 'Reference data maintained by APDI stewards (industry mapping, keyword taxonomy)';
CREATE SCHEMA IF NOT EXISTS explore            COMMENT 'Curated, denormalised tables for data exploration and the APDI Genie space';
CREATE SCHEMA IF NOT EXISTS ops                COMMENT 'Operational tables for the APDI pipelines';

CREATE TABLE IF NOT EXISTS ops.ingestion_log (
  run_id          STRING    COMMENT 'Databricks job run id, or a generated id for interactive runs',
  deployment_id   STRING    COMMENT 'Platform deployment (customer instance) the data came from',
  source_table    STRING    COMMENT 'schema.table in PostgreSQL',
  target_table    STRING    COMMENT 'Unity Catalog table written',
  mode            STRING    COMMENT 'full or incremental',
  status          STRING    COMMENT 'SUCCESS, FAILED or SKIPPED',
  rows_written    BIGINT    COMMENT 'Rows written by this run',
  watermark_from  STRING    COMMENT 'Incremental mode: rows greater than this value were loaded',
  started_at      TIMESTAMP,
  finished_at     TIMESTAMP,
  message         STRING    COMMENT 'Error text or informational note'
) COMMENT 'One row per table per ingestion run';

-- Manual industry mapping. Industry does not exist in the source data, so stewards
-- map it here. The most specific match wins: REALM, then TEAM, PROJECT, DOMAIN,
-- ORGANIZATION and finally DEPLOYMENT (the whole customer instance).
-- Artifacts without a manual mapping fall back to the keyword-inferred industry.
CREATE TABLE IF NOT EXISTS ref.industry_mapping (
  deployment_id STRING    COMMENT 'Deployment the mapping applies to. NULL applies it to every deployment',
  scope_level   STRING    COMMENT 'DEPLOYMENT, ORGANIZATION, DOMAIN, PROJECT, TEAM or REALM',
  scope_name    STRING    COMMENT 'Name exactly as in rbac (case-insensitive). NULL when scope_level = DEPLOYMENT',
  industry      STRING    COMMENT 'Industry label, e.g. Healthcare, Insurance, Banking & Financial Services',
  mapped_by     STRING    COMMENT 'Who made the mapping',
  mapped_at     TIMESTAMP COMMENT 'When the mapping was made. The latest wins on conflicts',
  notes         STRING
) COMMENT 'Steward-maintained industry mapping for customers and org units';

-- Example (uncomment and adapt):
-- INSERT INTO ref.industry_mapping VALUES
--   ('dep_001', 'DEPLOYMENT',   NULL,          'Insurance',  'jane.doe', current_timestamp(), 'Whole customer'),
--   ('dep_001', 'DOMAIN',       'Health Plans', 'Healthcare', 'jane.doe', current_timestamp(), 'Health subsidiary');
