export interface GraphNode {
  id: string;
  type: string;
  group: string;
  label: string;
  deployment?: string | null;
  description?: string | null;
  status?: string | null;
  run_count?: number | null;
  properties?: Record<string, unknown> | null;
  degree?: number | null;
  pagerank?: number | null;
  betweenness?: number | null;
  community_id?: number | null;
  is_isolated?: boolean | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  origin: string;
  weight: number;
  properties?: Record<string, unknown> | null;
}

export interface GraphPayload {
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated?: boolean;
  available?: number;
}

export interface Meta {
  mode: string;
  catalog: string;
  schema: string;
  max_nodes: number;
  node_types: { type: string; group: string; count: number }[];
  edge_types: { type: string; count: number }[];
  deployments: { id: string; label: string }[];
  has_metrics: boolean;
  has_communities: boolean;
  max_pagerank: number | null;
  max_degree: number | null;
}

export interface Relation {
  edge_type: string;
  direction: "in" | "out";
  other_type: string;
  count: number;
}

export interface NodeDetail {
  node: GraphNode;
  relations: Relation[];
  community: { community_id: number; community_name: string; size: number } | null;
}

export interface Community {
  community_id: number;
  community_name: string;
  size: number;
  artifact_count: number;
  top_artifacts: string[];
  top_industries: string[];
  top_sdlc_phases: string[];
  top_tech: string[];
  top_archetypes: string[];
  deployments: string[];
}

export interface Insights {
  hubs: GraphNode[];
  bridges: GraphNode[];
  islands: GraphNode[];
}
