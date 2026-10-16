import { useId } from 'react';
import './Panel.css';

export interface PanelProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  /** Right side of the header, e.g. a count, `<StatusPill>` or `<Button asChild>` link. */
  headerAside?: React.ReactNode;
  /** Heading level for the title (default h2 — pages have one h1). */
  headingLevel?: 2 | 3 | 4;
  className?: string;
  children?: React.ReactNode;
}

/**
 * Translucent white section inside the area panel. Headed by a title and optional description,
 * with an optional element on the right (count, pill, link button).
 */
export function Panel({ title, description, headerAside, headingLevel = 2, className, children }: PanelProps) {
  const titleId = useId();
  const Heading = `h${headingLevel}` as React.ElementType;
  return (
    <section className={['panel', className].filter(Boolean).join(' ')} aria-labelledby={titleId}>
      <div className="panel__head">
        <div className="panel__heading">
          <Heading id={titleId} className="panel__title">{title}</Heading>
          {description && <p className="panel__description">{description}</p>}
        </div>
        {headerAside && <div className="panel__aside">{headerAside}</div>}
      </div>
      {children && <div className="panel__body">{children}</div>}
    </section>
  );
}

export interface PanelSectionProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  headingLevel?: 3 | 4 | 5;
  className?: string;
  children?: React.ReactNode;
}

/** Titled sub-section inside a Panel, e.g. "Header auth — ChatGPT Custom GPTs and scripts". */
export function PanelSection({ title, description, headingLevel = 3, className, children }: PanelSectionProps) {
  const Heading = `h${headingLevel}` as React.ElementType;
  return (
    <div className={['panel-section', className].filter(Boolean).join(' ')}>
      <Heading className="panel-section__title">{title}</Heading>
      {description && <p className="panel__description">{description}</p>}
      {children && <div className="panel__body">{children}</div>}
    </div>
  );
}

/** Hairline between sections of one Panel. */
export function PanelDivider() {
  return <hr className="panel-divider" />;
}
