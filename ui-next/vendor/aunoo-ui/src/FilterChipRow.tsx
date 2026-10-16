import { useState } from 'react';
import './FilterChipRow.css';

export interface FilterChipOption {
  value: string;
  label: string;
  /** Shown after the label, e.g. "(100)". */
  count?: number;
}

export interface FilterChipRowProps {
  /** Row label, e.g. "Sources" (also the group's accessible name). */
  label: string;
  options: FilterChipOption[];
  /** Selected values. Empty = "All". */
  selected: string[];
  /** `(values) => void` */
  onChange: (values: string[]) => void;
  /** Total shown next to the label, e.g. 100 → "Sources (100)". */
  total?: number;
  /** Chips shown before "+N more". Default 8. */
  maxVisible?: number;
  /** Label of the reset chip. */
  allLabel?: string;
  className?: string;
}

/**
 * Labelled row of toggle chips with an "All" reset and "+N more" overflow. Each chip is a
 * toggle button (`aria-pressed`); selecting none means all.
 */
export function FilterChipRow({
  label,
  options,
  selected,
  onChange,
  total,
  maxVisible = 8,
  allLabel = 'All',
  className,
}: FilterChipRowProps) {
  const [expanded, setExpanded] = useState(false);
  // Selected chips stay visible even when they'd be in the overflow
  const visible = expanded
    ? options
    : options.filter((option, index) => index < maxVisible || selected.includes(option.value));
  const hidden = options.length - visible.length;

  const toggle = (value: string) =>
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);

  return (
    <div className={['filter-chip-row', className].filter(Boolean).join(' ')} role="group" aria-label={label}>
      <span className="filter-chip-row__label" aria-hidden="true">
        {label}
        {total !== undefined && <span className="filter-chip-row__total"> ({total})</span>}
      </span>
      <div className="filter-chip-row__chips">
        <button type="button" className="filter-chip" aria-pressed={selected.length === 0} onClick={() => onChange([])}>
          {allLabel}
        </button>
        {visible.map((option) => (
          <button
            key={option.value}
            type="button"
            className="filter-chip"
            aria-pressed={selected.includes(option.value)}
            onClick={() => toggle(option.value)}
          >
            {option.label}
            {option.count !== undefined && <span className="filter-chip__count">{option.count}</span>}
          </button>
        ))}
        {(hidden > 0 || expanded) && options.length > maxVisible && (
          <button type="button" className="filter-chip filter-chip--more" aria-expanded={expanded} onClick={() => setExpanded((e) => !e)}>
            {expanded ? 'Show less' : `+${hidden} more`}
          </button>
        )}
      </div>
    </div>
  );
}
