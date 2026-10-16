import './divergingBars.css';

/*
 * Bars either side of a zero line: growth to the right in green, shrinkage to the left in red, as
 * the old headcount-movers chart drew them. The design system's bar charts can't draw negatives.
 * Each row's name is a button when onSelect is given; the value is written beside its bar.
 */

export interface DivergingRow {
  id: string | number;
  label: string;
  value: number;
  /** Shown beside the bar, e.g. "+9 staff (+20.9%)" */
  valueText: string;
  color?: string;
  onSelect?: () => void;
}

export function DivergingBars({ title, rows }: { title: string; rows: DivergingRow[] }) {
  const max = Math.max(1, ...rows.map((r) => Math.abs(r.value)));
  return (
    <ul className="mm-div" aria-label={title}>
      {rows.map((r) => {
        const w = `${(Math.abs(r.value) / max) * 100}%`;
        const up = r.value >= 0;
        return (
          <li key={r.id} className="mm-div__row">
            <span className="mm-div__label">
              {r.color && <span className="mm-div__swatch" style={{ background: r.color }} aria-hidden="true" />}
              {r.onSelect ? <button type="button" className="text-link mm-linkbutton" onClick={r.onSelect}>{r.label}</button> : r.label}
            </span>
            <span className="mm-div__track" aria-hidden="true">
              <span className="mm-div__half mm-div__half--neg">{!up && <span className="mm-div__bar mm-div__bar--neg" style={{ width: w }} />}</span>
              <span className="mm-div__half mm-div__half--pos">{up && <span className="mm-div__bar mm-div__bar--pos" style={{ width: w }} />}</span>
            </span>
            <span className={`mm-div__value ${up ? 'mm-div__value--pos' : 'mm-div__value--neg'}`}>{r.valueText}</span>
          </li>
        );
      })}
    </ul>
  );
}
