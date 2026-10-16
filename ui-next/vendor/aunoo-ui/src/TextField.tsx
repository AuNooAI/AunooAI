import type { ReactNode } from 'react';
import { useId, useState } from 'react';
import { Icon } from './Icon';
import { IconButton } from './IconButton';
import './TextField.css';

export interface TextFieldProps {
  /** Always required for accessibility. Use `hideLabel` to keep it screen-reader only. */
  label: string;
  hideLabel?: boolean;
  /** Controlled value. Pair with `onChange`. */
  value?: string;
  /** Uncontrolled initial value. */
  defaultValue?: string;
  placeholder?: string;
  /** Helper text under the field. */
  hint?: ReactNode;
  /** Error message. Marks the field invalid. */
  error?: ReactNode;
  disabled?: boolean;
  maxLength?: number;
  name?: string;
  type?: 'text' | 'email' | 'search' | 'url' | 'time' | 'number' | 'password' | 'date' | 'datetime-local';
  /** For `type="password"`: what the value is, for the show/hide button's name ("Show API key"). Default "password". */
  secretName?: string;
  /** For `type="number"` (a number) or the date types (an ISO date string). */
  min?: number | string;
  max?: number | string;
  /** For `type="time"`: seconds granularity, e.g. 1 to show HH:MM:SS. */
  step?: number;
  autoComplete?: string;
  /** Inline element to the right, usually `<Button size="lg">`. */
  action?: ReactNode;
  /** `(value, event) => void` */
  onChange?: (value: string, event: React.ChangeEvent<HTMLInputElement>) => void;
  /** `(value) => void` — called on Enter. */
  onSubmit?: (value: string) => void;
  id?: string;
  className?: string;
}

/**
 * Single-line text input with a label, optional hint/error and an inline action
 * (e.g. a "Send request" Button). Enter calls `onSubmit` with the current value.
 */
export function TextField({
  label,
  hideLabel = false,
  value,
  defaultValue,
  placeholder,
  hint,
  error,
  disabled = false,
  maxLength,
  name,
  type = 'text',
  secretName = 'password',
  autoComplete = 'off',
  step,
  min,
  max,
  action,
  onChange,
  onSubmit,
  id: idProp,
  className,
}: TextFieldProps) {
  const autoId = useId();
  const id = idProp ?? autoId;
  const [revealed, setRevealed] = useState(false);
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(' ') || undefined;

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && onSubmit) {
      event.preventDefault();
      onSubmit(event.currentTarget.value);
    }
  };

  return (
    <div className={['text-field', className].filter(Boolean).join(' ')}>
      <label htmlFor={id} className={hideLabel ? 'text-field__label visually-hidden' : 'text-field__label'}>
        {label}
      </label>
      <div className="text-field__row">
        <input
          id={id}
          name={name}
          type={type === 'password' && revealed ? 'text' : type}
          step={step}
          min={min}
          max={max}
          className="text-field__input"
          value={value}
          defaultValue={defaultValue}
          placeholder={placeholder}
          maxLength={maxLength}
          autoComplete={autoComplete}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          onChange={onChange ? (event) => onChange(event.target.value, event) : undefined}
          onKeyDown={handleKeyDown}
        />
        {type === 'password' && (
          <IconButton
            icon={<Icon name={revealed ? 'EyeSlash' : 'Eye'} size="sm" />}
            label={`${revealed ? 'Hide' : 'Show'} ${secretName}`}
            disabled={disabled}
            onClick={() => setRevealed((r) => !r)}
          />
        )}
        {action}
      </div>
      {error && (
        <p id={errorId} className="text-field__error">
          {error}
        </p>
      )}
      {hint && (
        <p id={hintId} className="text-field__hint">
          {hint}
        </p>
      )}
    </div>
  );
}
