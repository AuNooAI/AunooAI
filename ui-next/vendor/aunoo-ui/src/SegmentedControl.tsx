import * as ToggleGroup from '@radix-ui/react-toggle-group';
import { Icon } from './Icon';
import type { IconName } from './icons';
import './SegmentedControl.css';

export interface SegmentedOption {
  value: string;
  label: string;
  icon?: IconName;
  /** Show only the icon; `label` becomes the accessible name. */
  iconOnly?: boolean;
}

export interface SegmentedControlProps {
  /** Accessible name for the group, e.g. "View". */
  label: string;
  options: SegmentedOption[];
  value: string;
  /** `(value) => void` — one option is always selected. */
  onValueChange: (value: string) => void;
  className?: string;
}

/**
 * Pick one of a few views (Radix ToggleGroup, single: arrow keys move between options).
 * §3.1 View toggle: track `rounded.mdPlus`, items `rounded.sm`; the chosen item is raised.
 */
export function SegmentedControl({ label, options, value, onValueChange, className }: SegmentedControlProps) {
  return (
    <ToggleGroup.Root
      type="single"
      className={['segmented', className].filter(Boolean).join(' ')}
      aria-label={label}
      value={value}
      // Radix sends "" when the active item is pressed again — keep the current choice
      onValueChange={(next) => next && onValueChange(next)}
    >
      {options.map((option) => (
        <ToggleGroup.Item
          key={option.value}
          value={option.value}
          className="segmented__item"
          aria-label={option.iconOnly ? option.label : undefined}
          title={option.iconOnly ? option.label : undefined}
        >
          {option.icon && <Icon name={option.icon} size="sm" />}
          {!option.iconOnly && option.label}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}
