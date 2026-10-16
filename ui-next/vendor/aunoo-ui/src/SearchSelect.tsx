import { useEffect, useId, useRef, useState } from 'react';
import * as RadixPopover from '@radix-ui/react-popover';
import { Icon } from './Icon';
import type { IconName } from './icons';
import './SearchSelect.css';

export interface SearchSelectOption {
  value: string;
  label: string;
  /** Small text after the label, e.g. "Primary" or an article count. */
  hint?: string;
}

export interface SearchSelectProps {
  /** Always required. Use `hideLabel` to keep it screen-reader only. */
  label: string;
  hideLabel?: boolean;
  options: SearchSelectOption[];
  value: string;
  /** `(value) => void` */
  onValueChange: (value: string) => void;
  /** Placeholder of the search box. */
  searchPlaceholder?: string;
  icon?: IconName;
  emptyText?: string;
  className?: string;
}

/**
 * Pick one of many options by typing (ARIA combobox: type to filter, ↑/↓ to move, Enter to
 * choose, Escape to close). For long lists where a plain Select gets unwieldy, e.g. 143 brands.
 */
export function SearchSelect({
  label,
  hideLabel = false,
  options,
  value,
  onValueChange,
  searchPlaceholder = 'Search…',
  icon,
  emptyText = 'No matches',
  className,
}: SearchSelectProps) {
  const id = useId();
  const listId = `${id}-list`;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);

  const q = query.trim().toLowerCase();
  const filtered = q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options;
  const selected = options.find((o) => o.value === value);

  // Open on the current value; reset the search each time
  useEffect(() => {
    if (open) {
      setQuery('');
      setActive(Math.max(0, options.findIndex((o) => o.value === value)));
    }
  }, [open, options, value]);

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`#${CSS.escape(`${listId}-${active}`)}`)?.scrollIntoView({ block: 'nearest' });
  }, [active, listId]);

  const choose = (option: SearchSelectOption | undefined) => {
    if (!option) return;
    onValueChange(option.value);
    setOpen(false);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    const last = filtered.length - 1;
    if (event.key === 'ArrowDown') setActive((a) => Math.min(last, a + 1));
    else if (event.key === 'ArrowUp') setActive((a) => Math.max(0, a - 1));
    else if (event.key === 'Home') setActive(0);
    else if (event.key === 'End') setActive(last);
    else if (event.key === 'Enter') choose(filtered[active]);
    else return;
    event.preventDefault();
  };

  return (
    <div className={['search-select', className].filter(Boolean).join(' ')}>
      <label htmlFor={id} className={hideLabel ? 'visually-hidden' : 'search-select__label'}>{label}</label>
      <RadixPopover.Root open={open} onOpenChange={setOpen}>
        <RadixPopover.Trigger asChild>
          <button id={id} type="button" className="search-select__trigger" aria-haspopup="listbox">
            {icon && <Icon name={icon} size="sm" className="search-select__icon" />}
            <span className="search-select__value">{selected?.label ?? '—'}</span>
            <Icon name="CaretDown" size="sm" className="search-select__caret" />
          </button>
        </RadixPopover.Trigger>
        <RadixPopover.Portal>
          <RadixPopover.Content className="search-select__content" align="start" aria-label={label}>
            <input
              className="search-select__input"
              type="text"
              role="combobox"
              aria-label={`Search ${label.toLowerCase()}`}
              aria-expanded="true"
              aria-controls={listId}
              aria-autocomplete="list"
              aria-activedescendant={filtered[active] ? `${listId}-${active}` : undefined}
              placeholder={searchPlaceholder}
              value={query}
              autoComplete="off"
              onChange={(event) => {
                setQuery(event.target.value);
                setActive(0);
              }}
              onKeyDown={onKeyDown}
            />
            <span className="visually-hidden" role="status">
              {filtered.length} {filtered.length === 1 ? 'match' : 'matches'}
            </span>
            <ul ref={listRef} id={listId} className="search-select__list" role="listbox" aria-label={label}>
              {filtered.map((option, index) => (
                <li
                  key={option.value}
                  id={`${listId}-${index}`}
                  role="option"
                  aria-selected={option.value === value}
                  data-active={index === active ? '' : undefined}
                  className="search-select__option"
                  // Keep focus in the search box while clicking an option
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseMove={() => setActive(index)}
                  onClick={() => choose(option)}
                >
                  <span className="search-select__option-label">{option.label}</span>
                  {option.hint && <span className="search-select__hint">{option.hint}</span>}
                  {option.value === value && <Icon name="Check" size="sm" className="search-select__check" />}
                </li>
              ))}
              {filtered.length === 0 && <li className="search-select__empty" role="presentation">{emptyText}</li>}
            </ul>
          </RadixPopover.Content>
        </RadixPopover.Portal>
      </RadixPopover.Root>
    </div>
  );
}
