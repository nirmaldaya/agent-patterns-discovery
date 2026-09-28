import { useMemo, useState } from "react";
import { edgeInfo, typeInfo, type Mode } from "../theme";
import type { GraphEdge, GraphNode } from "../types";
import { ShapeIcon } from "./ShapeIcon";

type SortKey = "label" | "type" | "degree" | "pagerank" | "community_id" | "run_count";

export function TableView({ mode, nodes, edges, onFocus }: { mode: Mode; nodes: GraphNode[]; edges: GraphEdge[]; onFocus(id: string): void }) {
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "pagerank", desc: true });
  const labels = useMemo(() => new Map(nodes.map((n) => [n.id, n.label])), [nodes]);
  const sorted = useMemo(() => {
    const v = (n: GraphNode) => (sort.key === "type" ? typeInfo(n.type).label : (n[sort.key] ?? -Infinity));
    return [...nodes].sort((a, b) => {
      const x = v(a), y = v(b);
      const cmp = typeof x === "string" && typeof y === "string" ? x.localeCompare(y) : Number(x) - Number(y);
      return sort.desc ? -cmp : cmp;
    });
  }, [nodes, sort]);

  const th = (key: SortKey, label: string, numeric = false) => (
    <th className={numeric ? "num" : ""} aria-sort={sort.key === key ? (sort.desc ? "descending" : "ascending") : "none"}>
      <button onClick={() => setSort({ key, desc: sort.key === key ? !sort.desc : numeric })}>
        {label}{sort.key === key ? (sort.desc ? " ▾" : " ▴") : ""}
      </button>
    </th>
  );

  if (nodes.length === 0) return <div className="table-view"><p className="muted">The canvas is empty.</p></div>;
  return (
    <div className="table-view">
      <h3>Nodes ({nodes.length})</h3>
      <table>
        <thead>
          <tr>{th("label", "Name")}{th("type", "Type")}{th("pagerank", "Importance", true)}{th("degree", "Connections", true)}{th("run_count", "Runs", true)}{th("community_id", "Pattern", true)}</tr>
        </thead>
        <tbody>
          {sorted.map((n) => (
            <tr key={n.id} onClick={() => onFocus(n.id)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onFocus(n.id)}>
              <td>{n.label}</td>
              <td><ShapeIcon type={n.type} mode={mode} size={11} /> {typeInfo(n.type).label}</td>
              <td className="num">{n.pagerank?.toFixed(3) ?? "–"}</td>
              <td className="num">{n.degree ?? "–"}</td>
              <td className="num">{n.run_count ?? "–"}</td>
              <td className="num">{n.community_id ?? "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>Relationships ({edges.length})</h3>
      <table>
        <thead><tr><th>From</th><th>Relationship</th><th>To</th><th className="num">Weight</th></tr></thead>
        <tbody>
          {edges.map((e) => (
            <tr key={e.id}>
              <td>{labels.get(e.source) ?? e.source}</td>
              <td>{edgeInfo(e.type).label}</td>
              <td>{labels.get(e.target) ?? e.target}</td>
              <td className="num">{e.weight}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
