# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Setup: schemas and control tables
# MAGIC
# MAGIC Run once (safe to re-run). Creates, inside the catalog:
# MAGIC `raw_core`, `raw_mcp`, `raw_process_studio`, `raw_rbac`, `raw_trulens`, `ref`, `explore`, `ops`,
# MAGIC plus `ops.ingestion_log` and `ref.industry_mapping`. Runs [`sql/00_setup.sql`](../sql/00_setup.sql).
# MAGIC
# MAGIC Needs **USE CATALOG** and **CREATE SCHEMA** on the catalog.
# MAGIC Next: `01_ingest_postgres`.

# COMMAND ----------

dbutils.widgets.text("catalog", "apdi", "Catalog")
dbutils.widgets.dropdown("create_catalog", "false", ["true", "false"], "CREATE CATALOG IF NOT EXISTS first")

# COMMAND ----------

import os
import sys

sys.path.insert(0, os.getcwd())
from sql_runner import run_sql_file  # noqa: E402

CATALOG = dbutils.widgets.get("catalog").strip()
run_sql_file(spark, CATALOG, os.path.abspath("../sql/00_setup.sql"),
             create_catalog=dbutils.widgets.get("create_catalog") == "true")
display(spark.sql(f"SHOW SCHEMAS IN `{CATALOG}`"))
