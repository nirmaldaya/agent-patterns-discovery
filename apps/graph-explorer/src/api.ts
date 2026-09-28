import type { Community, GraphEdge, GraphNode, GraphPayload, Insights, Meta, NodeDetail } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* keep status text */
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });
const qs = (params: Record<string, string | number>) =>
  new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();

export const api = {
  meta: () => request<Meta>("/api/meta"),
  search: (q: string, types: string[], limit = 25) =>
    request<GraphNode[]>(`/api/search?${qs({ q, types: types.join(","), limit })}`),
  nodes: (ids: string[]) => post<GraphNode[]>("/api/nodes", { ids }),
  connect: (ids: string[]) => post<GraphEdge[]>("/api/connect", { ids }),
  expand: (body: { ids: string[]; edge_types?: string[]; node_types?: string[]; exclude?: string[]; limit?: number }) =>
    post<GraphPayload>("/api/expand", body),
  node: (id: string) => request<NodeDetail>(`/api/node?${qs({ id })}`),
  overview: (p: { artifact_type: string; src_type: string; dst_type: string; min_count: number }) =>
    request<GraphPayload>(`/api/overview?${qs(p)}`),
  communities: () => request<Community[]>("/api/communities"),
  community: (id: number, limit: number) => request<GraphPayload>(`/api/communities/${id}?${qs({ limit })}`),
  cooccurrence: (kind: string, min_weight: number) =>
    request<GraphPayload>(`/api/cooccurrence?${qs({ kind, min_weight })}`),
  insights: () => request<Insights>("/api/insights"),
};
