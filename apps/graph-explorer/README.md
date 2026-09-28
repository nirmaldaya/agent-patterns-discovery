# APDI Graph Explorer (Databricks App)

An interactive graph explorer for the APDI knowledge graph: agents, workflows, tools, MCP servers, knowledge
bases, guardrails, processes, models, org units and their labels (industry, SDLC phase, tech, business function,
archetype), and every relationship between them.

**FastAPI** backend + **React** (Vite, TypeScript, Cytoscape.js) frontend, deployed as one Databricks App. It reads
the `graph_*` tables built by `notebooks/05_build_graph.py` and `06_graph_analytics.py` (see
[`docs/02_graph_model.md`](../../docs/02_graph_model.md)).

## What you can do

| | How |
|---|---|
| Start from an overview | **Start** tab: how two dimensions relate (e.g. SDLC phase × technology), a solution pattern, or the technology co-occurrence map |
| Find anything | **Search** tab: type a name, filter by type |
| Place what you want | **Drag** a search result onto the canvas. It lands where you drop it and links to what is already there. Or click **+** (add) / **⤢** (add with neighbours) |
| Grow the graph | **Double-click** a node, press **E**, or use **Expand**. The details panel adds one kind of neighbour at a time (e.g. only the tools of an agent) |
| Select / deselect | Click, **Ctrl/Shift+click** to add, **Shift+drag** on the background to box-select, **Select neighbours** |
| Choose what is shown | **Filters** tab: tick or untick node types (by category or one by one) and relationship types, set a minimum weight. Unticked types are also skipped when expanding |
| Arrange | Drag nodes anywhere, **Pin** them so layouts leave them alone, re-arrange with force-directed, concentric, hierarchy, circle or grid |
| Trim | **Remove** (Del), **Keep only**, **Clear**, **Undo** (Ctrl+Z) |
| Connect what you placed | **Find links** adds every relationship among the nodes on the canvas |
| Read the analytics | Node size = importance (PageRank) or connections. **Group into solution patterns** draws community boxes. The details panel shows metrics, labels, owner and pattern |
| Keep and share | **Views** tab saves the graph (nodes, positions, pins) in the browser. Export / import JSON, export PNG |
| Accessible | Colour = category (validated for colour-vision deficiency), shape = type, labels always on, **Table** view of the canvas, keyboard shortcuts, light and dark themes |

## Project layout

```
apps/graph-explorer/
├── app.yaml               Databricks Apps entry point and environment
├── requirements.txt       Python dependencies (installed by Databricks)
├── package.json           React build (Databricks runs npm install + npm run build)
├── backend/               FastAPI: main.py (routes), graph.py (queries), db.py (Databricks SQL / DuckDB)
├── src/                   React app: App.tsx, components/, theme.ts (colours, shapes)
├── sample_data/           Synthetic graph tables (parquet) for local development
└── tests/                 API tests (run against sample_data)
```

## Run locally

Prerequisites: Python 3.10+, Node 18+.

```bash
cd apps/graph-explorer
pip install -r requirements-dev.txt
npm install

# API on :8000 using the bundled synthetic sample data (DuckDB, no workspace needed)
APDI_LOCAL_DATA=sample_data python -m backend.server

# in a second terminal: UI with hot reload on http://localhost:5173 (proxies /api to :8000)
npm run dev
```

To run against a real workspace locally instead, unset `APDI_LOCAL_DATA` and set `DATABRICKS_HOST`, your usual
Databricks auth (e.g. `DATABRICKS_CONFIG_PROFILE`) and `DATABRICKS_WAREHOUSE_ID`.

Checks: `pytest -q` (API), `npm run typecheck`, `npm run build`.

To develop against your own data, export the five `graph_*` tables from Databricks as parquet
(`graph_nodes.parquet`, `graph_edges.parquet`, …) into a folder and point `APDI_LOCAL_DATA` at it.

## Deploy to Databricks

1. **Build the graph tables.** Run the `apdi-refresh` job (or notebooks 05 and 06) so `<catalog>.explore.graph_*` exist.
2. **Create the app.** In the workspace, **Compute → Apps → Create app → Custom**, name it `apdi-graph-explorer`.
3. **Add the SQL warehouse resource.** In the app's configuration, add an **App resource → SQL warehouse** with
   permission **Can use** and resource key **`sql-warehouse`**. `app.yaml` reads its id from that key.
4. **Grant the app's service principal read access** (its id is shown on the app's page):

   ```sql
   GRANT USE CATALOG ON CATALOG apdi TO `<app-service-principal-application-id>`;
   GRANT USE SCHEMA, SELECT ON SCHEMA apdi.explore TO `<app-service-principal-application-id>`;
   ```

5. **Deploy the code.** Either point the deployment at this folder in a workspace Git folder
   (`/Workspace/.../agent-patterns-discovery/apps/graph-explorer`), or from your machine:

   ```bash
   databricks sync apps/graph-explorer /Workspace/Users/<you>/apdi-graph-explorer
   databricks apps deploy apdi-graph-explorer --source-code-path /Workspace/Users/<you>/apdi-graph-explorer
   ```

   During deployment Databricks installs `requirements.txt`, runs `npm install` and `npm run build` (because
   `package.json` is present), then starts `python -m backend.server` from `app.yaml`.
6. **Share it.** Give users **Can use** on the app. Everyone sees the same data, read as the app's service principal.

Settings in `app.yaml`: `APDI_CATALOG` (default `apdi`), `APDI_SCHEMA` (`explore`), `APDI_MAX_NODES` (largest
response, default 300). If your workspace cannot reach the npm registry during deployment, run `npm run build`
locally and deploy with the `dist/` folder included (it is git-ignored by default).

## API

| Method | Path | Returns |
|---|---|---|
| GET | `/api/meta` | Node and edge type counts, deployments, whether metrics exist, maxima for sizing |
| GET | `/api/search?q=&types=&limit=` | Nodes whose label matches, most important first |
| POST | `/api/expand` `{ids, edge_types, node_types, exclude, limit}` | Strongest neighbours of `ids`, plus every link to nodes already on the canvas |
| POST | `/api/connect` `{ids}` | Edges among `ids` |
| POST | `/api/nodes` `{ids}` | Nodes with metrics |
| GET | `/api/node?id=` | One node with relationship counts by type and direction, and its pattern |
| GET | `/api/overview?artifact_type=&src_type=&dst_type=&min_count=` | Dimension-to-dimension summary graph |
| GET | `/api/communities`, `/api/communities/{id}` | Solution patterns, and one pattern's subgraph |
| GET | `/api/cooccurrence?kind=TECH\|TOOL&min_weight=` | Used-together map |
| GET | `/api/insights` | Most depended-on components, bridges and islands |

All user input is bound as query parameters. Type codes are validated, and table names come only from configuration.
