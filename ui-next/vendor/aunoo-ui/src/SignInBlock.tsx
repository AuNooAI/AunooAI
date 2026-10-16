import type { ReactNode } from 'react';
import { useId } from 'react';
import { CopyField } from './CopyField';
import { StatusPill } from './StatusPill';
import { Text } from './Text';
import './SignInBlock.css';

export interface SignInBlockField {
  id?: string;
  label: string;
  value: string;
  copied?: boolean;
}

export interface SignInBlockProps {
  title: ReactNode;
  /** Badge next to the title, e.g. "Recommended". */
  badge?: string;
  description?: ReactNode;
  /** `[{ id?, label, value, copied? }]` — rendered as CopyFields. */
  fields?: SignInBlockField[];
  /** Lines under the fields. `<code>` inside is set in mono. */
  hints?: ReactNode[];
  /** `(fieldId, value) => void` */
  onCopy?: (fieldId: string, value: string) => void;
  headingLevel?: 2 | 3 | 4;
  className?: string;
}

/**
 * Setup instructions on an inset surface: heading (+ optional badge), description,
 * one or more copyable values, and hint lines.
 */
export function SignInBlock({ title, badge, description, fields = [], hints = [], onCopy, headingLevel = 3, className }: SignInBlockProps) {
  const titleId = useId();
  const Heading = `h${headingLevel}` as const;
  return (
    <section className={['signin-block', className].filter(Boolean).join(' ')} aria-labelledby={titleId}>
      <div className="signin-block__head">
        <Heading id={titleId} className="signin-block__title">{title}</Heading>
        {badge && <StatusPill variant="compact">{badge}</StatusPill>}
      </div>
      {description && <Text variant="hint" className="signin-block__description">{description}</Text>}
      {fields.map((field) => (
        <CopyField
          key={field.id ?? field.label}
          className="signin-block__field"
          label={field.label}
          value={field.value}
          copied={field.copied}
          onCopy={onCopy ? () => onCopy(field.id ?? field.label, field.value) : undefined}
        />
      ))}
      {hints.map((hint, i) => (
        <Text key={i} variant="hint" className="signin-block__hint">{hint}</Text>
      ))}
    </section>
  );
}
