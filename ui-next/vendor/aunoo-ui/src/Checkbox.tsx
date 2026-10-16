import { useId } from 'react';
import * as RadixCheckbox from '@radix-ui/react-checkbox';
import { Icon } from './Icon';
import './Checkbox.css';

export interface CheckboxProps {
  /** Visible label (also the accessible name). */
  label: React.ReactNode;
  /** Controlled state. Pair with `onCheckedChange`. `'indeterminate'` = some of a group (e.g. select-page with a partial selection). */
  checked?: boolean | 'indeterminate';
  defaultChecked?: boolean;
  /** `(checked) => void` */
  onCheckedChange?: (checked: boolean) => void;
  disabled?: boolean;
  /** Keep the label for screen readers only (e.g. a row-select box next to the row's title). */
  hideLabel?: boolean;
  /** Box before the label (default), or after it at the row's far end. */
  boxPosition?: 'start' | 'end';
  id?: string;
  className?: string;
}

/**
 * Checkbox with its label as one clickable row (Radix Checkbox). Checked = the Phosphor fill
 * `Check` at 20px in accent; unchecked = an empty box (§2.9, 2026-09-30 decision).
 */
export function Checkbox({
  label,
  checked,
  defaultChecked,
  onCheckedChange,
  disabled = false,
  boxPosition = 'start',
  hideLabel = false,
  id: idProp,
  className,
}: CheckboxProps) {
  const autoId = useId();
  const id = idProp ?? autoId;
  return (
    <div
      className={['checkbox', `checkbox--box-${boxPosition}`, className].filter(Boolean).join(' ')}
      data-disabled={disabled ? '' : undefined}
    >
      <RadixCheckbox.Root
        id={id}
        className="checkbox__control"
        checked={checked}
        defaultChecked={defaultChecked}
        onCheckedChange={(state) => onCheckedChange?.(state === true)}
        disabled={disabled}
      >
        <span className="checkbox__box" aria-hidden="true" />
        <RadixCheckbox.Indicator className="checkbox__indicator">
          <Icon name={checked === 'indeterminate' ? 'Minus' : 'Check'} size="md" />
        </RadixCheckbox.Indicator>
      </RadixCheckbox.Root>
      <label htmlFor={id} className={hideLabel ? 'visually-hidden' : 'checkbox__label'}>{label}</label>
    </div>
  );
}
