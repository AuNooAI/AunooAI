import { useId } from 'react';
import { Checkbox } from './Checkbox';
import { Icon } from './Icon';
import { IconButton } from './IconButton';
import { Popover } from './Popover';
import './MultiSelect.css';

export interface MultiSelectOption {
  value: string;
  label: string;
}

export interface MultiSelectProps {
  /** Visible label (also names the list). */
  label: string;
  options: MultiSelectOption[];
  /** Selected values. */
  value: string[];
  /** `(values) => void` */
  onValueChange: (values: string[]) => void;
  /** Trigger text with nothing selected. */
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

/**
 * Pick several values from a list, e.g. a table filter. The trigger looks like Select and
 * summarises the choice; the list is a group of checkboxes in a Popover. A ✕ clears it.
 */
export function MultiSelect({ label, options, value, onValueChange, placeholder = 'Select options', disabled = false, className }: MultiSelectProps) {
  const id = useId();
  const chosen = options.filter((o) => value.includes(o.value));
  const summary = chosen.length === 0 ? placeholder : chosen.length === 1 ? chosen[0].label : `${chosen.length} selected`;
  const toggle = (v: string, on: boolean) => onValueChange(on ? [...value, v] : value.filter((x) => x !== v));

  return (
    <div className={['multi-select', className].filter(Boolean).join(' ')}>
      <span id={`${id}-label`} className="multi-select__label">{label}</span>
      <div className="multi-select__row">
        <Popover
          label={label}
          align="start"
          trigger={
            <button type="button" className="multi-select__trigger" disabled={disabled} aria-labelledby={`${id}-label ${id}-value`} data-placeholder={chosen.length ? undefined : ''}>
              <span id={`${id}-value`} className="multi-select__value">{summary}</span>
              <Icon name="CaretDown" size="sm" className="multi-select__caret" />
            </button>
          }
        >
          <div role="group" aria-label={label} className="multi-select__list">
            {options.map((o) => (
              <Checkbox key={o.value} label={o.label} checked={value.includes(o.value)} onCheckedChange={(c) => toggle(o.value, c)} />
            ))}
          </div>
        </Popover>
        {value.length > 0 && !disabled && <IconButton icon={<Icon name="X" size="sm" />} label={`Clear ${label}`} onClick={() => onValueChange([])} />}
      </div>
    </div>
  );
}
