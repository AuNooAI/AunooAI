import './StickyHeader.css';

export interface StickyHeaderProps {
  /** Accessible name if it holds controls, e.g. "Brand Watcher controls". */
  label?: string;
  className?: string;
  children?: React.ReactNode;
}

/**
 * Keeps its content (a section header, sub-tabs) pinned to the top of the area panel while the
 * section below scrolls. Sits on the area background so content scrolls under it cleanly.
 */
export function StickyHeader({ label, className, children }: StickyHeaderProps) {
  return (
    <div className={['sticky-header', className].filter(Boolean).join(' ')} role={label ? 'group' : undefined} aria-label={label}>
      {children}
    </div>
  );
}
