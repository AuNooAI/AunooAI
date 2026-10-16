import { useId } from 'react';
import { Button } from './Button';
import { Eyebrow } from './Eyebrow';
import { Icon } from './Icon';
import './CodeBlock.css';

export interface CodeBlockProps {
  /** Eyebrow label above the code, e.g. "Claude Code — header auth" */
  label: string;
  /** The snippet. Rendered verbatim (whitespace preserved). */
  code: string;
  /** Show the "Copied" confirmation state. */
  copied?: boolean;
  copyLabel?: string;
  copiedLabel?: string;
  /** `(code) => void`. Omit to hide the Copy button. */
  onCopy?: (code: string) => void;
  className?: string;
}

/**
 * Labelled, horizontally scrollable code snippet with a Copy button.
 * The component doesn't touch the clipboard: it calls `onCopy(code)` and the
 * app sets `copied` to show confirmation.
 */
export function CodeBlock({ label, code, copied = false, copyLabel = 'Copy', copiedLabel = 'Copied', onCopy, className }: CodeBlockProps) {
  const labelId = useId();
  return (
    <div className={['code-block', className].filter(Boolean).join(' ')}>
      <div className="code-block__head">
        <Eyebrow as="span" id={labelId}>{label}</Eyebrow>
        {onCopy && (
          <Button
            variant="secondary"
            size="sm"
            iconStart={<Icon name={copied ? 'Check' : 'Copy'} size="sm" />}
            onClick={() => onCopy(code)}
            aria-describedby={labelId}
          >
            {copied ? copiedLabel : copyLabel}
          </Button>
        )}
      </div>
      {/* tabIndex lets keyboard users scroll long lines */}
      <pre className="code-block__code" tabIndex={0} aria-labelledby={labelId}>
        <code>{code}</code>
      </pre>
      <span className="visually-hidden" role="status">
        {copied ? `${label} ${copiedLabel.toLowerCase()}` : ''}
      </span>
    </div>
  );
}
