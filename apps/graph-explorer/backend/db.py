"""Query access to the APDI graph tables.

Two interchangeable back ends:
* DatabricksDatabase: a Databricks SQL warehouse via the SQL connector, authenticated as the app's service
  principal (credentials injected by Databricks Apps).
* DuckDBDatabase: parquet exports on local disk, for development and tests without a workspace.

Queries are written once with named parameters (``:name``) and ``{table}`` placeholders.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

from . import config

log = logging.getLogger(__name__)

TABLES = {
    "nodes": "graph_nodes",
    "edges": "graph_edges",
    "summary": "graph_summary_edges",
    "metrics": "graph_node_metrics",
    "communities": "graph_communities",
}


class Database:
    mode = "abstract"

    def __init__(self) -> None:
        self._available: dict[str, bool] = {}

    def table(self, key: str) -> str:
        raise NotImplementedError

    def query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError

    def render(self, sql: str) -> str:
        return sql.format(**{k: self.table(k) for k in TABLES})

    def has_table(self, key: str) -> bool:
        """Whether an optional table (metrics, communities) exists. Cached after the first check."""
        if key not in self._available:
            try:
                self.query(f"SELECT 1 FROM {{{key}}} LIMIT 1")
                self._available[key] = True
            except Exception as exc:  # table not built yet, or no permission
                log.warning("table %s unavailable: %s", key, str(exc).splitlines()[0])
                self._available[key] = False
        return self._available[key]


class DatabricksDatabase(Database):
    mode = "databricks"

    def __init__(self) -> None:
        super().__init__()
        from databricks.sdk.core import Config

        if not config.WAREHOUSE_ID:
            raise RuntimeError("DATABRICKS_WAREHOUSE_ID is not set. Add a SQL warehouse resource to the app.")
        self._cfg = Config()
        self._http_path = f"/sql/1.0/warehouses/{config.WAREHOUSE_ID}"
        self._local = threading.local()

    def table(self, key: str) -> str:
        return f"`{config.CATALOG}`.`{config.SCHEMA}`.`{TABLES[key]}`"

    def _connect(self):
        from databricks import sql as dbsql

        return dbsql.connect(
            server_hostname=self._cfg.host,
            http_path=self._http_path,
            credentials_provider=lambda: self._cfg.authenticate,
        )

    def query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        text = self.render(sql)
        for attempt in (1, 2):
            conn = getattr(self._local, "conn", None)
            if conn is None:
                conn = self._local.conn = self._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(text, parameters=params or {})
                    cols = [d[0] for d in cur.description or []]
                    return [dict(zip(cols, row)) for row in cur.fetchall()]
            except Exception:
                # A dropped or expired connection: reconnect once, then give up.
                self._local.conn = None
                try:
                    conn.close()
                except Exception:
                    pass
                if attempt == 2:
                    raise
        return []


class DuckDBDatabase(Database):
    mode = "local"

    _PARAM = re.compile(r"(?<![:\w]):([A-Za-z_]\w*)")

    def __init__(self, data_dir: str) -> None:
        super().__init__()
        import duckdb

        self._con = duckdb.connect()
        self._con.execute(f"CREATE SCHEMA IF NOT EXISTS {config.SCHEMA}")
        root = Path(data_dir)
        for key, name in TABLES.items():
            path = root / name
            source = f"{path}/*.parquet" if path.is_dir() else f"{path}.parquet"
            if path.is_dir() or Path(source).exists():
                self._con.execute(
                    f"CREATE OR REPLACE VIEW {config.SCHEMA}.{name} AS SELECT * FROM read_parquet('{source}')"
                )

    def table(self, key: str) -> str:
        return f"{config.SCHEMA}.{TABLES[key]}"

    def query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        text = self._PARAM.sub(r"$\1", self.render(sql))
        cur = self._con.cursor()
        try:
            cur.execute(text, params or {})
            cols = [d[0] for d in cur.description or []]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            cur.close()


_db: Database | None = None
_lock = threading.Lock()


def get_db() -> Database:
    global _db
    with _lock:
        if _db is None:
            _db = DuckDBDatabase(config.LOCAL_DATA_DIR) if config.LOCAL_DATA_DIR else DatabricksDatabase()
            log.info("graph data source: %s", _db.mode)
        return _db


def parse_json(value: Any) -> Any:
    if value is None or isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None
