import type { ReactNode } from 'react';
import './Text.css';

export interface TextProps {
  variant?: 'description' | 'hint' | 'caption' | 'fine' | 'label';
  as?: 'p' | 'span' | 'div';
  align?: 'start' | 'center';
  /** error = a failure message (--error, AA on light surfaces). */
  tone?: 'default' | 'error';
  /** One line with an ellipsis. Give the full text another way too (e.g. a tooltip on a nearby button). */
  truncate?: boolean;
  className?: string;
  children: ReactNode;
}

/**
 * Small supporting copy styles used across panels.
 * - `description` 13px muted — panel and page descriptions
 * - `hint` 12px muted — notes, help lines, fine print that must be read
 * - `caption` 11.5px subtle — secondary hints ("Click a topic to remove it…")
 * - `fine` 11px subtle — legal-ish small print under a CTA
 * - `label` 12px medium muted — counts ("3 subscribed", "21 topics available")
 * `<code>` inside is set in Geist Mono.
 */
export function Text({ variant = 'hint', as: Comp = 'p', align = 'start', tone = 'default', truncate = false, className, children }: TextProps) {
  return (
    <Comp
      className={['text', `text--${variant}`, align === 'center' && 'text--center', tone === 'error' && 'text--error', truncate && 'text--truncate', className]
        .filter(Boolean)
        .join(' ')}
    >
      {children}
    </Comp>
  );
}
