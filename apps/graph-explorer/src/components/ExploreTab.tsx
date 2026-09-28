import { useState } from "react";
import type { Community, GraphNode, Insights, Meta } from "../types";
import type { Mode } from "../theme";
import { NodeListItem } from "./SearchTab";

export interface OverviewParams {
  artifact_type: string;
  src_type: string;
  dst_type: string;
  min_count: number;
}

const DIMENSIONS: [string, string][] = [
  ["INDUSTRY", "Industry"],
  ["BUSINESS_UNIT", "Business unit"],
  ["SDLC_PHASE", "SDLC phase"],
  ["TECH", "Technology"],
  ["BUSINESS_FUNCTION", "Business function"],
  ["ARCHETYPE", "Archetype"],
];

// Pairs available in graph_summary_edges (see notebooks/05_build_graph.py).
const PAIRS = new Set([
  "INDUSTRY>SDLC_PHASE", "INDUSTRY>TECH", "INDUSTRY>ARCHETYPE", "INDUSTRY>BUSINESS_FUNCTION",
  "BUSINESS_UNIT>SDLC_PHASE", "BUSINESS_UNIT>TECH", "BUSINESS_UNIT>ARCHETYPE", "SDLC_PHASE>TECH",
  "SDLC_PHASE>ARCHETYPE", "BUSINESS_FUNCTION>ARCHETYPE", "BUSINESS_FUNCTION>TECH", "ARCHETYPE>TECH",
]);

const SOURCES = DIMENSIONS.filter(([k]) => [...PAIRS].some((p) => p.startsWith(`${k}>`)));

interface Props {
  mode: Mode;
  meta: Meta | null;
  communities: Community[];
  insights: Insights | null;
  onOverview(p: OverviewParams, replace: boolean): void;
  onCommunity(id: number, replace: boolean): void;
  onCooccurrence(kind: string, minWeight: number, replace: boolean): void;
  onAdd(node: GraphNode): void;
  onAddExpand(node: GraphNode): void;
}

export function ExploreTab({ mode, meta, communities, insights, onOverview, onCommunity, onCooccurrence, onAdd, onAddExpand }: Props) {
  const [replace, setReplace] = useState(true);
  const [ov, setOv] = useState<OverviewParams>({ artifact_type: "AGENT", src_type: "INDUSTRY", dst_type: "SDLC_PHASE", min_count: 1 });
  const [coKind, setCoKind] = useState("TECH");
  const [coMin, setCoMin] = useState(1);
  const pairOk = PAIRS.has(`${ov.src_type}>${ov.dst_type}`);
  const targets = DIMENSIONS.filter(([k]) => PAIRS.has(`${ov.src_type}>${k}`));

  return (
    <div className="tab-body">
      <label className="check">
        <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
        Replace the canvas (untick to add to it)
      </label>

      <section className="card">
        <h3>Overview</h3>
        <p className="hint">How two dimensions relate. Link thickness is the number of artifacts carrying both values.</p>
        <div className="row">
          <label className="field">
            <span>Count</span>
            <select value={ov.artifact_type} onChange={(e) => setOv({ ...ov, artifact_type: e.target.value })}>
              <option value="AGENT">Agents</option>
              <option value="WORKFLOW">Workflows</option>
            </select>
          </label>
          <label className="field">
            <span>At least</span>
            <input type="number" min={1} value={ov.min_count} onChange={(e) => setOv({ ...ov, min_count: Math.max(1, Number(e.target.value) || 1) })} />
          </label>
        </div>
        <div className="row">
          <label className="field">
            <span>From</span>
            <select
              value={ov.src_type}
              onChange={(e) => {
                const src = e.target.value;
                const first = DIMENSIONS.find(([k]) => PAIRS.has(`${src}>${k}`));
                setOv({ ...ov, src_type: src, dst_type: PAIRS.has(`${src}>${ov.dst_type}`) ? ov.dst_type : first?.[0] ?? ov.dst_type });
              }}
            >
              {SOURCES.map(([k, l]) => (
                <option key={k} value={k}>{l}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>To</span>
            <select value={ov.dst_type} onChange={(e) => setOv({ ...ov, dst_type: e.target.value })}>
              {targets.map(([k, l]) => (
                <option key={k} value={k}>{l}</option>
              ))}
            </select>
          </label>
        </div>
        <button className="primary" disabled={!pairOk} onClick={() => onOverview(ov, replace)}>Show overview</button>
      </section>

      <section className="card">
        <h3>Solution patterns</h3>
        <p className="hint">Communities found by graph analytics: artifacts, tools and labels that belong together.</p>
        {!meta?.has_communities && <p className="muted">Run notebooks/06_graph_analytics.py to find patterns.</p>}
        <ul className="pattern-list">
          {communities.map((c) => (
            <li key={c.community_id}>
              <button className="pattern" onClick={() => onCommunity(c.community_id, replace)}>
                <span className="pattern-name">{c.community_name || `Pattern ${c.community_id}`}</span>
                <span className="muted small">
                  {c.artifact_count} artifacts · {c.size} nodes
                  {c.deployments?.length > 1 ? ` · ${c.deployments.length} customers` : ""}
                </span>
                {c.top_artifacts?.length > 0 && <span className="small">{c.top_artifacts.slice(0, 3).join(", ")}</span>}
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h3>Used together</h3>
        <p className="hint">Which technologies or tools appear in the same agents.</p>
        <div className="row">
          <label className="field">
            <span>Of</span>
            <select value={coKind} onChange={(e) => setCoKind(e.target.value)}>
              <option value="TECH">Technologies</option>
              <option value="TOOL">Tools</option>
            </select>
          </label>
          <label className="field">
            <span>Shared by at least</span>
            <input type="number" min={1} value={coMin} onChange={(e) => setCoMin(Math.max(1, Number(e.target.value) || 1))} />
          </label>
        </div>
        <button className="primary" onClick={() => onCooccurrence(coKind, coMin, replace)}>Show map</button>
      </section>

      {insights && (
        <section className="card">
          <h3>Insights</h3>
          <InsightList title="Most depended-on components" hint="Highest PageRank" nodes={insights.hubs} mode={mode} onAdd={onAdd} onAddExpand={onAddExpand} />
          <InsightList title="Bridges" hint="Connect otherwise separate parts" nodes={insights.bridges} mode={mode} onAdd={onAdd} onAddExpand={onAddExpand} />
          <InsightList title="Islands" hint="Artifacts wired to nothing" nodes={insights.islands} mode={mode} onAdd={onAdd} onAddExpand={onAddExpand} />
        </section>
      )}
    </div>
  );
}

function InsightList({ title, hint, nodes, mode, onAdd, onAddExpand }: { title: string; hint: string; nodes: GraphNode[]; mode: Mode; onAdd(n: GraphNode): void; onAddExpand(n: GraphNode): void }) {
  if (nodes.length === 0) return null;
  return (
    <details className="insight" open={title.startsWith("Most")}>
      <summary>
        {title} <span className="muted small">({nodes.length}) · {hint}</span>
      </summary>
      <ul className="node-list">
        {nodes.map((n) => (
          <NodeListItem key={n.id} node={n} mode={mode} onAdd={onAdd} onAddExpand={onAddExpand} />
        ))}
      </ul>
    </details>
  );
}
