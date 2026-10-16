import { Icon } from './Icon';
import type { IconName } from './icons';
import './EmptyState.css';

export interface EmptyStateProps {
  /** Decorative icon above the text, e.g. "Notebook". */
  icon?: IconName;
  /** Short heading, e.g. "No briefings yet". */
  title?: React.ReactNode;
  headingLevel?: 3 | 4;
  /** Optional button to get started. */
  action?: React.ReactNode;
  className?: string;
  /** The message (helper text under the title). */
  children: React.ReactNode;
}

/** Centred message on an inset surface for a list with nothing in it yet. */
export function EmptyState({ icon, title, headingLevel = 3, action, className, children }: EmptyStateProps) {
  const Heading = `h${headingLevel}` as React.ElementType;
  return (
    <div className={['empty-state', className].filter(Boolean).join(' ')}>
      {icon && (
        <span className="empty-state__icon">
          <Icon name={icon} size="lg" />
        </span>
      )}
      {title && <Heading className="empty-state__title">{title}</Heading>}
      <p className="empty-state__message">{children}</p>
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  );
}
