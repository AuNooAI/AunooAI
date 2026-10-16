import { useId } from 'react';
import { Button } from './Button';
import { IconButton } from './IconButton';
import { Eyebrow } from './Eyebrow';
import { Icon } from './Icon';
import './CopyField.css';

export interface CopyFieldProps {
  /** Eyebrow label above, e.g. "MCP server URL". Also used in the copy button's accessible name. */
  label?: string;
  /** What the value is, for screen readers ("ChatGPT key"). Defaults to `label`. Needed when there's no label. */
  valueName?: string;
  /** The text to show and copy. */
  value: string;
  /** button = "Copy" text button, value scrolls (URLs, commands) · icon = icon button, value truncates (keys) */
  variant?: 'button' | 'icon';
  /** Show the copied confirmation. */
  copied?: boolean;
  copyLabel?: string;
  copiedLabel?: string;
  /** `(value) => void` */
  onCopy?: (value: string) => void;
  className?: string;
}

/**
 * Read-only value (URL, command, key) with a copy action.
 * The component doesn't touch the clipboard: it calls `onCopy(value)` and the app sets `copied`.
 */
export function CopyField({
  label,
  valueName,
  value,
  variant = 'button',
  copied = false,
  copyLabel = 'Copy',
  copiedLabel = 'Copied',
  onCopy,
  className,
}: CopyFieldProps) {
  const labelId = useId();
  const name = valueName ?? label ?? 'value';

  return (
    <div className={['copy-field', `copy-field--${variant}`, className].filter(Boolean).join(' ')}>
      {label && <Eyebrow as="span" id={labelId}>{label}</Eyebrow>}
      <div className="copy-field__row">
        {/* Scrolls for long commands; focusable so the keyboard can scroll it */}
        <code
          className="copy-field__value"
          tabIndex={variant === 'button' ? 0 : undefined}
          aria-labelledby={label ? labelId : undefined}
        >
          {value}
        </code>
        {variant === 'button' ? (
          <Button
            variant="secondary"
            size="sm"
            iconStart={<Icon name={copied ? 'Check' : 'Copy'} size="sm" />}
            onClick={() => onCopy?.(value)}
            aria-describedby={label ? labelId : undefined}
          >
            {copied ? copiedLabel : copyLabel}
          </Button>
        ) : (
          <IconButton
            icon={<Icon name={copied ? 'Check' : 'Copy'} size="sm" />}
            label={copied ? `${copiedLabel} ${name}` : `${copyLabel} ${name}`}
            onClick={() => onCopy?.(value)}
          />
        )}
      </div>
      <span className="visually-hidden" role="status">
        {copied ? `${name} ${copiedLabel.toLowerCase()}` : ''}
      </span>
    </div>
  );
}
