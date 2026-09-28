import { useRef, useState } from "react";
import type { SavedView } from "../views";

interface Props {
  views: SavedView[];
  canSave: boolean;
  onSave(name: string): void;
  onLoad(view: SavedView): void;
  onDelete(name: string): void;
  onExport(): void;
  onImport(file: File): void;
}

export function ViewsTab({ views, canSave, onSave, onLoad, onDelete, onExport, onImport }: Props) {
  const [name, setName] = useState("");
  const file = useRef<HTMLInputElement>(null);
  return (
    <div className="tab-body">
      <p className="hint">Save the graph you built (nodes, positions and pins) and come back to it later. Views are kept in this browser; export to share one.</p>
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) {
            onSave(name.trim());
            setName("");
          }
        }}
      >
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="View name" aria-label="View name" />
        <button className="primary" type="submit" disabled={!canSave || !name.trim()}>Save</button>
      </form>
      {views.length === 0 && <p className="muted">No saved views yet.</p>}
      <ul className="view-list">
        {views.map((v) => (
          <li key={v.name}>
            <button className="pattern" onClick={() => onLoad(v)}>
              <span className="pattern-name">{v.name}</span>
              <span className="muted small">{v.snapshot.nodes.length} nodes · {new Date(v.savedAt).toLocaleString()}</span>
            </button>
            <button className="icon-btn" onClick={() => onDelete(v.name)} aria-label={`Delete ${v.name}`} title="Delete">×</button>
          </li>
        ))}
      </ul>
      <div className="row gap">
        <button onClick={onExport} disabled={!canSave}>Export JSON</button>
        <button onClick={() => file.current?.click()}>Import JSON</button>
        <input
          ref={file}
          type="file"
          accept="application/json,.json"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onImport(f);
            e.target.value = "";
          }}
        />
      </div>
    </div>
  );
}
