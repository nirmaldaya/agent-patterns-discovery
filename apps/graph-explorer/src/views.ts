import type { Snapshot } from "./components/GraphCanvas";

export interface SavedView {
  name: string;
  savedAt: string;
  snapshot: Snapshot;
}

const KEY = "apdi.graph-explorer.views";

export function loadViews(): SavedView[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as SavedView[]) : [];
  } catch {
    return [];
  }
}

export function storeViews(views: SavedView[]): boolean {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(views));
    return true;
  } catch {
    return false;
  }
}

export function download(filename: string, href: string) {
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export function downloadJson(filename: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  download(filename, url);
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
