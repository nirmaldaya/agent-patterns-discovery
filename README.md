# APDI · Agent Pattern Discovery & Intelligence (quick solution)

Makes what customers build on the platform (agents, workflows, tools, knowledge bases, MCP servers, guardrails
and processes) explorable in Databricks, and lets anyone query it in plain language through **Genie**.

| Step | What | Where |
|---|---|---|
| 1 | Identify the tables needed for data exploration | [`docs/01_table_inventory.md`](docs/01_table_inventory.md), [`config/tables.yml`](config/tables.yml) |
| 2 | Ingest them from PostgreSQL into Databricks | [`notebooks/01_ingest_postgres.py`](notebooks/01_ingest_postgres.py) |
| 3 | Build a Unity Catalog catalog with curated tables | [`notebooks/00_setup.py`](notebooks/00_setup.py), [`notebooks/02_build_explore.py`](notebooks/02_build_explore.py) (running [`sql/00_setup.sql`](sql/00_setup.sql) and [`sql/10_explore_tables.sql`](sql/10_explore_tables.sql)), [`notebooks/03_build_labels_and_catalog.py`](notebooks/03_build_labels_and_catalog.py), [`notebooks/06_apply_genie_metadata.py`](notebooks/06_apply_genie_metadata.py) |
| 4 | Attach Genie and ask questions | [`genie/genie_space_setup.md`](genie/genie_space_setup.md), [`genie/sample_queries.sql`](genie/sample_queries.sql) |
| 5 | Knowledge graph and graph analytics (for the graph UI) | [`docs/02_graph_model.md`](docs/02_graph_model.md), [`notebooks/04_build_graph.py`](notebooks/04_build_graph.py), [`notebooks/05_graph_analytics.py`](notebooks/05_graph_analytics.py) |
| 6 | Interactive graph explorer (FastAPI + React, deployed as a Databricks App) | [`apps/graph-explorer`](apps/graph-explorer/README.md) |

## What you get

```
apdi (catalog)
├── raw_core, raw_mcp, raw_process_studio, raw_rbac, raw_trulens   72 source tables copied 1:1 (secrets and PII removed)
├── explore                                                        curated tables for Genie (below)
├── ref                                                            industry_mapping (maintained by stewards), keyword_taxonomy
└── ops                                                            ingestion_log
```

| `explore` table | Grain |
|---|---|
| **`artifact_catalog`** | One row per agent, workflow, tool, MCP server, MCP tool, knowledge base, guardrail and process, with org context, usage and label arrays: `industries`, `sdlc_phases`, `tech_stack`, `business_functions`, `archetypes` |
| `artifact_labels` | One row per artifact, dimension and label, with the keyword that triggered it |
| `agents`, `workflows`, `tools`, `knowledge_bases`, `guardrails`, `mcp_servers`, `mcp_tools`, `processes` | One row per artifact with type-specific detail (role and goal, agent chain, parameters, files, model, ratings, runs) |
| `workflow_agents`, `agent_tools`, `agent_knowledge_bases`, `agent_guardrails`, `process_nodes` | How artifacts are wired together |
| `executions`, `llm_usage_daily`, `mcp_tool_usage_daily` | What actually runs: duration, status, tokens, cost, failures, PII and guardrail hits |
| `search_queries`, `user_feedback`, `quality_scores`, `integrations`, `org_hierarchy` | Demand, sentiment, evaluation scores, connected systems and org structure |
| `graph_nodes`, `graph_edges`, `graph_summary_edges` | Knowledge graph: artifacts, models, org units and taxonomy values as nodes, and composition, usage, ownership, label, lineage and co-occurrence relationships as weighted edges |
| `graph_node_metrics`, `graph_communities` | PageRank, betweenness, islands and solution-pattern communities with readable names |

### Industry, SDLC phase and tech stack

None of these exist in the source data, so this solution derives them:

* **Keyword labels.** [`config/keyword_taxonomy.yml`](config/keyword_taxonomy.yml) lists keywords per label for
  SDLC phase, tech stack, industry, business function and agent archetype. They are matched against each
  artifact's names, role, goal, description, tools and knowledge bases. The approach is transparent (`artifact_labels.matched_keyword`
  shows why) and easy to tune, but it is a first pass. An LLM classifier is the natural next step.
* **Manual industry mapping.** Stewards add rows to `ref.industry_mapping` at DEPLOYMENT, ORGANIZATION,
  DOMAIN, PROJECT, TEAM or REALM level. The most specific mapping wins, and a manual mapping always beats the
  inferred industry. Example:

  ```sql
  INSERT INTO apdi.ref.industry_mapping VALUES
    ('dep_001', 'DEPLOYMENT', NULL,           'Insurance',  'jane.doe', current_timestamp(), 'Whole customer'),
    ('dep_001', 'DOMAIN',     'Health Plans', 'Healthcare', 'jane.doe', current_timestamp(), 'Health subsidiary');
  ```

## Setup

### 1. Connectivity and a read-only PostgreSQL user

Databricks compute must reach the PostgreSQL host (VNet/VPC peering, Private Link or an IP allow-list).
Create a read-only user. Ideally grant it only the tables in `config/tables.yml`:

```sql
CREATE ROLE apdi_reader LOGIN PASSWORD '<strong password>';
GRANT USAGE ON SCHEMA core, mcp, process_studio, rbac, trulens TO apdi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA core, mcp, process_studio, rbac, trulens TO apdi_reader;
```

The ingestion query lists columns explicitly, so excluded columns (credentials, e-mails, prompts, payloads,
binaries) never leave PostgreSQL.

### 2. Secrets

```bash
databricks secrets create-scope apdi
databricks secrets put-secret apdi pg_host     --string-value <host>
databricks secrets put-secret apdi pg_port     --string-value 5432
databricks secrets put-secret apdi pg_database --string-value <database>
databricks secrets put-secret apdi pg_user     --string-value apdi_reader
databricks secrets put-secret apdi pg_password --string-value '<password>'
# optional, default is require
databricks secrets put-secret apdi pg_sslmode  --string-value require
```

### 3. Catalog

Create the catalog once in Catalog Explorer (or `CREATE CATALOG apdi`, adding `MANAGED LOCATION` if your
metastore requires one). The job creates the schemas and tables inside it.

### 4. Deploy and run

**Option A: Asset Bundle (recommended).** This deploys a job that runs daily.

```bash
databricks bundle deploy -t dev --var="catalog=apdi" --var="node_type_id=<vm type for your cloud>"
databricks bundle run apdi_refresh -t dev
```

**Option B: Git folder.** Clone this repo into the workspace as a Git folder and run the notebooks in order on
a Unity Catalog cluster with DBR 15.4 LTS or later:

| # | Notebook | Widgets (all have `catalog`, default `apdi`) |
|---|---|---|
| 0 | `notebooks/00_setup.py` | – |
| 1 | `notebooks/01_ingest_postgres.py` | `deployment_id`, `secret_scope`, `dry_run` (run with `true` first to test the connection) |
| 2 | `notebooks/02_build_explore.py` | – |
| 3 | `notebooks/03_build_labels_and_catalog.py` | – |
| 4 | `notebooks/04_build_graph.py` | – |
| 5 | `notebooks/05_graph_analytics.py` | `resolution` (community granularity) |
| 6 | `notebooks/06_apply_genie_metadata.py` | – |

The file names are in run order. `notebooks/sql_runner.py` is a helper module used by 00 and 02, not a notebook to run.

Check `apdi.ops.ingestion_log` after step 1. Every table should be `SUCCESS`.

### 5. Genie

Follow [`genie/genie_space_setup.md`](genie/genie_space_setup.md).

## Operating it

| Task | How |
|---|---|
| Refresh | The job runs daily at 02:00 UTC. Full tables are reloaded, and large logs (`ai_gateway_audit_log`, `tool_execution_audit`, `search_events`, `user_activity`, `agent_steps`, `tool_usage_stats`) load incrementally |
| Add or drop a table or column | Edit `config/tables.yml`. Use `exclude` for sensitive columns and `redact` for JSON/config columns that may hold secrets |
| Fix a label | Edit `config/keyword_taxonomy.yml` (keywords, or `patterns` for regexes) |
| Fix an industry | Insert into `apdi.ref.industry_mapping` |
| Add a second customer deployment | Run the ingest notebook with a new `deployment_id` and a secret scope pointing at that database. Every table carries `_deployment_id`, full loads replace only that deployment's rows, and all explore joins include it |

## What was tested

Everything below was run end to end on local Spark 4.0 with Delta 4.0 against PostgreSQL 16, loaded with the
**exact DDL of the five schemas** and synthetic data:

* All 72 tables ingest, including enum, interval, inet, jsonb, uuid and array columns. Excluded columns are
  absent, secrets inside JSON and code are masked, and incremental loads pick up only new rows.
* All 21 `explore` tables, the labels and the catalog build. Manual industry mapping precedence works.
* All 17 queries in `genie/sample_queries.sql` run.
* The knowledge graph builds with no dangling edges, the analytics find the expected solution patterns and the
  isolated agent in the test data, and all query recipes in `docs/02_graph_model.md` run.

Not testable outside Databricks, so check them on the first run:

* Unity Catalog primary and foreign keys. The notebook only warns if they fail, and Genie still works.
* `USE CATALOG`, `information_schema` and the asset bundle deployment.
* The Genie space itself.

The join assumptions listed at the end of the [table inventory](docs/01_table_inventory.md) should be
confirmed with the platform team.
