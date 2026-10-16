import { useId } from 'react';
import { Button } from './Button';
import { CopyField } from './CopyField';
import { Icon } from './Icon';
import { IconButton } from './IconButton';
import './KeyCard.css';

export interface KeyCardProps {
  /** Key name the user gave it, e.g. "ChatGPT". */
  name: string;
  /** Pre-formatted metadata, e.g. "Created 2 hours ago · scoped to 3 topics". */
  meta?: React.ReactNode;
  /** The key (or a masked version of it). */
  value: string;
  copiedKey?: boolean;
  copiedLink?: boolean;
  /** `() => void`. Omit to hide "Copy MCP link". */
  onCopyLink?: () => void;
  /** `(value) => void` */
  onCopyKey?: (value: string) => void;
  /** `() => void`. Omit to hide revoke. */
  onRevoke?: () => void;
  className?: string;
}

/**
 * One API key: name, metadata, the key value, and actions (copy MCP link, copy key, revoke).
 * Confirmation before revoking is the app's job.
 */
export function KeyCard({
  name,
  meta,
  value,
  copiedKey = false,
  copiedLink = false,
  onCopyLink,
  onCopyKey,
  onRevoke,
  className,
}: KeyCardProps) {
  const nameId = useId();
  return (
    <div className={['key-card', className].filter(Boolean).join(' ')} role="group" aria-labelledby={nameId}>
      <div className="key-card__top">
        <div className="key-card__heading">
          <div id={nameId} className="key-card__name">
            <Icon name="Key" size="sm" />
            {name}
          </div>
          {meta && <div className="key-card__meta">{meta}</div>}
        </div>
        <div className="key-card__actions">
          {onCopyLink && (
            <Button
              variant="secondary"
              size="sm"
              iconStart={copiedLink ? <Icon name="Check" size="sm" /> : undefined}
              onClick={onCopyLink}
              aria-describedby={nameId}
            >
              {copiedLink ? 'Copied' : 'Copy MCP link'}
            </Button>
          )}
          {onRevoke && (
            <IconButton icon={<Icon name="Trash" size="sm" />} label={`Revoke ${name} key`} tone="danger" onClick={onRevoke} />
          )}
        </div>
      </div>
      <CopyField
        className="key-card__value"
        variant="icon"
        value={value}
        valueName={`${name} key`}
        copied={copiedKey}
        onCopy={onCopyKey}
      />
    </div>
  );
}
