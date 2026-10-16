import { useId } from 'react';
import './FileField.css';

export interface FileFieldProps {
  /** Visible label (the accessible name). */
  label: string;
  /** File types, e.g. ".csv,.json". */
  accept?: string;
  /** Helper text under the field. */
  hint?: React.ReactNode;
  /** `(file) => void` — `null` when the choice is cleared. */
  onFileChange: (file: File | null) => void;
  disabled?: boolean;
  className?: string;
}

/** Native file picker (keyboard and screen-reader support come with it), with the button styled as a secondary chip. */
export function FileField({ label, accept, hint, onFileChange, disabled = false, className }: FileFieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <div className={['file-field', className].filter(Boolean).join(' ')}>
      <label htmlFor={id} className="file-field__label">{label}</label>
      <input
        id={id}
        type="file"
        className="file-field__input"
        accept={accept}
        disabled={disabled}
        aria-describedby={hintId}
        onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
      />
      {hint && <p id={hintId} className="file-field__hint">{hint}</p>}
    </div>
  );
}
