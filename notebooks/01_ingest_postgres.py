# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Ingest PostgreSQL → Unity Catalog (raw layer)
# MAGIC
# MAGIC Copies every table listed in `config/tables.yml` from the platform's PostgreSQL database into
# MAGIC `<catalog>.raw_<schema>.<table>` as Delta tables.
# MAGIC
# MAGIC * **full** tables are reloaded each run and only this deployment's rows are replaced (`replaceWhere`),
# MAGIC   so more customer deployments can share the same tables later.
# MAGIC * **incremental** tables append rows whose watermark column is greater than what is already loaded.
# MAGIC * Binary (`bytea`) columns are always dropped. Columns in `exclude` are never read, and only
# MAGIC   `include` columns are read when that key is present. Secret-looking keys inside `redact`
# MAGIC   columns are masked.
# MAGIC * Every run is logged to `<catalog>.ops.ingestion_log`.
# MAGIC
# MAGIC **Connection secrets** (Databricks secret scope, default `apdi`):
# MAGIC `pg_host`, `pg_port`, `pg_database`, `pg_user`, `pg_password`, plus optional `pg_sslmode` (default `require`).
# MAGIC
# MAGIC ```
# MAGIC databricks secrets create-scope apdi
# MAGIC databricks secrets put-secret apdi pg_host --string-value <host>
# MAGIC ...
# MAGIC ```

# COMMAND ----------

dbutils.widgets.text("catalog", "apdi", "Target catalog")
dbutils.widgets.text("deployment_id", "dep_001", "Deployment id (customer instance)")
dbutils.widgets.text("secret_scope", "apdi", "Secret scope")
dbutils.widgets.text("config_path", "../config/tables.yml", "Table config (relative to this notebook)")
dbutils.widgets.text("only_tables", "", "Only these sources (comma-separated schema.table, blank = all)")
dbutils.widgets.text("parallelism", "4", "Tables loaded in parallel")
dbutils.widgets.dropdown("dry_run", "false", ["true", "false"], "Dry run (print queries only)")

# COMMAND ----------

import datetime
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import yaml
from delta.tables import DeltaTable
from pyspark.sql import functions as F

CATALOG = dbutils.widgets.get("catalog").strip()
DEPLOYMENT_ID = dbutils.widgets.get("deployment_id").strip()
SCOPE = dbutils.widgets.get("secret_scope").strip()
CONFIG_PATH = os.path.abspath(dbutils.widgets.get("config_path").strip())
ONLY = {t.strip() for t in dbutils.widgets.get("only_tables").split(",") if t.strip()}
PARALLELISM = max(1, int(dbutils.widgets.get("parallelism") or 1))
DRY_RUN = dbutils.widgets.get("dry_run") == "true"

try:
    RUN_ID = dbutils.notebook.entry_point.getDbutils().notebook().getContext().jobRunId().get()
except Exception:
    RUN_ID = f"interactive-{uuid.uuid4().hex[:12]}"

# Store and compare timestamps in UTC so incremental watermarks line up with PostgreSQL.
spark.conf.set("spark.sql.session.timeZone", "UTC")


def secret(key, default=None):
    try:
        return dbutils.secrets.get(SCOPE, key)
    except Exception:
        if default is not None:
            return default
        raise


JDBC_URL = (
    f"jdbc:postgresql://{secret('pg_host')}:{secret('pg_port', '5432')}/{secret('pg_database')}"
    f"?sslmode={secret('pg_sslmode', 'require')}"
)
JDBC_USER = secret("pg_user")
JDBC_PASSWORD = secret("pg_password")

with open(CONFIG_PATH) as fh:
    CONFIG = yaml.safe_load(fh)

print(f"catalog={CATALOG} deployment={DEPLOYMENT_ID} run={RUN_ID} tables={len(CONFIG['tables'])} dry_run={DRY_RUN}")

# COMMAND ----------

# PostgreSQL types Spark's JDBC reader cannot map, or maps awkwardly, are cast to text in the pushdown query.
CAST_TO_TEXT = {
    "USER-DEFINED", "interval", "inet", "cidr", "macaddr", "money", "tsvector", "xml",
    "json", "jsonb", "uuid", "bit", "bit varying", "point", "tsrange", "tstzrange", "daterange",
}
# Arrays of these element types are read natively as Spark arrays, and any other array is cast to text.
NATIVE_ARRAYS = {"_text", "_varchar", "_bpchar", "_int2", "_int4", "_int8", "_bool", "_float4", "_float8", "_numeric"}

# Masks the value of any JSON key, or code assignment, whose name looks like a secret.
SECRET_JSON_RE = r'(?i)("[^"]*(password|passwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key|authorization|credential|bearer)[^"]*"\s*:\s*)"[^"]*"'
# Also matches values quoted with escaped quotes (code stored inside a JSON string), and masks without
# adding quotes so the surrounding JSON stays valid.
SECRET_CODE_RE = r"""(?i)\b((password|passwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key)\w*\s*=\s*)\\?["'][^"'\\]*\\?["']"""


def read_query(sql):
    return (
        spark.read.format("jdbc")
        .option("url", JDBC_URL)
        .option("driver", "org.postgresql.Driver")
        .option("user", JDBC_USER)
        .option("password", JDBC_PASSWORD)
        .option("query", sql)
        .option("fetchsize", 10000)
        .load()
    )


def source_columns(schema, table):
    rows = read_query(
        "SELECT column_name, data_type, udt_name FROM information_schema.columns "
        f"WHERE table_schema = '{schema}' AND table_name = '{table}' ORDER BY ordinal_position"
    ).collect()
    return [r.asDict() for r in rows]


def select_list(cols, spec):
    include, exclude = spec.get("include"), set(spec.get("exclude", []))
    names = {c["column_name"] for c in cols}
    missing = sorted((set(include or []) | exclude | set(spec.get("redact", []))) - names)
    exprs, kept = [], []
    for c in cols:
        name, dtype, udt = c["column_name"], c["data_type"], c["udt_name"]
        if dtype == "bytea" or name in exclude or (include and name not in include):
            continue
        quoted = '"' + name.replace('"', '""') + '"'
        if dtype in CAST_TO_TEXT or (dtype == "ARRAY" and udt not in NATIVE_ARRAYS):
            exprs.append(f"{quoted}::text AS {quoted}")
        else:
            exprs.append(quoted)
        kept.append(c)
    return exprs, kept, missing


def current_watermark(target, wm, wm_type):
    """Highest watermark already loaded for this deployment, as a PostgreSQL literal (None if empty)."""
    loaded = spark.table(target).where(F.col("_deployment_id") == DEPLOYMENT_ID)
    if "timestamp" in wm_type:
        # Format inside Spark (session time zone = UTC) so the driver's local time zone never matters.
        value = loaded.agg(F.date_format(F.max(wm), "yyyy-MM-dd HH:mm:ss.SSSSSS")).first()[0]
        if value is None:
            return None, None
        cast = "timestamptz" if "with time zone" in wm_type else "timestamp"
        suffix = "+00" if cast == "timestamptz" else ""
        return value, f"'{value}{suffix}'::{cast}"
    value = loaded.agg(F.max(wm)).first()[0]
    if value is None:
        return None, None
    if isinstance(value, (int, float)):
        return value, str(value)
    return value, "'" + str(value).replace("'", "''") + "'"

# COMMAND ----------


def ingest(spec):
    source = spec["source"]
    schema, table = source.split(".")
    target = f"`{CATALOG}`.`raw_{schema}`.`{table}`"
    mode = spec.get("mode", CONFIG.get("defaults", {}).get("mode", "full"))
    started = datetime.datetime.utcnow()
    log = dict(run_id=RUN_ID, deployment_id=DEPLOYMENT_ID, source_table=source,
               target_table=target.replace("`", ""), mode=mode, status="SUCCESS",
               rows_written=None, watermark_from=None, started_at=started, finished_at=None, message=None)
    try:
        cols = source_columns(schema, table)
        if not cols:
            log.update(status="SKIPPED", message="table not found in source")
            return log
        exprs, kept, missing = select_list(cols, spec)
        notes = [f"config columns not in source: {missing}"] if missing else []

        where = ""
        exists = spark.catalog.tableExists(target.replace("`", ""))
        if mode == "incremental":
            wm = spec["watermark"]
            if exists:
                wm_type = next(c["data_type"] for c in kept if c["column_name"] == wm)
                current, literal = current_watermark(target, wm, wm_type)
                if literal is not None:
                    where = f' WHERE "{wm}" > {literal}'
                    log["watermark_from"] = str(current)

        query = f'SELECT {", ".join(exprs)} FROM "{schema}"."{table}"{where}'
        if DRY_RUN:
            log.update(status="SKIPPED", message="dry run: " + query[:1500])
            return log

        df = read_query(query)
        for col in spec.get("redact", []):
            if col in df.columns:
                df = df.withColumn(col, F.regexp_replace(F.regexp_replace(F.col(col), SECRET_JSON_RE, '$1"***"'),
                                                         SECRET_CODE_RE, "$1***"))
        df = (df.withColumn("_deployment_id", F.lit(DEPLOYMENT_ID))
                .withColumn("_source_table", F.lit(source))
                .withColumn("_ingested_at", F.current_timestamp()))

        version_before = DeltaTable.forName(spark, target).history(1).first()["version"] if exists else -1
        writer = df.write.format("delta").option("mergeSchema", "true")
        if mode == "incremental":
            writer.mode("append").saveAsTable(target)
        elif exists:
            writer.mode("overwrite").option("replaceWhere", f"_deployment_id = '{DEPLOYMENT_ID}'").saveAsTable(target)
        else:
            writer.mode("overwrite").saveAsTable(target)

        last = DeltaTable.forName(spark, target).history(1).first()
        # Appending an empty DataFrame creates no commit, so an unchanged version means nothing was written.
        metrics = (last["operationMetrics"] or {}) if last["version"] != version_before else {}
        log["rows_written"] = int(metrics.get("numOutputRows", 0))
        log["message"] = "; ".join(notes) or None
    except Exception as exc:
        log.update(status="FAILED", message=str(exc)[:4000])
    finally:
        log["finished_at"] = datetime.datetime.utcnow()
    return log


specs = [t for t in CONFIG["tables"] if not ONLY or t["source"] in ONLY]

# Pre-flight: fail fast with a clear reason instead of 72 identical errors.
try:
    read_query("SELECT 1 AS ok").collect()
except Exception as exc:
    raise RuntimeError(
        "Cannot query PostgreSQL over JDBC. Check, in this order:\n"
        "  1. Compute: run on a classic cluster with *Dedicated (single user)* access mode. Serverless and "
        "Standard (shared) compute can block JDBC reads.\n"
        "  2. Network: the cluster must reach the database host and port (try %sh nc -vz <host> <port>).\n"
        f"  3. Secrets: scope '{SCOPE}' must hold pg_host, pg_port, pg_database, pg_user, pg_password.\n"
        f"Original error: {str(exc).splitlines()[0][:500]}"
    ) from exc

visible = {
    r.table_schema: r.n
    for r in read_query(
        "SELECT table_schema, count(*) AS n FROM information_schema.tables "
        "WHERE table_schema IN ('core', 'mcp', 'process_studio', 'rbac', 'trulens') GROUP BY table_schema"
    ).collect()
}
needed = sorted({t["source"].split(".")[0] for t in specs})
unseen = [schema for schema in needed if not visible.get(schema)]
if unseen:
    raise RuntimeError(
        f"The database user cannot see any tables in schema(s) {unseen}. Grant it access, e.g. "
        f"GRANT USAGE ON SCHEMA {', '.join(unseen)} TO <user>; "
        f"GRANT SELECT ON ALL TABLES IN SCHEMA {', '.join(unseen)} TO <user>;"
    )
print("PostgreSQL reachable. Tables visible per schema:", visible)
with ThreadPoolExecutor(max_workers=PARALLELISM) as pool:
    results = list(pool.map(ingest, specs))

# COMMAND ----------

log_df = spark.createDataFrame(
    results,
    "run_id string, deployment_id string, source_table string, target_table string, mode string, status string, "
    "rows_written bigint, watermark_from string, started_at timestamp, finished_at timestamp, message string",
)
if not DRY_RUN:
    log_df.write.mode("append").saveAsTable(f"`{CATALOG}`.ops.ingestion_log")
display(log_df.orderBy("status", "source_table"))

failed = [r["source_table"] for r in results if r["status"] == "FAILED"]
missing = [r["source_table"] for r in results if r["status"] == "SKIPPED" and r["message"] == "table not found in source"]
if failed or missing:
    raise RuntimeError(
        f"{len(failed)} table(s) failed: {failed}. {len(missing)} table(s) not found or not readable in the source: "
        f"{missing}. Later steps need these tables. See {CATALOG}.ops.ingestion_log for the error of each table."
    )
