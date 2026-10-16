import { useId, useState } from 'react';
import { TopicPill } from './TopicPill';
import './TagInput.css';

export interface TagInputProps {
  label: string;
  /** Current tags. */
  tags: string[];
  /** `(tags) => void` */
  onChange: (tags: string[]) => void;
  placeholder?: string;
  /** Clickable suggestions not yet added. */
  suggestions?: string[];
  hint?: React.ReactNode;
  className?: string;
}

/**
 * Free-form tags: type and press Enter (or comma) to add; Backspace in an empty box removes the
 * last tag; click a tag to remove it. Suggestions are one-click adds.
 */
export function TagInput({ label, tags, onChange, placeholder = 'Type and press Enter', suggestions = [], hint, className }: TagInputProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const [draft, setDraft] = useState('');
  const has = (value: string) => tags.some((t) => t.toLowerCase() === value.toLowerCase());
  const add = (value: string) => {
    const clean = value.trim().replace(/,$/, '').trim();
    if (clean && !has(clean)) onChange([...tags, clean]);
    setDraft('');
  };
  const open = suggestions.filter((s) => !has(s));

  return (
    <div className={['tag-input', className].filter(Boolean).join(' ')}>
      <label htmlFor={id} className="tag-input__label">{label}</label>
      <div className="tag-input__box">
        {tags.length > 0 && (
          <ul className="tag-input__tags" aria-label={`${label}: added`}>
            {tags.map((tag) => (
              <li key={tag}>
                <TopicPill label={tag} selected onToggle={() => onChange(tags.filter((t) => t !== tag))} />
              </li>
            ))}
          </ul>
        )}
        <input
          id={id}
          className="tag-input__input"
          value={draft}
          placeholder={placeholder}
          aria-describedby={hintId}
          autoComplete="off"
          onChange={(event) => (event.target.value.endsWith(',') ? add(event.target.value) : setDraft(event.target.value))}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              add(draft);
            } else if (event.key === 'Backspace' && !draft && tags.length) {
              onChange(tags.slice(0, -1));
            }
          }}
        />
      </div>
      {hint && <p id={hintId} className="tag-input__hint">{hint}</p>}
      {open.length > 0 && (
        <div className="tag-input__suggestions">
          <span className="tag-input__hint">Suggestions — click to add</span>
          <ul className="tag-input__tags" aria-label={`${label}: suggestions`}>
            {open.map((s) => (
              <li key={s}>
                <TopicPill label={s} onToggle={() => add(s)} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
