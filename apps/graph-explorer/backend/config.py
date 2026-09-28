"""Runtime configuration, read from environment variables (set in app.yaml on Databricks)."""

import os
import re

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _identifier(name: str, value: str) -> str:
    if not _IDENT.match(value):
        raise ValueError(f"{name} must be a plain identifier, got {value!r}")
    return value


CATALOG = _identifier("APDI_CATALOG", os.getenv("APDI_CATALOG", "apdi"))
SCHEMA = _identifier("APDI_SCHEMA", os.getenv("APDI_SCHEMA", "explore"))

# Set by the Databricks Apps SQL warehouse resource (see app.yaml).
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "")

# Local development: a folder of parquet exports of the graph tables, queried with DuckDB instead of Databricks.
LOCAL_DATA_DIR = os.getenv("APDI_LOCAL_DATA", "")

# Upper bound on nodes returned by any single graph request, to keep the canvas readable.
MAX_NODES = int(os.getenv("APDI_MAX_NODES", "300"))

# Seconds to cache slow-changing responses (metadata, communities). The graph is rebuilt daily.
CACHE_SECONDS = int(os.getenv("APDI_CACHE_SECONDS", "300"))

PORT = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", "8000")))
