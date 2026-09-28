import type cytoscape from "cytoscape";

/*
 * Colour carries the node *category* (4 values); shape carries the node *type* within it.
 * A graph shows every colour pair side by side, so only the first three slots of the reference palette are used:
 * they pass the all-pairs colour-vision checks in both modes. Organisation nodes are neutral grey.
 * Aqua is below 3:1 on the light surface, so labels stay visible and a table view exists (relief rule).
 */
export type Mode = "light" | "dark";

export interface Chrome {
  surface: string;
  page: string;
  panel: string;
  ink: string;
  ink2: string;
  muted: string;
  grid: string;
  axis: string;
  border: string;
  neutral: string;
  accent: string;
}

export const CHROME: Record<Mode, Chrome> = {
  light: {
    surface: "#fcfcfb", page: "#f9f9f7", panel: "#ffffff", ink: "#0b0b0b", ink2: "#52514e", muted: "#898781",
    grid: "#e1e0d9", axis: "#c3c2b7", border: "rgba(11,11,11,0.10)", neutral: "#898781", accent: "#2a78d6",
  },
  dark: {
    surface: "#1a1a19", page: "#0d0d0d", panel: "#141413", ink: "#ffffff", ink2: "#c3c2b7", muted: "#898781",
    grid: "#2c2c2a", axis: "#383835", border: "rgba(255,255,255,0.10)", neutral: "#898781", accent: "#3987e5",
  },
};

export type CategoryKey = "built" | "component" | "classification" | "org";

export const CATEGORIES: { key: CategoryKey; label: string; hint: string; color: Record<Mode, string> }[] = [
  { key: "built", label: "Built", hint: "Agents, workflows, processes", color: { light: "#2a78d6", dark: "#3987e5" } },
  { key: "classification", label: "Classification", hint: "Industry, SDLC phase, tech, function, archetype",
    color: { light: "#eb6834", dark: "#d95926" } },
  { key: "component", label: "Components", hint: "Tools, MCP, knowledge bases, guardrails, models",
    color: { light: "#1baf7a", dark: "#199e70" } },
  { key: "org", label: "Organisation", hint: "Customer, organisation, business unit, project, team",
    color: { light: "#898781", dark: "#898781" } },
];

export interface NodeTypeInfo {
  label: string;
  category: CategoryKey;
  shape: cytoscape.Css.NodeShape;
}

export const NODE_TYPES: Record<string, NodeTypeInfo> = {
  AGENT: { label: "Agent", category: "built", shape: "ellipse" },
  WORKFLOW: { label: "Workflow", category: "built", shape: "round-rectangle" },
  PROCESS: { label: "Process", category: "built", shape: "cut-rectangle" },
  TOOL: { label: "Tool", category: "component", shape: "diamond" },
  MCP_TOOL: { label: "MCP tool", category: "component", shape: "round-diamond" },
  MCP_SERVER: { label: "MCP server", category: "component", shape: "round-hexagon" },
  KNOWLEDGE_BASE: { label: "Knowledge base", category: "component", shape: "barrel" },
  GUARDRAIL: { label: "Guardrail", category: "component", shape: "octagon" },
  MODEL: { label: "Model", category: "component", shape: "star" },
  INDUSTRY: { label: "Industry", category: "classification", shape: "round-tag" },
  SDLC_PHASE: { label: "SDLC phase", category: "classification", shape: "round-pentagon" },
  TECH: { label: "Technology", category: "classification", shape: "rhomboid" },
  BUSINESS_FUNCTION: { label: "Business function", category: "classification", shape: "tag" },
  ARCHETYPE: { label: "Archetype", category: "classification", shape: "round-triangle" },
  DEPLOYMENT: { label: "Customer", category: "org", shape: "round-octagon" },
  ORGANIZATION: { label: "Organisation", category: "org", shape: "rectangle" },
  BUSINESS_UNIT: { label: "Business unit", category: "org", shape: "round-rectangle" },
  PROJECT: { label: "Project", category: "org", shape: "bottom-round-rectangle" },
  TEAM: { label: "Team", category: "org", shape: "ellipse" },
};

export const typeInfo = (type: string): NodeTypeInfo =>
  NODE_TYPES[type] ?? { label: type, category: "org", shape: "ellipse" };

export const categoryColor = (category: CategoryKey, mode: Mode) =>
  CATEGORIES.find((c) => c.key === category)!.color[mode];

export const nodeColor = (type: string, mode: Mode) => categoryColor(typeInfo(type).category, mode);

export interface EdgeTypeInfo {
  label: string;
  style: "solid" | "dashed" | "dotted";
  directed: boolean;
}

export const EDGE_TYPES: Record<string, EdgeTypeInfo> = {
  CONTAINS: { label: "contains", style: "solid", directed: true },
  USES_TOOL: { label: "uses tool", style: "solid", directed: true },
  USES_KNOWLEDGE_BASE: { label: "uses KB", style: "solid", directed: true },
  HAS_GUARDRAIL: { label: "has guardrail", style: "solid", directed: true },
  USES_MODEL: { label: "uses model", style: "solid", directed: true },
  EXPOSES: { label: "exposes", style: "solid", directed: true },
  INCLUDES: { label: "includes", style: "solid", directed: true },
  CALLS: { label: "calls", style: "dashed", directed: true },
  OWNED_BY: { label: "owned by", style: "solid", directed: true },
  PART_OF: { label: "part of", style: "solid", directed: true },
  IN_INDUSTRY: { label: "in industry", style: "dotted", directed: true },
  SUPPORTS_PHASE: { label: "supports phase", style: "dotted", directed: true },
  USES_TECH: { label: "uses tech", style: "dotted", directed: true },
  SERVES_FUNCTION: { label: "serves function", style: "dotted", directed: true },
  HAS_ARCHETYPE: { label: "is a", style: "dotted", directed: true },
  CLONED_FROM: { label: "cloned from", style: "dashed", directed: true },
  CO_OCCURS: { label: "used together", style: "solid", directed: false },
  SUMMARY: { label: "artifacts in both", style: "solid", directed: false },
};

export const edgeInfo = (type: string): EdgeTypeInfo =>
  EDGE_TYPES[type] ?? { label: type.toLowerCase().replace(/_/g, " "), style: "solid", directed: true };

export type SizeMode = "pagerank" | "degree" | "uniform";

export interface StyleOptions {
  mode: Mode;
  sizeMode: SizeMode;
  showEdgeLabels: boolean;
  maxPagerank: number;
  maxDegree: number;
}

const truncate = (s: string, n = 28) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

export function nodeSize(data: { pagerank?: number | null; degree?: number | null }, o: StyleOptions): number {
  if (o.sizeMode === "uniform") return 30;
  const value = o.sizeMode === "pagerank" ? data.pagerank ?? 0 : data.degree ?? 0;
  const max = o.sizeMode === "pagerank" ? o.maxPagerank : o.maxDegree;
  if (!max || max <= 0) return 30;
  return 22 + 42 * Math.sqrt(Math.min(1, Math.max(0, value / max)));
}

export function buildStylesheet(o: StyleOptions): cytoscape.StylesheetJson {
  const c = CHROME[o.mode];
  return [
    {
      selector: "node",
      style: {
        "background-color": (n: cytoscape.NodeSingular) => nodeColor(n.data("type"), o.mode),
        shape: (n: cytoscape.NodeSingular) => typeInfo(n.data("type")).shape,
        width: (n: cytoscape.NodeSingular) => nodeSize(n.data(), o),
        height: (n: cytoscape.NodeSingular) => nodeSize(n.data(), o),
        label: (n: cytoscape.NodeSingular) => truncate(String(n.data("label") ?? "")),
        color: c.ink,
        "font-size": 11,
        "font-family": 'system-ui, -apple-system, "Segoe UI", sans-serif',
        "text-valign": "bottom",
        "text-margin-y": 4,
        "text-wrap": "none",
        "text-background-color": c.surface,
        "text-background-opacity": 0.85,
        "text-background-padding": "2px",
        "text-background-shape": "roundrectangle",
        "border-width": 2,
        "border-color": c.surface,
        "overlay-opacity": 0,
      },
    },
    {
      selector: "node:selected",
      style: { "border-width": 3, "border-color": c.ink, "font-weight": "bold" },
    },
    {
      selector: "node.pinned",
      style: { "border-style": "double", "border-width": 4, "border-color": c.ink2 },
    },
    {
      selector: "node.seed-flash",
      style: { "border-color": c.accent, "border-width": 4 },
    },
    {
      selector: "node[?isGroup]",
      style: {
        shape: "round-rectangle",
        "background-color": c.grid,
        "background-opacity": 0.35,
        "border-width": 1,
        "border-color": c.axis,
        "border-style": "dashed",
        label: "data(label)",
        "text-valign": "top",
        "text-halign": "center",
        "font-size": 12,
        "font-weight": "bold",
        color: c.ink2,
        "text-background-opacity": 0,
        padding: "18px",
      },
    },
    {
      selector: "edge",
      style: {
        width: (e: cytoscape.EdgeSingular) => 1.5 + Math.min(3.5, Math.log2(1 + (Number(e.data("weight")) || 1)) - 1),
        "line-color": c.muted,
        "line-opacity": 0.55,
        "line-style": (e: cytoscape.EdgeSingular) => edgeInfo(e.data("type")).style,
        "target-arrow-shape": (e: cytoscape.EdgeSingular) => (edgeInfo(e.data("type")).directed ? "triangle" : "none"),
        "target-arrow-color": c.muted,
        "arrow-scale": 0.8,
        "curve-style": "bezier",
        label: o.showEdgeLabels ? (e: cytoscape.EdgeSingular) => edgeInfo(e.data("type")).label : "",
        "font-size": 9,
        color: c.ink2,
        "text-rotation": "autorotate",
        "text-background-color": c.surface,
        "text-background-opacity": 0.9,
        "text-background-padding": "1px",
        "overlay-opacity": 0,
      },
    },
    {
      selector: "edge:selected",
      style: { "line-color": c.ink, "target-arrow-color": c.ink, width: 3 },
    },
    { selector: ".hidden", style: { display: "none" } },
    { selector: ".faded", style: { opacity: 0.18 } },
    {
      selector: "edge.highlight",
      style: { "line-color": c.ink2, "target-arrow-color": c.ink2, "line-opacity": 0.9 },
    },
  ];
}
