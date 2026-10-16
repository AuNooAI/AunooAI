import { useId, useState } from 'react';
import * as RadixSelect from '@radix-ui/react-select';
import { Icon } from './Icon';
import type { IconName } from './icons';
import './Select.css';

export interface SelectOption {
  value: string;
  label: string;
  /** Second line in the list (not shown on the trigger). */
  description?: string;
  /** Phosphor name registered in Icon. */
  icon?: IconName;
  /** Small tag after the label, e.g. "Default". */
  tag?: string;
  /** Heading of the group this option belongs to. Consecutive options with the same group are listed under it. */
  group?: string;
  disabled?: boolean;
}

export interface SelectProps {
  /** Always required. Use `hideLabel` to keep it screen-reader only. */
  label: string;
  hideLabel?: boolean;
  /** Helper text under the trigger, e.g. "Slower speeds are easier to read". */
  hint?: React.ReactNode;
  options: SelectOption[];
  /** Controlled value. Pair with `onValueChange`. */
  value?: string;
  defaultValue?: string;
  /** `(value) => void` */
  onValueChange?: (value: string) => void;
  placeholder?: string;
  /** Icon at the start of the trigger, e.g. "CalendarBlank". */
  icon?: IconName;
  /** Extra action at the bottom of the list, e.g. "Configure Profiles". Doesn't change the value. */
  footerAction?: { label: string; icon?: IconName; onSelect: () => void };
  disabled?: boolean;
  /** Stretch the trigger to its container. */
  fullWidth?: boolean;
  className?: string;
}

const ACTION_VALUE = '__select-footer-action__';

/**
 * Single-choice dropdown (Radix Select: arrow keys, typeahead, Escape, focus returns to the
 * trigger). The chosen option shows a check. Options can carry an icon, a description and a tag.
 */
export function Select({
  label,
  hideLabel = false,
  hint,
  options,
  value,
  defaultValue,
  onValueChange,
  placeholder,
  icon,
  footerAction,
  disabled = false,
  fullWidth = false,
  className,
}: SelectProps) {
  const id = useId();
  const [inner, setInner] = useState(defaultValue);
  const current = value ?? inner;

  const handleChange = (next: string) => {
    if (next === ACTION_VALUE) {
      footerAction?.onSelect();
      return;
    }
    if (value === undefined) setInner(next);
    onValueChange?.(next);
  };

  return (
    <div className={['select', fullWidth && 'select--full', className].filter(Boolean).join(' ')}>
      <label htmlFor={id} className={hideLabel ? 'select__label visually-hidden' : 'select__label'}>{label}</label>
      <RadixSelect.Root value={current} onValueChange={handleChange} disabled={disabled}>
        <RadixSelect.Trigger id={id} className="select__trigger" aria-describedby={hint ? `${id}-hint` : undefined}>
          {icon && <Icon name={icon} size="sm" className="select__trigger-icon" />}
          <span className="select__value">
            <RadixSelect.Value placeholder={placeholder} />
          </span>
          <RadixSelect.Icon className="select__caret">
            <Icon name="CaretDown" size="sm" />
          </RadixSelect.Icon>
        </RadixSelect.Trigger>
        <RadixSelect.Portal>
          <RadixSelect.Content className="select__content" position="popper" align="start">
            <RadixSelect.Viewport className="select__viewport">
              {groupOptions(options).map(({ group, items }, index) => {
                const rendered = items.map((option) => (
                  <RadixSelect.Item key={option.value} value={option.value} disabled={option.disabled} className="select__item">
                    {option.icon && <Icon name={option.icon} size="sm" className="select__item-icon" />}
                    <span className="select__item-text">
                      <span className="select__item-label">
                        <RadixSelect.ItemText>{option.label}</RadixSelect.ItemText>
                        {option.tag && <span className="select__tag">{option.tag}</span>}
                      </span>
                      {option.description && <span className="select__item-description">{option.description}</span>}
                    </span>
                    <RadixSelect.ItemIndicator className="select__check">
                      <Icon name="Check" size="sm" />
                    </RadixSelect.ItemIndicator>
                  </RadixSelect.Item>
                ));
                return group ? (
                  <RadixSelect.Group key={`${group}-${index}`}>
                    {index > 0 && <RadixSelect.Separator className="select__separator" />}
                    <RadixSelect.Label className="select__group-label">{group}</RadixSelect.Label>
                    {rendered}
                  </RadixSelect.Group>
                ) : (
                  rendered
                );
              })}
              {footerAction && (
                <>
                  <RadixSelect.Separator className="select__separator" />
                  <RadixSelect.Item value={ACTION_VALUE} className="select__item select__item--action">
                    {footerAction.icon && <Icon name={footerAction.icon} size="sm" className="select__item-icon" />}
                    <RadixSelect.ItemText>{footerAction.label}</RadixSelect.ItemText>
                  </RadixSelect.Item>
                </>
              )}
            </RadixSelect.Viewport>
          </RadixSelect.Content>
        </RadixSelect.Portal>
      </RadixSelect.Root>
      {hint && <p id={`${id}-hint`} className="select__hint">{hint}</p>}
    </div>
  );
}

/** Runs of consecutive options that share a `group`. */
function groupOptions(options: SelectOption[]) {
  const runs: { group?: string; items: SelectOption[] }[] = [];
  for (const option of options) {
    const last = runs[runs.length - 1];
    if (last && last.group === option.group) last.items.push(option);
    else runs.push({ group: option.group, items: [option] });
  }
  return runs;
}
