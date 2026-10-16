import './StickyFooter.css';

export interface StickyFooterProps {
  /** Accessible name, e.g. "Topic actions". */
  label?: string;
  /** Left side, e.g. an "Unsaved changes" note. */
  status?: React.ReactNode;
  className?: string;
  /** Right side: the form's buttons. */
  children?: React.ReactNode;
}

/**
 * Keeps a long form's actions pinned to the bottom of the area panel while the fields scroll.
 * Sits on the area background with a hairline above, like Dialog's footer.
 */
export function StickyFooter({ label, status, className, children }: StickyFooterProps) {
  return (
    <div className={['sticky-footer', className].filter(Boolean).join(' ')} role={label ? 'group' : undefined} aria-label={label}>
      <div className="sticky-footer__status">{status}</div>
      <div className="sticky-footer__actions">{children}</div>
    </div>
  );
}
