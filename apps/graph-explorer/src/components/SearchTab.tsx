import { useEffect, useState } from "react";
import { api } from "../api";
import { NODE_TYPES, typeInfo, type Mode } from "../theme";
import type { GraphNode, Meta } from "../types";
import { NODE_MIME } from "./GraphCanvas";
import { ShapeIcon } from "./ShapeIcon";

interface Props {
  mode: Mode;
  meta: Meta | null;
  onAdd(node: GraphNode): void;
  onAddExpand(node: GraphNode): void;
}

export function NodeListItem({ node, mode, onAdd, onAddExpand }: { node: GraphNode; mode: Mode; onAdd(n: GraphNode): void; onAddExpand?(n: GraphNode): void }) {
  return (
    <li
      className="node-item"
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData(NODE_MIME, JSON.stringify(node));
        e.dataTransfer.effectAllowed = "copy";
      }}
      title="Drag onto the canvas, or use the buttons"
    >
      <ShapeIcon type={node.type} mode={mode} />
      <span className="node-item-text">
        <span className="node-item-label">{node.label}</span>
        <span className="muted small">{typeInfo(node.type).label}</span>
      </span>
      <button className="icon-btn" onClick={() => onAdd(node)} aria-label={`Add ${node.label}`} title="Add to canvas">+</button>
      {onAddExpand && (
        <button className="icon-btn" onClick={() => onAddExpand(node)} aria-label={`Add ${node.label} with neighbours`} title="Add with neighbours">⤢</button>
      )}
    </li>
  );
}

export function SearchTab({ mode, meta, onAdd, onAddExpand }: Props) {
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [results, setResults] = useState<GraphNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!q.trim()) {
      setResults([]);
      return;
    }
    const handle = window.setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        setResults(await api.search(q, type ? [type] : [], 40));
      } catch (e) {
        setError(String((e as Error).message));
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => window.clearTimeout(handle);
  }, [q, type]);

  const types = (meta?.node_types ?? []).map((t) => t.type).filter((t, i, a) => a.indexOf(t) === i);

  return (
    <div className="tab-body">
      <label className="field">
        <span>Find a node</span>
        <input autoFocus type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Agent, tool, Jira, Healthcare…" />
      </label>
      <label className="field">
        <span>Type</span>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">All types</option>
          {types.map((t) => (
            <option key={t} value={t}>{NODE_TYPES[t]?.label ?? t}</option>
          ))}
        </select>
      </label>
      <p className="hint">Drag a result onto the canvas to place it where you want. It connects to what is already there.</p>
      {loading && <p className="muted">Searching…</p>}
      {error && <p className="error">{error}</p>}
      {!loading && q.trim() && results.length === 0 && !error && <p className="muted">No matches.</p>}
      <ul className="node-list">
        {results.map((n) => (
          <NodeListItem key={n.id} node={n} mode={mode} onAdd={onAdd} onAddExpand={onAddExpand} />
        ))}
      </ul>
    </div>
  );
}
