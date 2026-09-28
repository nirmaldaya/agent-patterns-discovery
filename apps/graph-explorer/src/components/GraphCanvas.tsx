import cytoscape, { type Core, type ElementDefinition, type NodeSingular } from "cytoscape";
import fcose from "cytoscape-fcose";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { CHROME, buildStylesheet, type StyleOptions } from "../theme";
import type { GraphEdge, GraphNode } from "../types";

cytoscape.use(fcose);

export const NODE_MIME = "application/x-apdi-node";

export type LayoutName = "fcose" | "concentric" | "breadthfirst" | "circle" | "grid";

export interface AddOptions {
  /** Place new nodes in a ring around these existing nodes (expand). */
  anchorIds?: string[];
  /** Place new nodes here, in model coordinates (drag and drop). */
  position?: { x: number; y: number };
  /** Run a full layout afterwards (overview, community and co-occurrence loads). */
  fullLayout?: boolean;
}

export interface Snapshot {
  nodes: { data: GraphNode; position: { x: number; y: number }; pinned: boolean }[];
  edges: GraphEdge[];
}

export interface CanvasStats {
  nodes: number;
  edges: number;
  byType: Record<string, number>;
  byEdgeType: Record<string, number>;
}

export interface HoverInfo {
  kind: "node" | "edge";
  data: GraphNode | GraphEdge;
  x: number;
  y: number;
}

export interface CanvasHandle {
  addGraph(nodes: GraphNode[], edges: GraphEdge[], opts?: AddOptions): string[];
  removeNodes(ids: string[]): void;
  keepOnly(ids: string[]): void;
  clear(): void;
  nodeIds(): string[];
  selectedIds(): string[];
  select(ids: string[], focus?: boolean): void;
  selectNeighbours(): void;
  togglePin(ids: string[]): void;
  runLayout(name: LayoutName, randomize?: boolean): void;
  fit(): void;
  png(): string;
  snapshot(): Snapshot;
  restore(s: Snapshot): void;
  elements(): { nodes: GraphNode[]; edges: GraphEdge[] };
}

interface Props {
  style: StyleOptions;
  hiddenTypes: Set<string>;
  hiddenEdgeTypes: Set<string>;
  minWeight: number;
  highlightNeighbours: boolean;
  groupByCommunity: boolean;
  communityNames: Map<number, string>;
  onSelect(ids: string[]): void;
  onExpand(id: string): void;
  onContext(id: string | null, x: number, y: number): void;
  onHover(info: HoverInfo | null): void;
  onDropNode(node: GraphNode, position: { x: number; y: number }): void;
  onChange(stats: CanvasStats): void;
}

const WEIGHTED_ORIGINS = new Set(["RUNTIME", "DERIVED", "SUMMARY"]);
const REAL_NODES = "node[!isGroup]";

function nodeDef(n: GraphNode, position?: { x: number; y: number }): ElementDefinition {
  return { group: "nodes", data: { ...n }, position: position ? { ...position } : undefined };
}

function edgeDef(e: GraphEdge): ElementDefinition {
  return { group: "edges", data: { ...e } };
}

function ring(center: { x: number; y: number }, count: number, index: number, offset: number) {
  const radius = 120 + Math.max(0, count - 8) * 9;
  const angle = offset + (2 * Math.PI * index) / Math.max(count, 1);
  return { x: center.x + radius * Math.cos(angle), y: center.y + radius * Math.sin(angle) };
}

export const GraphCanvas = forwardRef<CanvasHandle, Props>(function GraphCanvas(props, ref) {
  const container = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const propsRef = useRef(props);
  propsRef.current = props;

  const cy = () => cyRef.current!;

  const emitStats = () => {
    const c = cy();
    const byType: Record<string, number> = {};
    const byEdgeType: Record<string, number> = {};
    c.nodes(REAL_NODES).forEach((n) => {
      byType[n.data("type")] = (byType[n.data("type")] ?? 0) + 1;
    });
    c.edges().forEach((e) => {
      byEdgeType[e.data("type")] = (byEdgeType[e.data("type")] ?? 0) + 1;
    });
    propsRef.current.onChange({ nodes: c.nodes(REAL_NODES).length, edges: c.edges().length, byType, byEdgeType });
  };

  const applyFilters = () => {
    const { hiddenTypes, hiddenEdgeTypes, minWeight } = propsRef.current;
    const c = cy();
    c.batch(() => {
      c.elements().removeClass("hidden");
      c.nodes(REAL_NODES).forEach((n) => {
        if (hiddenTypes.has(n.data("type"))) n.addClass("hidden");
      });
      c.edges().forEach((e) => {
        const weighted = WEIGHTED_ORIGINS.has(e.data("origin"));
        if (hiddenEdgeTypes.has(e.data("type")) || (weighted && (Number(e.data("weight")) || 0) < minWeight)) {
          e.addClass("hidden");
        }
      });
      // A community box with no visible member is hidden too.
      c.nodes("[?isGroup]").forEach((g) => {
        if (g.children().not(".hidden").empty()) g.addClass("hidden");
      });
    });
  };

  const applyHighlight = () => {
    const c = cy();
    c.batch(() => {
      c.elements().removeClass("faded highlight");
      const selected = c.nodes(`${REAL_NODES}:selected`);
      if (!propsRef.current.highlightNeighbours || selected.empty()) return;
      const keep = selected.closedNeighborhood();
      c.elements().not(keep).not("[?isGroup]").addClass("faded");
      keep.edges().addClass("highlight");
    });
  };

  const regroup = () => {
    const { groupByCommunity, communityNames } = propsRef.current;
    const c = cy();
    c.batch(() => {
      c.nodes(REAL_NODES).forEach((n) => {
        if (n.parent().nonempty()) n.move({ parent: null });
      });
      c.nodes("[?isGroup]").remove();
      if (!groupByCommunity) return;
      const members = new Map<number, string[]>();
      c.nodes(REAL_NODES).forEach((n) => {
        const community = n.data("community_id");
        if (community === null || community === undefined) return;
        members.set(community, [...(members.get(community) ?? []), n.id()]);
      });
      members.forEach((ids, community) => {
        if (ids.length < 2) return;
        const groupId = `group:${community}`;
        c.add({ group: "nodes", data: { id: groupId, isGroup: true, label: communityNames.get(community) ?? `Pattern ${community}` } });
        ids.forEach((id) => c.getElementById(id).move({ parent: groupId }));
      });
    });
    applyFilters();
  };

  /** Fit to the given elements without zooming in further than a comfortable reading size. */
  const fitCapped = (eles?: cytoscape.CollectionReturnValue, maxZoom = 1.25) => {
    const c = cy();
    const target = eles ?? c.elements().not(".hidden");
    if (target.empty()) return;
    c.fit(target, 40);
    if (c.zoom() > maxZoom) {
      c.zoom(maxZoom);
      c.center(target);
    }
  };

  /** Settle newly added nodes around their ring positions while everything already placed stays exactly where it is. */
  const tidy = (freshIds: Set<string>) => {
    const c = cy();
    const visible = c.elements().not(".hidden");
    const fixed = c
      .nodes(REAL_NODES)
      .filter((n) => !n.hasClass("hidden") && !freshIds.has(n.id()))
      .map((n) => ({ nodeId: n.id(), position: { ...(n as cytoscape.NodeSingular).position() } }));
    const bringIntoView = () => {
      const ext = c.extent();
      const outside = [...freshIds].some((id) => {
        const pos = (c.getElementById(id) as cytoscape.NodeSingular).position();
        return pos.x < ext.x1 || pos.x > ext.x2 || pos.y < ext.y1 || pos.y > ext.y2;
      });
      if (outside) fitCapped();
    };
    if (propsRef.current.groupByCommunity || fixed.length === 0) {
      bringIntoView();
      return;
    }
    visible
      .layout({
        name: "fcose", quality: "default", randomize: false, fixedNodeConstraint: fixed, nodeRepulsion: 7000,
        idealEdgeLength: 95, nodeSeparation: 90, nodeDimensionsIncludeLabels: true, animate: true,
        animationDuration: 350, fit: false, stop: bringIntoView,
      } as unknown as cytoscape.LayoutOptions)
      .run();
  };

  const runLayout = (name: LayoutName, randomize = false) => {
    const c = cy();
    const eles = c.elements().not(".hidden");
    if (eles.empty()) return;
    const common = { animate: true, animationDuration: 450, fit: false, stop: () => fitCapped() };
    const options: Record<string, unknown> =
      name === "fcose"
        ? {
            name: "fcose", quality: "default", randomize, nodeRepulsion: 7000, idealEdgeLength: 95,
            nodeSeparation: 90, packComponents: true, nodeDimensionsIncludeLabels: true,
            fixedNodeConstraint: c.nodes(".pinned").map((n) => ({ nodeId: n.id(), position: { ...n.position() } })),
            ...common,
          }
        : name === "concentric"
          ? { name, concentric: (n: NodeSingular) => n.degree(false), levelWidth: () => 2, minNodeSpacing: 30, ...common }
          : name === "breadthfirst"
            ? { name, directed: true, spacingFactor: 1.15, roots: c.nodes(`${REAL_NODES}:selected`), ...common }
            : { name, avoidOverlap: true, ...common };
    eles.layout(options as unknown as cytoscape.LayoutOptions).run();
  };

  useEffect(() => {
    const c = cytoscape({
      container: container.current!,
      style: buildStylesheet(propsRef.current.style),
      boxSelectionEnabled: true,
      minZoom: 0.08,
      maxZoom: 3,
    });
    cyRef.current = c;

    let selectTimer: number | undefined;
    c.on("select unselect", () => {
      window.clearTimeout(selectTimer);
      selectTimer = window.setTimeout(() => {
        propsRef.current.onSelect(c.nodes(`${REAL_NODES}:selected`).map((n) => n.id()));
        applyHighlight();
      }, 30);
    });
    c.on("dbltap", REAL_NODES, (evt) => propsRef.current.onExpand(evt.target.id()));
    c.on("cxttap", (evt) => {
      const p = evt.renderedPosition ?? { x: 0, y: 0 };
      const target = evt.target;
      const isNode = target !== c && target.isNode?.() && !target.data("isGroup");
      if (isNode && !target.selected()) {
        c.elements().unselect();
        target.select();
      }
      propsRef.current.onContext(isNode ? target.id() : null, p.x, p.y);
    });
    c.on("tap", (evt) => {
      if (evt.target === c) propsRef.current.onContext(null, -1, -1);
    });
    c.on("mouseover", "node, edge", (evt) => {
      const t = evt.target;
      if (t.data("isGroup")) return;
      const p = t.isNode() ? t.renderedPosition() : t.renderedMidpoint();
      propsRef.current.onHover({ kind: t.isNode() ? "node" : "edge", data: t.data(), x: p.x, y: p.y });
    });
    c.on("mouseout", "node, edge", () => propsRef.current.onHover(null));
    c.on("drag pan zoom", () => propsRef.current.onHover(null));

    return () => {
      window.clearTimeout(selectTimer);
      c.destroy();
      cyRef.current = null;
    };
  }, []);

  useEffect(() => {
    cyRef.current?.style(buildStylesheet(props.style));
  }, [props.style]);

  useEffect(applyFilters, [props.hiddenTypes, props.hiddenEdgeTypes, props.minWeight]);
  useEffect(applyHighlight, [props.highlightNeighbours]);
  useEffect(regroup, [props.groupByCommunity, props.communityNames]);

  useImperativeHandle(ref, () => ({
    addGraph(nodes, edges, opts = {}) {
      const c = cy();
      const wasEmpty = c.nodes(REAL_NODES).empty();
      const fresh = nodes.filter((n) => c.getElementById(n.id).empty());
      const freshIds = new Set(fresh.map((n) => n.id));
      const positions = new Map<string, { x: number; y: number }>();

      if (opts.position) {
        fresh.forEach((n, i) => positions.set(n.id, i === 0 ? opts.position! : ring(opts.position!, fresh.length - 1, i - 1, 0)));
      } else if (!wasEmpty && !opts.fullLayout) {
        // Put each new node next to the anchor it is linked to, so the user's arrangement is preserved.
        const anchors = (opts.anchorIds ?? []).filter((id) => c.getElementById(id).nonempty());
        const byAnchor = new Map<string, GraphNode[]>();
        const extent = c.extent();
        const fallback = { x: (extent.x1 + extent.x2) / 2, y: (extent.y1 + extent.y2) / 2 };
        for (const n of fresh) {
          const link = edges.find(
            (e) => (e.source === n.id && anchors.includes(e.target)) || (e.target === n.id && anchors.includes(e.source)),
          );
          const anchor = link ? (link.source === n.id ? link.target : link.source) : anchors[0] ?? "";
          byAnchor.set(anchor, [...(byAnchor.get(anchor) ?? []), n]);
        }
        byAnchor.forEach((group, anchor) => {
          const center = anchor ? c.getElementById(anchor).position() : fallback;
          const offset = Math.random() * Math.PI;
          group.forEach((n, i) => positions.set(n.id, ring(center, group.length, i, offset)));
        });
      }

      c.batch(() => {
        c.add(fresh.map((n) => nodeDef(n, positions.get(n.id))));
        const addable = edges.filter(
          (e) => c.getElementById(e.id).empty() && c.getElementById(e.source).nonempty() && c.getElementById(e.target).nonempty(),
        );
        c.add(addable.map(edgeDef));
      });

      if (propsRef.current.groupByCommunity) regroup();
      else applyFilters();
      applyHighlight();
      if (opts.position) {
        if (fresh.length === 1) c.getElementById(fresh[0].id).flashClass("seed-flash", 900);
        if (wasEmpty) fitCapped();
      } else if (wasEmpty || opts.fullLayout) {
        runLayout("fcose", true);
      } else if (fresh.length) {
        tidy(freshIds);
      }
      emitStats();
      return [...freshIds];
    },
    removeNodes(ids) {
      const c = cy();
      c.batch(() => ids.forEach((id) => c.getElementById(id).remove()));
      regroup();
      emitStats();
    },
    keepOnly(ids) {
      const c = cy();
      const keep = new Set(ids);
      c.batch(() => c.nodes(REAL_NODES).filter((n) => !keep.has(n.id())).remove());
      regroup();
      emitStats();
    },
    clear() {
      cy().elements().remove();
      emitStats();
      propsRef.current.onSelect([]);
    },
    nodeIds: () => cy().nodes(REAL_NODES).map((n) => n.id()),
    selectedIds: () => cy().nodes(`${REAL_NODES}:selected`).map((n) => n.id()),
    select(ids, focus = false) {
      const c = cy();
      c.elements().unselect();
      const eles = c.collection();
      ids.forEach((id) => eles.merge(c.getElementById(id)));
      eles.select();
      if (focus && eles.nonempty()) c.animate({ center: { eles }, zoom: Math.max(c.zoom(), 1) }, { duration: 350 });
    },
    selectNeighbours() {
      const c = cy();
      c.nodes(`${REAL_NODES}:selected`).neighborhood(REAL_NODES).select();
    },
    togglePin(ids) {
      const c = cy();
      ids.forEach((id) => {
        const n = c.getElementById(id);
        if (n.hasClass("pinned")) n.removeClass("pinned").unlock();
        else n.addClass("pinned").lock();
      });
    },
    runLayout,
    fit: () => fitCapped(undefined, 2),
    png: () => cy().png({ full: true, scale: 2, bg: CHROME[propsRef.current.style.mode].surface }),
    snapshot() {
      const c = cy();
      return {
        nodes: c.nodes(REAL_NODES).map((n) => ({ data: n.data() as GraphNode, position: { ...n.position() }, pinned: n.hasClass("pinned") })),
        edges: c.edges().map((e) => e.data() as GraphEdge),
      };
    },
    restore(s) {
      const c = cy();
      c.batch(() => {
        c.elements().remove();
        c.add(s.nodes.map((n) => nodeDef(n.data, n.position)));
        c.add(s.edges.filter((e) => c.getElementById(e.source).nonempty() && c.getElementById(e.target).nonempty()).map(edgeDef));
        s.nodes.filter((n) => n.pinned).forEach((n) => c.getElementById(n.data.id).addClass("pinned").lock());
      });
      regroup();
      applyHighlight();
      fitCapped();
      emitStats();
      propsRef.current.onSelect([]);
    },
    elements() {
      const c = cy();
      return {
        nodes: c.nodes(REAL_NODES).map((n) => n.data() as GraphNode),
        edges: c.edges().map((e) => e.data() as GraphEdge),
      };
    },
  }));

  const onDragOver = (e: React.DragEvent) => {
    if (e.dataTransfer.types.includes(NODE_MIME)) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    }
  };

  const onDrop = (e: React.DragEvent) => {
    const raw = e.dataTransfer.getData(NODE_MIME);
    if (!raw) return;
    e.preventDefault();
    const rect = container.current!.getBoundingClientRect();
    const c = cy();
    const pan = c.pan();
    const zoom = c.zoom();
    const position = { x: (e.clientX - rect.left - pan.x) / zoom, y: (e.clientY - rect.top - pan.y) / zoom };
    propsRef.current.onDropNode(JSON.parse(raw) as GraphNode, position);
  };

  return (
    <div
      ref={container}
      className="graph-canvas"
      onDragOver={onDragOver}
      onDrop={onDrop}
      onContextMenu={(e) => e.preventDefault()}
      role="application"
      aria-label="Graph canvas. Drag nodes to arrange them, double-click a node to expand it, right-click for actions."
    />
  );
});
