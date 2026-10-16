import { useId } from 'react';
import './TextArea.css';

export interface TextAreaProps {
  label: string;
  hideLabel?: boolean;
  value?: string;
  defaultValue?: string;
  /** `(value) => void` */
  onChange?: (value: string) => void;
  placeholder?: string;
  hint?: React.ReactNode;
  rows?: number;
  readOnly?: boolean;
  /** Geist Mono — prompts, templates, code. */
  mono?: boolean;
  className?: string;
}

/** Multi-line text input. `readOnly` keeps it selectable and focusable but not editable. */
export function TextArea({ label, hideLabel = false, value, defaultValue, onChange, placeholder, hint, rows = 4, readOnly = false, mono = false, className }: TextAreaProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <div className={['text-area', mono && 'text-area--mono', className].filter(Boolean).join(' ')}>
      <label htmlFor={id} className={hideLabel ? 'visually-hidden' : 'text-area__label'}>{label}</label>
      <textarea
        id={id}
        className="text-area__input"
        value={value}
        defaultValue={defaultValue}
        onChange={onChange ? (event) => onChange(event.target.value) : undefined}
        placeholder={placeholder}
        rows={rows}
        readOnly={readOnly}
        aria-describedby={hintId}
      />
      {hint && <p id={hintId} className="text-area__hint">{hint}</p>}
    </div>
  );
}
