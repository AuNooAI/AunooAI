import { Meter, Stack, Text } from '@aunoo/ui';
import './geo.css';

/*
 * Horizontal bars as a list of labelled meters, in place of the old page's recharts bar charts. Each
 * row names its value in words, so the bar is a summary and the number is always readable. A row can
 * be a button (a category that filters the Articles tab).
 */
export interface BarRow {
  id: string;
  label: string;
  value: number;
  /** Shown instead of the bare number, e.g. "12 hotspots (8%)" */
  valueText?: string;
  tone?: 'neutral' | 'success' | 'warning' | 'error';
}

export function BarList({ rows, max, onPick, pickLabel, empty = 'Nothing to show yet.' }: {
  rows: BarRow[];
  /** Defaults to the largest value */
  max?: number;
  onPick?: (id: string) => void;
  /** Accessible name for the pick action, e.g. (label) => `Show ${label} articles` */
  pickLabel?: (label: string) => string;
  empty?: string;
}) {
  if (!rows.length) return <Text variant="caption">{empty}</Text>;
  const top = max ?? Math.max(1, ...rows.map((r) => r.value));
  return (
    <Stack as="ul" gap="sm" label="Values">
      {rows.map((r) => {
        // The meter's own label is for screen readers only, so the name is shown above it too
        const meter = (
          <>
            <Text variant="label" as="span">{r.label}</Text>
            <Meter label={r.label} value={r.value} min={0} max={top} valueText={r.valueText ?? r.value.toLocaleString()} tone={r.tone ?? 'neutral'} />
          </>
        );
        return (
          <li key={r.id}>
            {onPick ? (
              <button type="button" className="geo-linkbutton geo-linkbutton--block" aria-label={pickLabel?.(r.label)} onClick={() => onPick(r.id)}>
                {meter}
              </button>
            ) : meter}
          </li>
        );
      })}
    </Stack>
  );
}
