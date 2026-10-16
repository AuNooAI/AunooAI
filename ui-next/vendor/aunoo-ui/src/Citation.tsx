import './Citation.css';

export interface CitationProps {
  /** Reference number shown in the chip. */
  n: number;
  /** Source URL (opens in a new tab). Without it the chip is plain text. */
  href?: string;
  /** Source title, for the accessible name and tooltip. */
  title?: string;
  className?: string;
}

/** Inline source reference, e.g. "…for AI content [3]". */
export function Citation({ n, href, title, className }: CitationProps) {
  const name = title ? `Source ${n}: ${title}` : `Source ${n}`;
  const classes = ['citation', className].filter(Boolean).join(' ');
  return href ? (
    <a className={classes} href={href} target="_blank" rel="noreferrer" aria-label={`${name} (opens in new tab)`} title={title}>
      {n}
    </a>
  ) : (
    <span className={classes} title={title}>
      <span aria-hidden="true">{n}</span>
      <span className="visually-hidden">{name}</span>
    </span>
  );
}
