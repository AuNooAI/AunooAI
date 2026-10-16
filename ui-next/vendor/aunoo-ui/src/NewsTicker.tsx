import { useEffect, useState } from 'react';
import { Icon } from './Icon';
import { IconButton } from './IconButton';
import { StatusPill } from './StatusPill';
import './NewsTicker.css';

export interface NewsTickerItem {
  id: string;
  /** Pre-formatted time, e.g. "13:30". */
  time?: string;
  /** Machine-readable ISO time for `<time dateTime>`. */
  dateTime?: string;
  title: React.ReactNode;
  /** e.g. "Techmeme". */
  source?: React.ReactNode;
  /** Opens in a new tab. */
  href?: string;
}

export interface NewsTickerProps {
  /** `[{ id, time?, dateTime?, title, source?, href? }]` — newest first. */
  items: NewsTickerItem[];
  /** Accessible name for the strip. */
  label?: string;
  /** Visible pill text. */
  badge?: React.ReactNode;
  /** `() => void` — shows the Refresh button. */
  onRefresh?: () => void;
  /** `() => void` — shows the Settings button. */
  onSettings?: () => void;
  /** `() => void` — shows the Hide button. */
  onDismiss?: () => void;
  /** Scroll the headlines continuously, one full pass every N seconds. Omit for a static, swipeable list.
   *  Adds a Pause / Play button; stops on hover or focus; never moves under prefers-reduced-motion. */
  cycleSeconds?: number;
  /** With `cycleSeconds`: start paused (the user presses Play). */
  defaultPaused?: boolean;
  className?: string;
}

/**
 * One-line strip of the latest headlines with a live pill and actions. Static — it scrolls
 * sideways on demand instead of auto-scrolling (no marquee motion in §2.12).
 */
export function NewsTicker({
  items,
  label = 'Latest headlines',
  badge = 'Latest',
  onRefresh,
  onSettings,
  onDismiss,
  cycleSeconds,
  defaultPaused = false,
  className,
}: NewsTickerProps) {
  const [paused, setPaused] = useState(defaultPaused);
  useEffect(() => setPaused(defaultPaused), [defaultPaused]);
  const moving = Boolean(cycleSeconds) && items.length > 0;
  const hasActions = moving || onRefresh || onSettings || onDismiss;

  const renderItems = (copy: boolean) =>
    items.map((item) => (
      <li key={`${copy ? 'copy-' : ''}${item.id}`} className="news-ticker__item" aria-hidden={copy || undefined}>
        {item.time && (
          <time className="news-ticker__time" dateTime={item.dateTime}>{item.time}</time>
        )}
        {item.href ? (
          <a className="news-ticker__title" href={item.href} target="_blank" rel="noreferrer" tabIndex={copy ? -1 : undefined}>
            {item.title}
          </a>
        ) : (
          <span className="news-ticker__title">{item.title}</span>
        )}
        {item.source && <span className="news-ticker__source">{item.source}</span>}
      </li>
    ));

  return (
    <section className={['news-ticker', className].filter(Boolean).join(' ')} aria-label={label}>
      <StatusPill variant="compact" tone="live" className="news-ticker__badge">{badge}</StatusPill>
      {moving ? (
        // The list is drawn twice so the loop is seamless; the copy is hidden from assistive tech
        <div className="news-ticker__viewport" tabIndex={0} role="region" aria-label="Headlines">
          <ul
            className="news-ticker__list news-ticker__list--moving"
            data-paused={paused || undefined}
            style={{ '--ticker-cycle': `${cycleSeconds}s` } as React.CSSProperties}
          >
            {renderItems(false)}
            {renderItems(true)}
          </ul>
        </div>
      ) : (
        <ul className="news-ticker__list" tabIndex={0} aria-label="Headlines">
          {renderItems(false)}
        </ul>
      )}
      {hasActions && (
        <div className="news-ticker__actions">
          {moving && (
            <IconButton
              icon={<Icon name={paused ? 'Play' : 'Pause'} size="sm" />}
              label={paused ? 'Play headlines' : 'Pause headlines'}
              onClick={() => setPaused((p) => !p)}
            />
          )}
          {onRefresh && (
            <IconButton icon={<Icon name="ArrowClockwise" size="sm" />} label="Refresh headlines" onClick={onRefresh} />
          )}
          {onSettings && (
            <IconButton icon={<Icon name="GearSix" size="sm" />} label="Headline settings" onClick={onSettings} />
          )}
          {onDismiss && (
            <IconButton icon={<Icon name="X" size="sm" />} label="Hide headlines" onClick={onDismiss} />
          )}
        </div>
      )}
    </section>
  );
}
