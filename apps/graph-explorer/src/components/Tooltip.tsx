import type { HoverInfo } from "./GraphCanvas";
import { edgeInfo, typeInfo } from "../theme";
import type { GraphEdge, GraphNode } from "../types";

const fmt = (v: number | null | undefined, digits = 3) => (v === null || v === undefined ? "–" : Number(v).toFixed(digits));

export function Tooltip({ info }: { info: HoverInfo | null }) {
  if (!info) return null;
  const style = { left: info.x + 14, top: info.y + 14 };
  if (info.kind === "node") {
    const n = info.data as GraphNode;
    return (
      <div className="tooltip" style={style} role="tooltip">
        <div className="tooltip-title">{n.label}</div>
        <div className="muted">{typeInfo(n.type).label}</div>
        {n.pagerank !== undefined && n.pagerank !== null && <div>Importance (PageRank) <b>{fmt(n.pagerank)}</b></div>}
        {n.degree !== undefined && n.degree !== null && <div>Connections <b>{n.degree}</b></div>}
        {n.run_count !== undefined && n.run_count !== null && <div>Runs <b>{n.run_count}</b></div>}
      </div>
    );
  }
  const e = info.data as GraphEdge;
  return (
    <div className="tooltip" style={style} role="tooltip">
      <div className="tooltip-title">{edgeInfo(e.type).label}</div>
      {e.type === "SUMMARY" && <div><b>{e.weight}</b> artifacts carry both</div>}
      {e.type === "CO_OCCURS" && <div>Used together in <b>{e.weight}</b> agents</div>}
      {e.type === "CALLS" && <div><b>{e.weight}</b> calls</div>}
      {typeof e.properties?.matched_keyword === "string" && <div className="muted">matched “{e.properties.matched_keyword}”</div>}
      {e.origin.startsWith("LABEL") && <div className="muted">{e.origin === "LABEL_MANUAL" ? "steward mapping" : "keyword label"}</div>}
    </div>
  );
}
