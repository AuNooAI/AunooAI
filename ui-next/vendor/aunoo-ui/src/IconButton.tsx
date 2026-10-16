import { Tooltip } from './Tooltip';
import './IconButton.css';

export interface IconButtonProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'type'> {
  /** Icon element, e.g. `<Icon name="Copy" size="sm" />` */
  icon: React.ReactNode;
  /** Accessible name and tooltip text, e.g. "Copy key" */
  label: string;
  /** danger = destructive action (turns --error on hover) */
  tone?: 'neutral' | 'danger';
  /** light = 28px chip on light surfaces · dark = 36px top-nav button on dark chrome */
  surface?: 'light' | 'dark';
  /** Shows an accent dot and adds this to the accessible name, e.g. "99+ unread". */
  badge?: string;
  /** Where the tooltip opens. */
  tooltipSide?: 'top' | 'right' | 'bottom' | 'left';
  disabled?: boolean;
  type?: 'button' | 'submit' | 'reset';
  className?: string;
}

/** Square icon-only button with a tooltip. `label` is required — it's the accessible name and the tooltip. */
export function IconButton({
  icon,
  label,
  tone = 'neutral',
  surface = 'light',
  badge,
  tooltipSide,
  disabled = false,
  type = 'button',
  className,
  ...rest
}: IconButtonProps) {
  return (
    <Tooltip content={label} side={tooltipSide}>
      <button
        type={type}
        className={['icon-button', `icon-button--${tone}`, `icon-button--${surface}`, className].filter(Boolean).join(' ')}
        aria-label={badge ? `${label}, ${badge}` : label}
        disabled={disabled}
        {...rest}
      >
        {icon}
        {badge && <span className="icon-button__badge" aria-hidden="true" />}
      </button>
    </Tooltip>
  );
}
