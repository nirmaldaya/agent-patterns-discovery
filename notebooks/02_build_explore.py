# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Build the curated explore tables
# MAGIC
# MAGIC Rebuilds `<catalog>.explore.*` (agents, workflows, tools, knowledge bases, MCP, processes, executions,
# MAGIC LLM usage, searches, quality, org hierarchy) from the `raw_*` tables. Runs
# MAGIC [`sql/10_explore_tables.sql`](../sql/10_explore_tables.sql).
# MAGIC
# MAGIC Needs `01_ingest_postgres` to have loaded the raw tables. Next: `03_build_labels_and_catalog`.

# COMMAND ----------

dbutils.widgets.text("catalog", "apdi", "Catalog")

# COMMAND ----------

import os
import sys

sys.path.insert(0, os.getcwd())
from sql_runner import run_sql_file  # noqa: E402

CATALOG = dbutils.widgets.get("catalog").strip()
run_sql_file(spark, CATALOG, os.path.abspath("../sql/10_explore_tables.sql"), drop_foreign_keys_in="explore")
display(spark.sql(f"SHOW TABLES IN `{CATALOG}`.explore"))
