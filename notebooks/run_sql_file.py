# Databricks notebook source
# MAGIC %md
# MAGIC # Run a SQL file against the APDI catalog
# MAGIC
# MAGIC Executes every statement in a `.sql` file from this repo after `USE CATALOG <catalog>`.
# MAGIC Used by the job for `sql/00_setup.sql` (with `create_catalog = true`) and `sql/10_explore_tables.sql`.
# MAGIC
# MAGIC Statements are split on `;`, so SQL files must not contain semicolons inside literals or comments.
# MAGIC
# MAGIC When `drop_foreign_keys_in` names a schema, foreign-key constraints in that schema are dropped first.
# MAGIC `04_apply_genie_metadata` adds them, and they would otherwise block `CREATE OR REPLACE` of the tables they reference.

# COMMAND ----------

dbutils.widgets.text("catalog", "apdi", "Catalog")
dbutils.widgets.text("sql_file", "../sql/10_explore_tables.sql", "SQL file (relative to this notebook)")
dbutils.widgets.dropdown("create_catalog", "false", ["true", "false"], "CREATE CATALOG IF NOT EXISTS first")
dbutils.widgets.text("drop_foreign_keys_in", "", "Drop FK constraints in this schema first (blank = skip)")

# COMMAND ----------

import os
import re
import time

CATALOG = dbutils.widgets.get("catalog").strip()
SQL_FILE = os.path.abspath(dbutils.widgets.get("sql_file").strip())
FK_SCHEMA = dbutils.widgets.get("drop_foreign_keys_in").strip()

if dbutils.widgets.get("create_catalog") == "true":
    # Needs CREATE CATALOG on the metastore. If your workspace requires a managed location,
    # create the catalog once in Catalog Explorer and leave this option off.
    spark.sql(f"CREATE CATALOG IF NOT EXISTS `{CATALOG}`")
spark.sql(f"USE CATALOG `{CATALOG}`")

if FK_SCHEMA:
    fks = spark.sql(f"""
        SELECT table_name, constraint_name
        FROM `{CATALOG}`.information_schema.table_constraints
        WHERE table_schema = '{FK_SCHEMA}' AND constraint_type = 'FOREIGN KEY'
    """).collect()
    for fk in fks:
        spark.sql(f"ALTER TABLE `{FK_SCHEMA}`.`{fk.table_name}` DROP CONSTRAINT IF EXISTS `{fk.constraint_name}`")
    print(f"Dropped {len(fks)} foreign key(s) in {FK_SCHEMA}")


def split_statements(text):
    body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--"))
    return [s.strip() for s in body.split(";") if s.strip()]


with open(SQL_FILE) as fh:
    statements = split_statements(fh.read())

print(f"{SQL_FILE}: {len(statements)} statements")
for i, stmt in enumerate(statements, 1):
    head = re.sub(r"\s+", " ", stmt)[:100]
    started = time.time()
    spark.sql(stmt)
    print(f"[{i}/{len(statements)}] {time.time() - started:6.1f}s  {head}")
