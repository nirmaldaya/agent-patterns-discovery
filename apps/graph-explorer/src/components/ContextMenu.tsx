export interface MenuAction {
  label: string;
  shortcut?: string;
  onClick(): void;
  disabled?: boolean;
}

export function ContextMenu({ x, y, title, actions, onClose }: { x: number; y: number; title?: string; actions: MenuAction[]; onClose(): void }) {
  return (
    <>
      <div className="menu-backdrop" onClick={onClose} onContextMenu={(e) => { e.preventDefault(); onClose(); }} />
      <div className="context-menu" style={{ left: x, top: y }} role="menu">
        {title && <div className="menu-title">{title}</div>}
        {actions.map((a) => (
          <button
            key={a.label}
            role="menuitem"
            disabled={a.disabled}
            onClick={() => {
              onClose();
              a.onClick();
            }}
          >
            <span>{a.label}</span>
            {a.shortcut && <kbd>{a.shortcut}</kbd>}
          </button>
        ))}
      </div>
    </>
  );
}
