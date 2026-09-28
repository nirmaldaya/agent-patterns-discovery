import { nodeColor, typeInfo, type Mode } from "../theme";

/** Small SVG of a node type's shape in its category colour, used in legends and lists. */
const PATHS: Record<string, string> = {
  ellipse: "M8 1a7 7 0 1 0 0.01 0Z",
  "round-rectangle": "M3 2h10a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z",
  rectangle: "M1.5 2.5h13v11h-13Z",
  "bottom-round-rectangle": "M1.5 2.5h13v8a3 3 0 0 1-3 3h-7a3 3 0 0 1-3-3Z",
  "cut-rectangle": "M4 2h8l3 3v6l-3 3H4l-3-3V5Z",
  diamond: "M8 1l7 7-7 7-7-7Z",
  "round-diamond": "M8 1.5q.7 0 1.2.5l5 5q1 1 0 2l-5 5q-1.2 1-2.4 0l-5-5q-1-1 0-2l5-5q.5-.5 1.2-.5Z",
  "round-hexagon": "M4.5 2h7l3.5 6-3.5 6h-7L1 8Z",
  octagon: "M5 1h6l4 4v6l-4 4H5l-4-4V5Z",
  "round-octagon": "M5 1h6l4 4v6l-4 4H5l-4-4V5Z",
  star: "M8 .8l2.1 4.6 5 .5-3.8 3.3 1.1 4.9L8 11.6l-4.4 2.5 1.1-4.9L.9 5.9l5-.5Z",
  barrel: "M4 1.5h8q3 6.5 0 13H4q-3-6.5 0-13Z",
  "round-tag": "M1.5 3h9l4 5-4 5h-9Z",
  tag: "M1.5 3h9l4 5-4 5h-9Z",
  "round-pentagon": "M8 1l7 5-2.7 8H3.7L1 6Z",
  "round-triangle": "M8 1.5l7 12.5H1Z",
  rhomboid: "M4 2.5h11l-3 11H1Z",
};

export function ShapeIcon({ type, mode, size = 14 }: { type: string; mode: Mode; size?: number }) {
  const info = typeInfo(type);
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" className="shape-icon">
      <path d={PATHS[info.shape] ?? PATHS.ellipse} fill={nodeColor(type, mode)} />
    </svg>
  );
}
