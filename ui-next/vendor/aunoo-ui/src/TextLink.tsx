import './TextLink.css';

export interface TextLinkProps {
  href: string;
  /** Another site: opens in a new tab and says so to screen readers. */
  external?: boolean;
  className?: string;
  children: React.ReactNode;
}

/** Inline text link in running copy and lists. Underlined so it never relies on colour alone. */
export function TextLink({ href, external = false, className, children }: TextLinkProps) {
  return (
    <a
      className={['text-link', className].filter(Boolean).join(' ')}
      href={href}
      {...(external ? { target: '_blank', rel: 'noreferrer' } : {})}
    >
      {children}
      {external && <span className="visually-hidden"> (opens in new tab)</span>}
    </a>
  );
}
