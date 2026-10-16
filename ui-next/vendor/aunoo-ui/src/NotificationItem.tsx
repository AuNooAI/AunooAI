import { Icon } from './Icon';
import { IconButton } from './IconButton';
import { StatusDot } from './StatusDot';
import type { IconName } from './icons';
import './NotificationItem.css';

export interface NotificationItemProps {
  /** Phosphor name registered in Icon, shown in a small tile, e.g. "ArrowsClockwise". */
  icon?: IconName;
  title: string;
  description?: React.ReactNode;
  /** Pre-formatted relative time, e.g. "Just now", "5 min ago". */
  timestamp?: string;
  /** Machine-readable ISO time for `<time dateTime>`. */
  dateTime?: string;
  /** Unread: inset surface + accent dot ("Unread" for screen readers). */
  unread?: boolean;
  /** `() => void` — shows an "Open" button (e.g. go to the feed). */
  onOpen?: () => void;
  /** Accessible name of the Open button. Defaults to "Open {title}". */
  openLabel?: string;
  headingLevel?: 3 | 4;
  as?: 'div' | 'li';
  className?: string;
}

/**
 * One notification: icon tile, title with an unread dot, description, time, and an optional
 * Open action. Render inside a `<ul>` with `as="li"`.
 */
export function NotificationItem({
  icon,
  title,
  description,
  timestamp,
  dateTime,
  unread = false,
  onOpen,
  openLabel,
  headingLevel = 3,
  as: Comp = 'div',
  className,
}: NotificationItemProps) {
  const Heading = `h${headingLevel}` as React.ElementType;
  return (
    <Comp
      className={['notification-item', className].filter(Boolean).join(' ')}
      data-unread={unread ? '' : undefined}
    >
      {icon && (
        <span className="notification-item__icon">
          <Icon name={icon} size="sm" />
        </span>
      )}
      <div className="notification-item__text">
        <Heading className="notification-item__title">
          <span className="notification-item__title-text">{title}</span>
          {unread && <StatusDot tone="accent" label="Unread" />}
        </Heading>
        {description && <p className="notification-item__description">{description}</p>}
        {timestamp && (
          <time className="notification-item__time" dateTime={dateTime}>{timestamp}</time>
        )}
      </div>
      {onOpen && (
        <IconButton
          className="notification-item__action"
          icon={<Icon name="ArrowSquareOut" size="sm" />}
          label={openLabel ?? `Open ${title}`}
          tooltipSide="left"
          onClick={onOpen}
        />
      )}
    </Comp>
  );
}
