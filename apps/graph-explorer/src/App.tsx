import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { ContextMenu, type MenuAction } from "./components/ContextMenu";
import { DetailsPanel } from "./components/DetailsPanel";
import { ExploreTab, type OverviewParams } from "./components/ExploreTab";
import { FiltersTab, type DisplaySettings } from "./components/FiltersTab";
import { GraphCanvas, type CanvasHandle, type CanvasStats, type HoverInfo, type LayoutName } from "./components/GraphCanvas";
import { Legend } from "./components/Legend";
import { SearchTab } from "./components/SearchTab";
import { TableView } from "./components/TableView";
import { Tooltip } from "./components/Tooltip";
import { ViewsTab } from "./components/ViewsTab";
import { NODE_TYPES, type Mode, type StyleOptions } from "./theme";
import type { Community, GraphNode, GraphPayload, Insights, Meta, NodeDetail } from "./types";
import { download, downloadJson, loadViews, storeViews, type SavedView } from "./views";

type Tab = "search" | "explore" | "filters" | "views";
type Toast = { kind: "info" | "error"; text: string } | null;

const EMPTY_STATS: CanvasStats = { nodes: 0, edges: 0, byType: {}, byEdgeType: {} };
const HISTORY_LIMIT = 40;

function initialMode(): Mode {
  try {
    const saved = window.localStorage.getItem("apdi.theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* storage unavailable */
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const canvas = useRef<CanvasHandle>(null);
  const history = useRef<ReturnType<CanvasHandle["snapshot"]>[]>([]);
  const detailRequest = useRef(0);

  const [mode, setMode] = useState<Mode>(initialMode);
  const [tab, setTab] = useState<Tab>("explore");
  const [view, setView] = useState<"graph" | "table">("graph");
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [communities, setCommunities] = useState<Community[]>([]);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [stats, setStats] = useState<CanvasStats>(EMPTY_STATS);
  const [selected, setSelected] = useState<string[]>([]);
  const [detail, setDetail] = useState<NodeDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());
  const [hiddenEdgeTypes, setHiddenEdgeTypes] = useState<Set<string>>(new Set());
  const [settings, setSettings] = useState<DisplaySettings>({
    sizeMode: "pagerank", showEdgeLabels: false, highlightNeighbours: true, groupByCommunity: false, minWeight: 1, expandLimit: 25,
  });
  const [layout, setLayout] = useState<LayoutName>("fcose");
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const [menu, setMenu] = useState<{ id: string | null; x: number; y: number } | null>(null);
  const [busy, setBusy] = useState(0);
  const [toast, setToast] = useState<Toast>(null);
  const [views, setViews] = useState<SavedView[]>(loadViews);
  const [canUndo, setCanUndo] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.theme = mode;
    try {
      window.localStorage.setItem("apdi.theme", mode);
    } catch {
      /* ignore */
    }
  }, [mode]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), toast.kind === "error" ? 8000 : 4500);
    return () => window.clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    api.meta().then(setMeta).catch((e: Error) => setMetaError(e.message));
    api.communities().then(setCommunities).catch(() => setCommunities([]));
    api.insights().then(setInsights).catch(() => setInsights(null));
  }, []);

  const notify = (kind: "info" | "error", text: string) => setToast({ kind, text });

  const run = useCallback(async (label: string, fn: () => Promise<void>) => {
    setBusy((b) => b + 1);
    try {
      await fn();
    } catch (e) {
      notify("error", `${label} failed: ${(e as Error).message}`);
    } finally {
      setBusy((b) => b - 1);
    }
  }, []);

  const remember = () => {
    const c = canvas.current;
    if (!c) return;
    history.current.push(c.snapshot());
    if (history.current.length > HISTORY_LIMIT) history.current.shift();
    setCanUndo(true);
  };

  const undo = () => {
    const snap = history.current.pop();
    if (snap) canvas.current?.restore(snap);
    setCanUndo(history.current.length > 0);
  };

  const allTypes = useMemo(
    () => [...new Set([...(meta?.node_types ?? []).map((t) => t.type), ...Object.keys(NODE_TYPES)])],
    [meta],
  );

  // ---- graph actions -------------------------------------------------------------------------------------------
  const expand = (ids: string[], edgeTypes: string[] = [], nodeTypes?: string[]) =>
    run("Expand", async () => {
      if (ids.length === 0) return;
      const types = nodeTypes ?? (hiddenTypes.size ? allTypes.filter((t) => !hiddenTypes.has(t)) : []);
      const res = await api.expand({ ids, edge_types: edgeTypes, node_types: types, exclude: canvas.current!.nodeIds(), limit: settings.expandLimit });
      remember();
      const added = canvas.current!.addGraph(res.nodes, res.edges, { anchorIds: ids });
      if (added.length === 0) notify("info", hiddenTypes.size ? "No new neighbours with the current filters." : "No new neighbours.");
      else if (res.truncated) notify("info", `Added the ${added.length} strongest of ${res.available} neighbours. Raise “Nodes added per expand” in Filters, or expand by one relationship.`);
    });

  const addNode = (node: GraphNode, position?: { x: number; y: number }, expandAfter = false) =>
    run("Add node", async () => {
      const c = canvas.current!;
      remember();
      c.addGraph([node], [], { position });
      const edges = await api.connect(c.nodeIds());
      c.addGraph([], edges.filter((e) => e.source === node.id || e.target === node.id));
      c.select([node.id]);
      if (expandAfter) await expand([node.id]);
    });

  const findLinks = () =>
    run("Find links", async () => {
      const c = canvas.current!;
      const before = c.elements().edges.length;
      remember();
      c.addGraph([], await api.connect(c.nodeIds()));
      const added = c.elements().edges.length - before;
      notify("info", added ? `Added ${added} relationships between the nodes on the canvas.` : "All relationships between these nodes are already shown.");
    });

  const loadPayload = (label: string, fetcher: () => Promise<GraphPayload>, replace: boolean) =>
    run(label, async () => {
      const res = await fetcher();
      remember();
      if (replace) canvas.current!.clear();
      canvas.current!.addGraph(res.nodes, res.edges, { fullLayout: true });
      if (res.nodes.length === 0) notify("info", "Nothing to show for this selection.");
      else if (res.truncated) notify("info", "Showing the strongest part only. Narrow the selection to see everything.");
    });

  const showOverview = (p: OverviewParams, replace: boolean) => loadPayload("Overview", () => api.overview(p), replace);
  const showCommunity = (id: number, replace: boolean) => loadPayload("Pattern", () => api.community(id, 80), replace);
  const showCooccurrence = (kind: string, min: number, replace: boolean) =>
    loadPayload("Co-occurrence", () => api.cooccurrence(kind, min), replace);

  const removeSelected = () => {
    const ids = canvas.current?.selectedIds() ?? [];
    if (!ids.length) return;
    remember();
    canvas.current!.removeNodes(ids);
  };
  const keepOnlySelected = () => {
    const ids = canvas.current?.selectedIds() ?? [];
    if (!ids.length) return;
    remember();
    canvas.current!.keepOnly(ids);
  };
  const clearCanvas = () => {
    if (!stats.nodes) return;
    remember();
    canvas.current?.clear();
  };

  // ---- selection details -----------------------------------------------------------------------------------------
  useEffect(() => {
    if (selected.length !== 1) {
      setDetail(null);
      return;
    }
    const token = ++detailRequest.current;
    setDetailLoading(true);
    api
      .node(selected[0])
      .then((d) => token === detailRequest.current && setDetail(d))
      .catch((e: Error) => token === detailRequest.current && notify("error", `Details failed: ${e.message}`))
      .finally(() => token === detailRequest.current && setDetailLoading(false));
  }, [selected]);

  // ---- saved views -----------------------------------------------------------------------------------------------
  const saveView = (name: string) => {
    const next = [{ name, savedAt: new Date().toISOString(), snapshot: canvas.current!.snapshot() }, ...views.filter((v) => v.name !== name)];
    setViews(next);
    notify(storeViews(next) ? "info" : "error", storeViews(next) ? `Saved “${name}”.` : "Could not save: browser storage is full or disabled.");
  };
  const loadView = (v: SavedView) => {
    remember();
    canvas.current!.restore(v.snapshot);
    notify("info", `Loaded “${v.name}”.`);
  };
  const deleteView = (name: string) => {
    const next = views.filter((v) => v.name !== name);
    setViews(next);
    storeViews(next);
  };
  const importView = async (file: File) => {
    try {
      const parsed = JSON.parse(await file.text());
      const snapshot = parsed.snapshot ?? parsed;
      if (!Array.isArray(snapshot?.nodes) || !Array.isArray(snapshot?.edges)) throw new Error("not an APDI graph export");
      remember();
      canvas.current!.restore(snapshot);
      notify("info", `Imported ${snapshot.nodes.length} nodes.`);
    } catch (e) {
      notify("error", `Import failed: ${(e as Error).message}`);
    }
  };

  // ---- keyboard ----------------------------------------------------------------------------------------------------
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || el.isContentEditable) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        undo();
      } else if (e.key === "Delete" || e.key === "Backspace") {
        removeSelected();
      } else if (e.key.toLowerCase() === "e") {
        expand(canvas.current?.selectedIds() ?? []);
      } else if (e.key.toLowerCase() === "f") {
        canvas.current?.fit();
      } else if (e.key === "Escape") {
        setMenu(null);
        canvas.current?.select([]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // ---- derived -------------------------------------------------------------------------------------------------------
  const styleOptions: StyleOptions = useMemo(
    () => ({ mode, sizeMode: settings.sizeMode, showEdgeLabels: settings.showEdgeLabels, maxPagerank: meta?.max_pagerank ?? 0, maxDegree: meta?.max_degree ?? 0 }),
    [mode, settings.sizeMode, settings.showEdgeLabels, meta],
  );
  const communityNames = useMemo(() => new Map(communities.map((c) => [c.community_id, c.community_name])), [communities]);
  const tableData = useMemo(() => (view === "table" ? canvas.current?.elements() ?? { nodes: [], edges: [] } : { nodes: [], edges: [] }), [view, stats]);

  const menuActions: MenuAction[] = menu?.id
    ? [
        { label: "Expand neighbours", shortcut: "E", onClick: () => expand(canvas.current!.selectedIds()) },
        { label: "Select neighbours", onClick: () => canvas.current!.selectNeighbours() },
        { label: "Pin / unpin position", onClick: () => canvas.current!.togglePin(canvas.current!.selectedIds()) },
        { label: "Keep only selected", onClick: keepOnlySelected },
        { label: "Remove", shortcut: "Del", onClick: removeSelected },
      ]
    : [
        { label: "Find links between nodes", onClick: findLinks, disabled: stats.nodes < 2 },
        { label: "Re-arrange", onClick: () => canvas.current!.runLayout(layout) },
        { label: "Fit to screen", shortcut: "F", onClick: () => canvas.current!.fit() },
        { label: "Undo", shortcut: "Ctrl Z", onClick: undo, disabled: !canUndo },
        { label: "Clear canvas", onClick: clearCanvas, disabled: stats.nodes === 0 },
      ];

  const dataLabel = meta ? (meta.mode === "local" ? "Sample data (local)" : `${meta.catalog}.${meta.schema}`) : "";

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>APDI Graph Explorer</h1>
          <span className="muted small">Agents, workflows, tools and how they connect{dataLabel ? ` · ${dataLabel}` : ""}</span>
        </div>
        <div className="row gap">
          {busy > 0 && <span className="spinner" role="status" aria-label="Loading" />}
          <button onClick={() => setMode(mode === "light" ? "dark" : "light")} aria-label="Toggle light or dark theme">
            {mode === "light" ? "Dark" : "Light"} theme
          </button>
        </div>
      </header>

      {metaError && (
        <div className="banner error" role="alert">
          Cannot read the graph tables: {metaError}. Check the app's SQL warehouse resource and that its service principal can
          read <code>{"<catalog>.explore"}</code>.
        </div>
      )}

      <div className="app-body">
        <aside className="sidebar">
          <nav className="tabs" role="tablist">
            {(["explore", "search", "filters", "views"] as Tab[]).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
                {t === "explore" ? "Start" : t === "search" ? "Search" : t === "filters" ? "Filters" : "Views"}
              </button>
            ))}
          </nav>
          {tab === "search" && <SearchTab mode={mode} meta={meta} onAdd={(n) => addNode(n)} onAddExpand={(n) => addNode(n, undefined, true)} />}
          {tab === "explore" && (
            <ExploreTab
              mode={mode} meta={meta} communities={communities} insights={insights}
              onOverview={showOverview} onCommunity={showCommunity} onCooccurrence={showCooccurrence}
              onAdd={(n) => addNode(n)} onAddExpand={(n) => addNode(n, undefined, true)}
            />
          )}
          {tab === "filters" && (
            <FiltersTab
              mode={mode} meta={meta} onCanvas={stats.byType} onCanvasEdges={stats.byEdgeType}
              hiddenTypes={hiddenTypes} setHiddenTypes={setHiddenTypes}
              hiddenEdgeTypes={hiddenEdgeTypes} setHiddenEdgeTypes={setHiddenEdgeTypes}
              settings={settings} setSettings={setSettings}
            />
          )}
          {tab === "views" && (
            <ViewsTab
              views={views} canSave={stats.nodes > 0} onSave={saveView} onLoad={loadView} onDelete={deleteView}
              onExport={() => downloadJson(`apdi-graph-${new Date().toISOString().slice(0, 10)}.json`, { version: 1, snapshot: canvas.current!.snapshot() })}
              onImport={importView}
            />
          )}
        </aside>

        <main className="stage">
          <div className="toolbar" role="toolbar" aria-label="Graph actions">
            <button onClick={() => expand(selected)} disabled={!selected.length} title="Add neighbours of the selected nodes (E)">Expand</button>
            <button onClick={findLinks} disabled={stats.nodes < 2} title="Add every relationship between the nodes on the canvas">Find links</button>
            <button onClick={removeSelected} disabled={!selected.length} title="Remove selected (Del)">Remove</button>
            <button onClick={keepOnlySelected} disabled={!selected.length}>Keep only</button>
            <button onClick={() => canvas.current!.togglePin(selected)} disabled={!selected.length} title="Pinned nodes stay put when re-arranging">Pin</button>
            <span className="sep" />
            <select value={layout} onChange={(e) => setLayout(e.target.value as LayoutName)} aria-label="Layout">
              <option value="fcose">Force-directed</option>
              <option value="concentric">Concentric</option>
              <option value="breadthfirst">Hierarchy</option>
              <option value="circle">Circle</option>
              <option value="grid">Grid</option>
            </select>
            <button onClick={() => canvas.current!.runLayout(layout)} disabled={!stats.nodes}>Re-arrange</button>
            <button onClick={() => canvas.current!.fit()} disabled={!stats.nodes} title="Fit (F)">Fit</button>
            <span className="sep" />
            <button onClick={undo} disabled={!canUndo} title="Undo (Ctrl+Z)">Undo</button>
            <button onClick={clearCanvas} disabled={!stats.nodes}>Clear</button>
            <span className="sep" />
            <div className="segmented" role="group" aria-label="View">
              <button className={view === "graph" ? "active" : ""} aria-pressed={view === "graph"} onClick={() => setView("graph")}>Graph</button>
              <button className={view === "table" ? "active" : ""} aria-pressed={view === "table"} onClick={() => setView("table")}>Table</button>
            </div>
            <button onClick={() => download("apdi-graph.png", canvas.current!.png())} disabled={!stats.nodes}>PNG</button>
            <span className="grow" />
            <span className="muted small tabular">{stats.nodes} nodes · {stats.edges} relationships</span>
          </div>

          <div className="canvas-wrap">
            <GraphCanvas
              ref={canvas}
              style={styleOptions}
              hiddenTypes={hiddenTypes}
              hiddenEdgeTypes={hiddenEdgeTypes}
              minWeight={settings.minWeight}
              highlightNeighbours={settings.highlightNeighbours}
              groupByCommunity={settings.groupByCommunity}
              communityNames={communityNames}
              onSelect={setSelected}
              onExpand={(id) => expand([id])}
              onContext={(id, x, y) => setMenu(x < 0 ? null : { id, x, y })}
              onHover={setHover}
              onDropNode={(node, position) => addNode(node, position)}
              onChange={setStats}
            />
            <Legend mode={mode} byType={stats.byType} byEdgeType={stats.byEdgeType} />
            <Tooltip info={menu ? null : hover} />
            {menu && (
              <ContextMenu x={menu.x} y={menu.y} title={menu.id ? `${selected.length || 1} selected` : "Canvas"} actions={menuActions} onClose={() => setMenu(null)} />
            )}
            {stats.nodes === 0 && view === "graph" && (
              <div className="empty-state">
                <h2>Build your graph</h2>
                <p className="muted">Start from a view below, or search on the left and drag nodes onto the canvas.</p>
                <div className="row gap wrap center">
                  <button className="primary" onClick={() => showOverview({ artifact_type: "AGENT", src_type: "SDLC_PHASE", dst_type: "TECH", min_count: 1 }, true)}>SDLC phase × technology</button>
                  <button className="primary" onClick={() => showOverview({ artifact_type: "AGENT", src_type: "INDUSTRY", dst_type: "ARCHETYPE", min_count: 1 }, true)}>Industry × agent type</button>
                  {communities[0] && <button className="primary" onClick={() => showCommunity(communities[0].community_id, true)}>Largest solution pattern</button>}
                  <button onClick={() => setTab("search")}>Search</button>
                </div>
              </div>
            )}
            {view === "table" && (
              <TableView
                mode={mode} nodes={tableData.nodes} edges={tableData.edges}
                onFocus={(id) => {
                  setView("graph");
                  window.setTimeout(() => canvas.current?.select([id], true), 0);
                }}
              />
            )}
          </div>
        </main>

        <aside className="details-pane">
          <DetailsPanel
            mode={mode} detail={detail} loading={detailLoading} selectedCount={selected.length} canvasCount={stats.nodes}
            onExpandRelation={(edgeType, otherType) => expand(selected, [edgeType], [otherType])}
            onExpand={() => expand(selected)}
            onRemove={removeSelected}
            onKeepOnly={keepOnlySelected}
            onPin={() => canvas.current!.togglePin(selected)}
            onSelectNeighbours={() => canvas.current!.selectNeighbours()}
            onShowPattern={(id) => showCommunity(id, false)}
          />
        </aside>
      </div>

      {toast && (
        <div className={`toast ${toast.kind}`} role={toast.kind === "error" ? "alert" : "status"}>
          {toast.text}
          <button className="icon-btn" onClick={() => setToast(null)} aria-label="Dismiss">×</button>
        </div>
      )}
    </div>
  );
}
