import { edgeInfo, typeInfo, type Mode } from "../theme";
import type { NodeDetail } from "../types";
import { ShapeIcon } from "./ShapeIcon";

interface Props {
  mode: Mode;
  detail: NodeDetail | null;
  loading: boolean;
  selectedCount: number;
  canvasCount: number;
  onExpandRelation(edgeType: string, otherType: string): void;
  onExpand(): void;
  onRemove(): void;
  onKeepOnly(): void;
  onPin(): void;
  onSelectNeighbours(): void;
  onShowPattern(communityId: number): void;
}

const LABEL_KEYS: [string, string][] = [
  ["industries", "Industry"],
  ["sdlc_phases", "SDLC phase"],
  ["tech_stack", "Technology"],
  ["business_functions", "Business function"],
  ["archetypes", "Archetype"],
];
const ORG_KEYS: [string, string][] = [
  ["organization", "Organisation"],
  ["business_unit", "Business unit"],
  ["project", "Project"],
  ["team", "Team"],
];

const fmt = (v: number | null | undefined, digits = 3) => (v === null || v === undefined ? "–" : Number(v).toFixed(digits));

export function DetailsPanel(p: Props) {
  if (p.selectedCount === 0) {
    return (
      <div className="details empty-details">
        <h2>Details</h2>
        <p className="muted">Select a node to see what it is and what it connects to.</p>
        <ul className="tips">
          <li><b>Double-click</b> a node to expand its neighbours</li>
          <li><b>Right-click</b> a node for actions</li>
          <li><b>Shift + drag</b> on the background to select several</li>
          <li><b>Drag</b> search results onto the canvas</li>
          <li><kbd>Del</kbd> remove · <kbd>E</kbd> expand · <kbd>Ctrl</kbd>+<kbd>Z</kbd> undo</li>
        </ul>
      </div>
    );
  }

  const actions = (
    <div className="row gap wrap">
      <button className="primary" onClick={p.onExpand}>Expand</button>
      <button onClick={p.onSelectNeighbours}>Select neighbours</button>
      <button onClick={p.onPin}>Pin / unpin</button>
      <button onClick={p.onKeepOnly}>Keep only</button>
      <button className="danger" onClick={p.onRemove}>Remove</button>
    </div>
  );

  if (p.selectedCount > 1) {
    return (
      <div className="details">
        <h2>{p.selectedCount} nodes selected</h2>
        {actions}
      </div>
    );
  }

  if (p.loading || !p.detail) {
    return (
      <div className="details">
        <h2>Details</h2>
        <p className="muted">Loading…</p>
      </div>
    );
  }

  const { node, relations, community } = p.detail;
  const props = (node.properties ?? {}) as Record<string, unknown>;
  const orgPath = ORG_KEYS.map(([k]) => props[k]).filter(Boolean) as string[];

  return (
    <div className="details">
      <div className="details-head">
        <ShapeIcon type={node.type} mode={p.mode} size={20} />
        <div>
          <h2>{node.label}</h2>
          <span className="muted">{typeInfo(node.type).label}{node.status ? ` · ${node.status}` : ""}</span>
        </div>
      </div>
      {node.description && <p className="description">{node.description}</p>}
      {actions}

      {orgPath.length > 0 && (
        <section>
          <h3>Owned by</h3>
          <p>{orgPath.join(" › ")}</p>
        </section>
      )}

      {LABEL_KEYS.some(([k]) => Array.isArray(props[k]) && (props[k] as unknown[]).length > 0) && (
        <section>
          <h3>Labels</h3>
          {LABEL_KEYS.map(([k, label]) =>
            Array.isArray(props[k]) && (props[k] as unknown[]).length > 0 ? (
              <div key={k} className="chips">
                <span className="muted small">{label}</span>
                {(props[k] as string[]).map((v) => <span key={v} className="chip">{v}</span>)}
              </div>
            ) : null,
          )}
          {props.industry_source === "INFERRED_KEYWORD" && <p className="muted small">Industry inferred from keywords.</p>}
        </section>
      )}

      <section>
        <h3>Network</h3>
        <dl className="metrics">
          <dt>Connections</dt><dd className="tabular">{node.degree ?? "–"}</dd>
          <dt>Importance (PageRank)</dt><dd className="tabular">{fmt(node.pagerank)}</dd>
          <dt>Bridging (betweenness)</dt><dd className="tabular">{fmt(node.betweenness)}</dd>
          {node.run_count !== null && node.run_count !== undefined && (<><dt>Runs</dt><dd className="tabular">{node.run_count}</dd></>)}
          {node.is_isolated && (<><dt>Island</dt><dd>not wired to any other artifact</dd></>)}
        </dl>
      </section>

      {community && (
        <section>
          <h3>Solution pattern</h3>
          <p>{community.community_name} <span className="muted small">({community.size} nodes)</span></p>
          <button onClick={() => p.onShowPattern(community.community_id)}>Show this pattern</button>
        </section>
      )}

      <section>
        <h3>Relationships</h3>
        <p className="muted small">Add only one kind of neighbour at a time.</p>
        <ul className="relations">
          {relations.map((r) => (
            <li key={`${r.edge_type}-${r.direction}-${r.other_type}`}>
              <span className="grow">
                {r.direction === "out" ? `${edgeInfo(r.edge_type).label} →` : `← ${edgeInfo(r.edge_type).label}`}{" "}
                <ShapeIcon type={r.other_type} mode={p.mode} size={11} /> {typeInfo(r.other_type).label}
              </span>
              <span className="muted tabular">{r.count}</span>
              <button className="icon-btn" onClick={() => p.onExpandRelation(r.edge_type, r.other_type)} title="Add these neighbours" aria-label={`Add ${typeInfo(r.other_type).label} via ${edgeInfo(r.edge_type).label}`}>+</button>
            </li>
          ))}
        </ul>
      </section>
      <p className="muted small">{node.id}</p>
    </div>
  );
}
