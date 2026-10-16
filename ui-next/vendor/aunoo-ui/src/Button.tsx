import type { ReactNode } from 'react';
import { Slot, Slottable } from '@radix-ui/react-slot';
import './Button.css';

export interface ButtonProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'type'> {
  /** primary = accent (one per block) · secondary = neutral chip · ghost = transparent · onSurface = secondary lifted on an inset areaBg block ·
   *  danger = confirms a destructive action (Delete), in place of primary */
  variant?: 'primary' | 'secondary' | 'ghost' | 'onSurface' | 'danger';
  /** sm 28px · md 32px · lg 36px (next to a field, or full width) */
  size?: 'sm' | 'md' | 'lg';
  /** Icon element before the label, e.g. `<Icon name="Plus" size="sm" />` */
  iconStart?: ReactNode;
  /** Icon element after the label, e.g. `<Icon name="ArrowSquareOut" size="sm" />` */
  iconEnd?: ReactNode;
  fullWidth?: boolean;
  /** Action in progress: disabled + aria-busy. Pass the in-progress label as children. */
  busy?: boolean;
  disabled?: boolean;
  /** Render the single child element (e.g. an `<a>`) with button styling. */
  asChild?: boolean;
  type?: 'button' | 'submit' | 'reset';
  className?: string;
  children: ReactNode;
}

/**
 * Text button. One `primary` per block (§3.1).
 * Use `asChild` to render a link: `<Button asChild><a href="…">Full reference</a></Button>`.
 */
export function Button({
  variant = 'primary',
  size = 'md',
  iconStart,
  iconEnd,
  fullWidth = false,
  busy = false,
  disabled = false,
  asChild = false,
  type = 'button',
  className,
  children,
  ...rest
}: ButtonProps) {
  const Comp = asChild ? Slot : 'button';
  const isDisabled = disabled || busy;
  const classes = [
    'button',
    `button--${variant}`,
    `button--${size}`,
    fullWidth && 'button--full',
    className,
  ].filter(Boolean).join(' ');

  return (
    <Comp
      className={classes}
      {...(asChild ? { 'aria-disabled': isDisabled || undefined } : { type, disabled: isDisabled })}
      aria-busy={busy || undefined}
      data-disabled={isDisabled ? '' : undefined}
      {...rest}
    >
      {iconStart}
      <Slottable>{children}</Slottable>
      {iconEnd}
    </Comp>
  );
}
