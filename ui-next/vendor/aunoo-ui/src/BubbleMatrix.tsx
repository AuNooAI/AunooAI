import { chartColorClass, type ChartColor } from './chartColors';
import './BubbleMatrix.css';

export interface BubbleMatrixProps {
  /** The table caption. */
  title: string;
  /** Column headings (e.g. future signals). */
  columns: string[];
  /** One row per item (e.g. sentiment), each with its colour. */
  rows: { id: string; label: string; color: ChartColor; values: number[] }[];
  /** Hide the caption visually (when a Panel title already names it). */
  hideTitle?: boolean;
  className?: string;
}

/**
 * Counts at each row × column crossing, drawn as circles sized by count (area ∝ value). It's a real
 * table, so the numbers are read row by row; the circles are the visual summary.
 */
export function BubbleMatrix({ title, columns, rows, hideTitle = false, className }: BubbleMatrixProps) {
  const max = Math.max(1, ...rows.flatMap((r) => r.values));
  return (
    <div className={['bubble-matrix', className].filter(Boolean).join(' ')} role="region" aria-label={title} tabIndex={0}>
      <table className="bubble-matrix__table">
        <caption className={hideTitle ? 'visually-hidden' : 'bubble-matrix__caption'}>{title}</caption>
        <thead>
          <tr>
            <td />
            {columns.map((c) => <th key={c} scope="col">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <th scope="row">{r.label}</th>
              {r.values.map((v, i) => (
                <td key={columns[i]}>
                  <span className="bubble-matrix__cell">
                    {v > 0 && (
                      <span
                        className={`bubble-matrix__bubble ${chartColorClass(r.color)}`}
                        style={{ width: `${Math.sqrt(v / max) * 100}%` }}
                        aria-hidden="true"
                      />
                    )}
                    <span className="bubble-matrix__value">{v}</span>
                  </span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
