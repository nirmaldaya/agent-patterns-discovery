import { useState } from "react";
import { CATEGORIES, NODE_TYPES, edgeInfo, type Mode } from "../theme";
import { ShapeIcon } from "./ShapeIcon";

/** Always-visible key: colour = category, shape = type. Lists only what is on the canvas. */
export function Legend({ mode, byType, byEdgeType }: { mode: Mode; byType: Record<string, number>; byEdgeType: Record<string, number> }) {
  const [open, setOpen] = useState(true);
  const present = Object.keys(byType);
  if (present.length === 0) return null;
  const styles = new Set(Object.keys(byEdgeType).map((t) => edgeInfo(t).style));
  if (!open) {
    return (
      <button className="legend legend-closed" onClick={() => setOpen(true)} aria-expanded="false">
        {CATEGORIES.map((c) => <span key={c.key} className="dot" style={{ background: c.color[mode] }} />)} Legend
      </button>
    );
  }
  return (
    <div className="legend" aria-label="Legend">
      <button className="legend-toggle icon-btn" onClick={() => setOpen(false)} aria-expanded="true" aria-label="Hide legend" title="Hide legend">–</button>
      {CATEGORIES.map((cat) => {
        const types = Object.entries(NODE_TYPES).filter(([t, info]) => info.category === cat.key && present.includes(t));
        if (types.length === 0) return null;
        return (
          <div key={cat.key} className="legend-row">
            <span className="legend-cat">
              <span className="dot" style={{ background: cat.color[mode] }} />
              {cat.label}
            </span>
            {types.map(([t, info]) => (
              <span key={t} className="legend-item">
                <ShapeIcon type={t} mode={mode} size={12} /> {info.label}
              </span>
            ))}
          </div>
        );
      })}
      {styles.size > 1 && (
        <div className="legend-row legend-lines">
          {styles.has("solid") && <span className="legend-item"><i className="line solid" /> design / usage</span>}
          {styles.has("dotted") && <span className="legend-item"><i className="line dotted" /> label</span>}
          {styles.has("dashed") && <span className="legend-item"><i className="line dashed" /> runtime call / clone</span>}
        </div>
      )}
    </div>
  );
}
