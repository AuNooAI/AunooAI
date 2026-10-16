import './AreaPanel.css';

export interface AreaPanelProps {
  /** Target for the skip link. */
  id?: string;
  /** default = centred 940px column · wide = full width of the panel (dashboards) */
  width?: 'default' | 'wide';
  className?: string;
  children?: React.ReactNode;
}

/**
 * The light, rounded content panel inside the dark chrome (§4.1), with a centred page column.
 * Renders `<main>` — one per page.
 */
export function AreaPanel({ id = 'main', width = 'default', className, children }: AreaPanelProps) {
  return (
    <main id={id} tabIndex={-1} className={['area-panel', width === 'wide' && 'area-panel--wide', className].filter(Boolean).join(' ')}>
      <div className="area-panel__page">{children}</div>
    </main>
  );
}
