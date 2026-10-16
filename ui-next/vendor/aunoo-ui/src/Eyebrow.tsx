import './Eyebrow.css';

export interface EyebrowProps {
  /** Element to render. Use a heading (`h3`) when it titles a section. */
  as?: 'p' | 'span' | 'h2' | 'h3' | 'h4' | 'div' | 'label';
  id?: string;
  className?: string;
  children: React.ReactNode;
}

/** Small uppercase section label ("Current plan", "Tools your agent can call"). No outer margin — the parent sets spacing. */
export function Eyebrow({ as: Comp = 'p', id, className, children }: EyebrowProps) {
  return (
    <Comp id={id} className={['eyebrow', className].filter(Boolean).join(' ')}>
      {children}
    </Comp>
  );
}
