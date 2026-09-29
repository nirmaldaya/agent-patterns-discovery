"""Runs a .sql file from this repo statement by statement. Used by 00_setup and 02_build_explore.

Plain Python module (not a notebook) so both notebooks share one implementation.
Statements are split on ";", so the SQL files keep semicolons out of literals and comments.
"""

import re
import time


def split_statements(text: str) -> list:
    body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--"))
    return [s.strip() for s in body.split(";") if s.strip()]


def _hint(msg: str, catalog: str) -> str:
    if "TABLE_OR_VIEW_NOT_FOUND" in msg and "raw_" in msg:
        return ("A raw table does not exist yet. Run notebooks/01_ingest_postgres (dry_run = false) first, then check "
                f"{catalog}.ops.ingestion_log: every table should be SUCCESS.")
    if "SCHEMA_NOT_FOUND" in msg:
        return "A schema is missing. Run notebooks/00_setup first."
    if "PERMISSION_DENIED" in msg or "INSUFFICIENT_PERMISSIONS" in msg:
        return (f"Missing privileges on catalog {catalog}. You need USE CATALOG and CREATE SCHEMA on it "
                f"(check with: SHOW GRANTS ON CATALOG {catalog}).")
    if "NO_SUCH_CATALOG" in msg or "CATALOG_NOT_FOUND" in msg:
        return f"Catalog {catalog} does not exist. Create it in Catalog Explorer, or set the catalog widget."
    return ""


def run_sql_file(spark, catalog: str, path: str, create_catalog: bool = False, drop_foreign_keys_in: str = "") -> None:
    if create_catalog:
        spark.sql(f"CREATE CATALOG IF NOT EXISTS `{catalog}`")
    spark.sql(f"USE CATALOG `{catalog}`")

    if drop_foreign_keys_in:
        # 06_apply_genie_metadata adds foreign keys, which would block CREATE OR REPLACE of the tables they reference.
        try:
            fks = spark.sql(f"""
                SELECT table_name, constraint_name FROM `{catalog}`.information_schema.table_constraints
                WHERE table_schema = '{drop_foreign_keys_in}' AND constraint_type = 'FOREIGN KEY'
            """).collect()
            for fk in fks:
                spark.sql(f"ALTER TABLE `{drop_foreign_keys_in}`.`{fk.table_name}` DROP CONSTRAINT IF EXISTS `{fk.constraint_name}`")
            print(f"Dropped {len(fks)} foreign key(s) in {drop_foreign_keys_in}")
        except Exception as exc:  # no Unity Catalog information_schema: nothing to drop
            print(f"Skipped foreign-key cleanup: {str(exc).splitlines()[0][:200]}")

    with open(path) as fh:
        statements = split_statements(fh.read())
    print(f"{path}: {len(statements)} statements in catalog {catalog}")
    for i, stmt in enumerate(statements, 1):
        head = re.sub(r"\s+", " ", stmt)[:100]
        started = time.time()
        try:
            spark.sql(stmt)
        except Exception as exc:
            msg = str(exc)
            hint = _hint(msg, catalog)
            if hint:
                raise RuntimeError(f"Statement {i} failed: {head}\n{hint}\nOriginal error: {msg.splitlines()[0]}") from exc
            raise
        print(f"[{i}/{len(statements)}] {time.time() - started:6.1f}s  {head}")
