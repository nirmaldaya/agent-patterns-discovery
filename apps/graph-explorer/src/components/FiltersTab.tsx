import { CATEGORIES, NODE_TYPES, edgeInfo, type Mode, type SizeMode } from "../theme";
import type { Meta } from "../types";
import { ShapeIcon } from "./ShapeIcon";

export interface DisplaySettings {
  sizeMode: SizeMode;
  showEdgeLabels: boolean;
  highlightNeighbours: boolean;
  groupByCommunity: boolean;
  minWeight: number;
  expandLimit: number;
}

interface Props {
  mode: Mode;
  meta: Meta | null;
  onCanvas: Record<string, number>;
  onCanvasEdges: Record<string, number>;
  hiddenTypes: Set<string>;
  setHiddenTypes(s: Set<string>): void;
  hiddenEdgeTypes: Set<string>;
  setHiddenEdgeTypes(s: Set<string>): void;
  settings: DisplaySettings;
  setSettings(s: DisplaySettings): void;
}

function toggle(set: Set<string>, keys: string[], on: boolean): Set<string> {
  const next = new Set(set);
  keys.forEach((k) => (on ? next.delete(k) : next.add(k)));
  return next;
}

export function FiltersTab({ mode, meta, onCanvas, onCanvasEdges, hiddenTypes, setHiddenTypes, hiddenEdgeTypes, setHiddenEdgeTypes, settings, setSettings }: Props) {
  const totals = new Map<string, number>();
  (meta?.node_types ?? []).forEach((t) => totals.set(t.type, (totals.get(t.type) ?? 0) + t.count));
  const edgeTotals = new Map((meta?.edge_types ?? []).map((t) => [t.type, t.count]));
  const edgeTypes = [...new Set([...edgeTotals.keys(), ...Object.keys(onCanvasEdges)])];
  const set = (patch: Partial<DisplaySettings>) => setSettings({ ...settings, ...patch });

  return (
    <div className="tab-body">
      <p className="hint">
        Untick a type to hide it on the canvas. Hidden types are also skipped when you expand a node, so you only pull in
        what you want.
      </p>
      <div className="row gap">
        <button onClick={() => setHiddenTypes(new Set())}>Show all</button>
        <button onClick={() => setHiddenTypes(new Set(["INDUSTRY", "SDLC_PHASE", "TECH", "BUSINESS_FUNCTION", "ARCHETYPE"]))}>Hide labels</button>
        <button onClick={() => setHiddenTypes(new Set(["DEPLOYMENT", "ORGANIZATION", "BUSINESS_UNIT", "PROJECT", "TEAM"]))}>Hide org</button>
      </div>

      {CATEGORIES.map((cat) => {
        const types = Object.keys(NODE_TYPES).filter((t) => NODE_TYPES[t].category === cat.key);
        const shown = types.filter((t) => !hiddenTypes.has(t)).length;
        return (
          <fieldset key={cat.key} className="type-group">
            <legend>
              <label className="check">
                <input
                  type="checkbox"
                  checked={shown === types.length}
                  ref={(el) => {
                    if (el) el.indeterminate = shown > 0 && shown < types.length;
                  }}
                  onChange={(e) => setHiddenTypes(toggle(hiddenTypes, types, e.target.checked))}
                />
                <span className="dot" style={{ background: cat.color[mode] }} />
                <b>{cat.label}</b>
              </label>
            </legend>
            {types.map((t) => (
              <label key={t} className="check type-check">
                <input type="checkbox" checked={!hiddenTypes.has(t)} onChange={(e) => setHiddenTypes(toggle(hiddenTypes, [t], e.target.checked))} />
                <ShapeIcon type={t} mode={mode} />
                <span className="grow">{NODE_TYPES[t].label}</span>
                <span className="muted small tabular" title="on canvas / in the graph">
                  {onCanvas[t] ?? 0} / {totals.get(t) ?? 0}
                </span>
              </label>
            ))}
          </fieldset>
        );
      })}

      <fieldset className="type-group">
        <legend><b>Relationships</b></legend>
        {edgeTypes.map((t) => (
          <label key={t} className="check type-check">
            <input type="checkbox" checked={!hiddenEdgeTypes.has(t)} onChange={(e) => setHiddenEdgeTypes(toggle(hiddenEdgeTypes, [t], e.target.checked))} />
            <i className={`line ${edgeInfo(t).style}`} />
            <span className="grow">{edgeInfo(t).label}</span>
            <span className="muted small tabular">{onCanvasEdges[t] ?? 0} / {edgeTotals.get(t) ?? 0}</span>
          </label>
        ))}
        <label className="field">
          <span>Minimum weight for calls, co-occurrence and overview links: <b>{settings.minWeight}</b></span>
          <input type="range" min={1} max={20} value={settings.minWeight} onChange={(e) => set({ minWeight: Number(e.target.value) })} />
        </label>
      </fieldset>

      <fieldset className="type-group">
        <legend><b>Display</b></legend>
        <label className="field">
          <span>Node size</span>
          <select value={settings.sizeMode} onChange={(e) => set({ sizeMode: e.target.value as SizeMode })}>
            <option value="pagerank">Importance (PageRank)</option>
            <option value="degree">Connections</option>
            <option value="uniform">Same size</option>
          </select>
        </label>
        <label className="check"><input type="checkbox" checked={settings.showEdgeLabels} onChange={(e) => set({ showEdgeLabels: e.target.checked })} /> Relationship labels</label>
        <label className="check"><input type="checkbox" checked={settings.highlightNeighbours} onChange={(e) => set({ highlightNeighbours: e.target.checked })} /> Highlight neighbours of the selection</label>
        <label className="check"><input type="checkbox" checked={settings.groupByCommunity} disabled={!meta?.has_metrics} onChange={(e) => set({ groupByCommunity: e.target.checked })} /> Group into solution patterns</label>
        <label className="field">
          <span>Nodes added per expand: <b>{settings.expandLimit}</b></span>
          <input type="range" min={5} max={Math.min(200, meta?.max_nodes ?? 200)} step={5} value={settings.expandLimit} onChange={(e) => set({ expandLimit: Number(e.target.value) })} />
        </label>
      </fieldset>
    </div>
  );
}
