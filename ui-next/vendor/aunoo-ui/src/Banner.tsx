import { useId } from 'react';
import { Icon } from './Icon';
import type { IconName } from './icons';
import './Banner.css';

export interface BannerProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  /** Usually a `<Button>`: primary to start, secondary to end/undo. */
  action?: React.ReactNode;
  /** promo = pink (offers, "why this matters") · info = blue (context) · success = opportunity · warning = risk · error = failed */
  tone?: 'promo' | 'info' | 'success' | 'warning' | 'error';
  /** Decorative icon before the title. */
  icon?: IconName;
  /** Heading level for the title (default h3, inside a Panel). */
  headingLevel?: 2 | 3 | 4;
  className?: string;
}

/** Callout on a tint: title, description, optional action. Promo (pink) or info (blue). */
export function Banner({ title, description, action, tone = 'promo', icon, headingLevel = 3, className }: BannerProps) {
  const titleId = useId();
  const Heading = `h${headingLevel}` as React.ElementType;
  return (
    <section className={['banner', `banner--${tone}`, className].filter(Boolean).join(' ')} aria-labelledby={titleId}>
      <div className="banner__text">
        <Heading id={titleId} className="banner__title">
          {icon && <Icon name={icon} size="sm" />}
          {title}
        </Heading>
        {description && <p className="banner__description">{description}</p>}
      </div>
      {action && <div className="banner__action">{action}</div>}
    </section>
  );
}
