# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Apply Genie metadata (comments, primary and foreign keys)
# MAGIC
# MAGIC Genie reads Unity Catalog table and column comments to understand the data, and reads primary and
# MAGIC foreign keys to work out joins. This notebook applies both from `config/genie_metadata.yml`.
# MAGIC
# MAGIC The explore tables are rebuilt with `CREATE OR REPLACE`, which drops comments and constraints, so this
# MAGIC notebook runs after every rebuild. Constraints are informational (not enforced) in Unity Catalog.
# MAGIC A constraint that cannot be applied is reported but does not fail the run, because Genie works without it.

# COMMAND ----------

dbutils.widgets.text("catalog", "apdi", "Catalog")
dbutils.widgets.text("metadata_path", "../config/genie_metadata.yml", "Metadata file (relative to this notebook)")

# COMMAND ----------

import os

import yaml

CATALOG = dbutils.widgets.get("catalog").strip()
spark.sql(f"USE CATALOG `{CATALOG}`")
with open(os.path.abspath(dbutils.widgets.get("metadata_path").strip())) as fh:
    META = yaml.safe_load(fh)

SCHEMA = META.get("schema", "explore")
COMMON = META.get("common_columns") or {}


def lit(text):
    return "'" + " ".join(str(text).split()).replace("\\", "\\\\").replace("'", "\\'") + "'"


def table_columns(table):
    return {f.name for f in spark.table(f"{SCHEMA}.{table}").schema.fields}


warnings = []
existing = {r.tableName for r in spark.sql(f"SHOW TABLES IN {SCHEMA}").collect()}

# COMMAND ----------

for table, spec in META["tables"].items():
    if table not in existing:
        warnings.append(f"{table}: table not found, skipped")
        continue
    fq = f"{SCHEMA}.{table}"
    spark.sql(f"COMMENT ON TABLE {fq} IS {lit(spec['comment'])}")
    cols = table_columns(table)
    specific = spec.get("columns") or {}
    for col in sorted(specific.keys() - cols):
        warnings.append(f"{table}.{col}: column not found, comment skipped")
    comments = {c: t for c, t in COMMON.items() if c in cols}
    comments.update({c: t for c, t in specific.items() if c in cols})
    for col, comment in comments.items():
        spark.sql(f"ALTER TABLE {fq} ALTER COLUMN `{col}` COMMENT {lit(comment)}")

# COMMAND ----------

# Primary keys first, because foreign keys must reference an existing primary key.
for table, spec in META["tables"].items():
    pk = spec.get("primary_key")
    if not pk or table not in existing:
        continue
    fq = f"{SCHEMA}.{table}"
    try:
        for col in pk:
            spark.sql(f"ALTER TABLE {fq} ALTER COLUMN `{col}` SET NOT NULL")
        spark.sql(f"ALTER TABLE {fq} DROP CONSTRAINT IF EXISTS pk_{table}")
        spark.sql(f"ALTER TABLE {fq} ADD CONSTRAINT pk_{table} PRIMARY KEY ({', '.join(pk)})")
    except Exception as exc:
        warnings.append(f"{table}: primary key not applied: {str(exc).splitlines()[0][:300]}")

for table, spec in META["tables"].items():
    if table not in existing:
        continue
    fq = f"{SCHEMA}.{table}"
    for i, fk in enumerate(spec.get("foreign_keys") or [], 1):
        name = f"fk_{table}_{i}"
        ref_table, ref_cols = fk["references"]["table"], fk["references"]["columns"]
        try:
            spark.sql(f"ALTER TABLE {fq} DROP CONSTRAINT IF EXISTS {name}")
            spark.sql(
                f"ALTER TABLE {fq} ADD CONSTRAINT {name} FOREIGN KEY ({', '.join(fk['columns'])}) "
                f"REFERENCES {SCHEMA}.{ref_table} ({', '.join(ref_cols)})"
            )
        except Exception as exc:
            warnings.append(f"{table}: foreign key {name} not applied: {str(exc).splitlines()[0][:300]}")

# COMMAND ----------

print(f"Applied metadata to {len(META['tables'])} tables in {CATALOG}.{SCHEMA}")
for w in warnings:
    print("WARNING:", w)
