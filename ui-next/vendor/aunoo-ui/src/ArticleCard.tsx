import { useId, useState } from 'react';
import { Button } from './Button';
import { Icon } from './Icon';
import { IconButton } from './IconButton';
import { Menu, type MenuItem } from './Menu';
import './ArticleCard.css';

export interface ArticleCardProps {
  title: React.ReactNode;
  /** Opens the title as a link (new tab). */
  href?: string;
  /** Top line, e.g. "Oct 5, 2026" or "AI and Machine Learning · Technology". */
  meta?: React.ReactNode;
  /** A string renders as body text under the title; any other node (e.g. a `<Banner>`) closes the header, after the footer. */
  summary?: React.ReactNode;
  /** Expanded content, revealed by the "See more" toggle in the top row and shown after the header. */
  details?: React.ReactNode;
  /** Chips row, e.g. category + signal `<Chip>`s. */
  tags?: React.ReactNode;
  /** Bottom line, e.g. source link and relative time. */
  footer?: React.ReactNode;
  /** Small flag next to the meta, e.g. `<Chip size="sm" tone="accent">Promoted</Chip>`. */
  flag?: React.ReactNode;
  /** `[{ id, label, icon? }]` — shows a ⋮ menu. */
  actions?: MenuItem[];
  /** `(id) => void` */
  onAction?: (id: string) => void;
  /** Accessible name of the ⋮ button — include the title so each card's menu is distinct. */
  actionsLabel?: string;
  /** Leading control, e.g. a select-this-article `<Checkbox>`. */
  leading?: React.ReactNode;
  /** Inside a `Grid`: take the whole row while expanded, so neighbours don't stretch to match. */
  expandFullWidth?: boolean;
  /** card = standalone panel · row = compact inset row for long lists */
  variant?: 'card' | 'row';
  headingLevel?: 3 | 4;
  /** Faded title: already read. */
  read?: boolean;
  as?: 'article' | 'li';
  className?: string;
}

/**
 * News item: meta line, title, summary (optionally expandable), tag chips, footer and an
 * actions menu. Used for briefing articles, incidents, narratives and article lists.
 */
export function ArticleCard({
  title,
  href,
  meta,
  summary,
  details,
  tags,
  footer,
  flag,
  actions,
  onAction,
  actionsLabel = 'Article actions',
  leading,
  expandFullWidth = false,
  variant = 'card',
  headingLevel = 3,
  read = false,
  as: Comp = 'article',
  className,
}: ArticleCardProps) {
  const [expanded, setExpanded] = useState(false);
  const detailsId = useId();
  const Heading = `h${headingLevel}` as React.ElementType;

  return (
    <Comp
      className={['article-card', `article-card--${variant}`, className].filter(Boolean).join(' ')}
      data-read={read ? '' : undefined}
      data-grid-span={expandFullWidth && expanded ? 'full' : undefined}
    >
      {leading && <div className="article-card__leading">{leading}</div>}
      <div className="article-card__main">
        {(meta || flag || actions || details) && (
          <div className="article-card__top">
            {meta && <div className="article-card__meta">{meta}</div>}
            {flag}
            {details && (
              <Button
                variant="ghost"
                size="sm"
                className="article-card__more"
                aria-expanded={expanded}
                aria-controls={detailsId}
                iconEnd={<Icon name="CaretDown" size="sm" className="article-card__chevron" />}
                onClick={() => setExpanded((e) => !e)}
              >
                {expanded ? 'See less' : 'See more'}
              </Button>
            )}
            {actions && (
              <Menu
                items={actions}
                onSelect={(id) => onAction?.(id)}
                trigger={
                  <IconButton
                    className="article-card__menu"
                    icon={<Icon name="DotsThreeOutlineVertical" size="sm" />}
                    label={actionsLabel}
                  />
                }
              />
            )}
          </div>
        )}
        <Heading className="article-card__title">
          {href ? (
            <a href={href} target="_blank" rel="noreferrer">
              {title}
              <span className="visually-hidden"> (opens in new tab)</span>
            </a>
          ) : (
            title
          )}
        </Heading>
        {typeof summary === 'string' && <p className="article-card__summary">{summary}</p>}
        {tags && <div className="article-card__tags">{tags}</div>}
        {footer && <div className="article-card__footer">{footer}</div>}
        {/* A block summary (e.g. a "Why this matters" Banner) closes the header, after the source */}
        {summary && typeof summary !== 'string' && <div className="article-card__summary-block">{summary}</div>}
        {details && (
          <div id={detailsId} className="article-card__details" hidden={!expanded}>
            {details}
          </div>
        )}
      </div>
    </Comp>
  );
}
