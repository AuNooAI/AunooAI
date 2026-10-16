import { useId } from 'react';
import * as RadixSwitch from '@radix-ui/react-switch';
import './Switch.css';

export interface SwitchProps {
  /** Visible label (the accessible name). */
  label: React.ReactNode;
  /** Line under the label, e.g. "Generate dashboard content on a schedule". */
  description?: React.ReactNode;
  /** Controlled state. Pair with `onCheckedChange`. */
  checked?: boolean;
  defaultChecked?: boolean;
  /** `(checked) => void` */
  onCheckedChange?: (checked: boolean) => void;
  disabled?: boolean;
  id?: string;
  className?: string;
}

/**
 * On/off setting row: label and description on the left, switch on the right (Radix Switch,
 * role="switch"). §3.1: on = accent, off track = chipCount.
 */
export function Switch({ label, description, checked, defaultChecked, onCheckedChange, disabled = false, id: idProp, className }: SwitchProps) {
  const autoId = useId();
  const id = idProp ?? autoId;
  const descriptionId = description ? `${id}-description` : undefined;
  return (
    <div className={['switch', className].filter(Boolean).join(' ')} data-disabled={disabled ? '' : undefined}>
      <div className="switch__text">
        <label htmlFor={id} className="switch__label">{label}</label>
        {description && <p id={descriptionId} className="switch__description">{description}</p>}
      </div>
      <RadixSwitch.Root
        id={id}
        className="switch__control"
        checked={checked}
        defaultChecked={defaultChecked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        aria-describedby={descriptionId}
      >
        <RadixSwitch.Thumb className="switch__thumb" />
      </RadixSwitch.Root>
    </div>
  );
}
