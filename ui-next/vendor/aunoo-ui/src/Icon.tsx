import { ICONS, STROKE_ICONS, type IconName } from './icons';
import './Icon.css';

export interface IconProps {
  /** Phosphor icon name, e.g. "Plug". Must be registered in `icons.ts`. */
  name: IconName;
  /** sm 16 · md 20 · lg 24 */
  size?: 'sm' | 'md' | 'lg';
  /** Accessible name. Omit for decorative icons next to a text label. */
  label?: string;
  className?: string;
}

/**
 * Phosphor icon in the fill weight — except chevrons (`STROKE_ICONS`), which use the regular stroke weight.
 * Colour follows the text (currentColor).
 * Decorative by default (hidden from screen readers); pass `label` when the icon carries meaning on its own.
 */
export function Icon({ name, size = 'md', label, className }: IconProps) {
  const PhosphorIcon = ICONS[name];
  const a11y = label
    ? { role: 'img' as const, 'aria-label': label }
    : { 'aria-hidden': true, focusable: 'false' as const };
  return (
    <PhosphorIcon
      weight={STROKE_ICONS.has(name) ? 'regular' : 'fill'}
      color="currentColor"
      className={['icon', `icon--${size}`, className].filter(Boolean).join(' ')}
      {...a11y}
    />
  );
}
