import { Banner, Button, EmptyState, Icon, Meter, Skeleton, Stack, Text } from '@aunoo/ui';
import './policy.css';

/*
 * Small pieces every Crisis Tracker sub-tab uses: a ranked list of bars, the loading and empty
 * states, and the co-occurrence heatmap.
 */

export interface BarItem {
  id: string;
  label: string;
  value: number;
  /** Shown after the count, e.g. a percentage */
  note?: string;
  /** A line under the bar, e.g. what a category covers */
  detail?: string;
}

/** A ranked list of horizontal bars, each scaled against the largest */
export function BarList({ title, items, unit = 'articles', empty = 'Nothing to show for this period.' }: { title: string; items: BarItem[]; unit?: string; empty?: string }) {
  if (!items.length) return <Text variant="caption">{empty}</Text>;
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <Stack as="ul" gap="sm" label={title}>
      {items.map((i) => (
        <li key={i.id} className="policy-bar">
          {/* The meter's own label is for screen readers only, so the name is shown here too */}
          <Text variant="label" as="span">{i.label}</Text>
          <Meter label={i.label} value={i.value} max={max} valueText={`${i.value.toLocaleString()} ${unit}${i.note ? ` (${i.note})` : ''}`} />
          {i.detail && <Text variant="caption">{i.detail}</Text>}
        </li>
      ))}
    </Stack>
  );
}

export const Loading = ({ lines = 6 }: { lines?: number }) => <Skeleton variant="text" lines={lines} />;

/** For a breakdown whose read failed: says so and offers a retry */
export function LoadFailed({ what, onRetry }: { what: string; onRetry: () => void }) {
  return (
    <Banner
      tone="error"
      title={`The ${what} didn’t load`}
      description="The server didn’t answer for this period."
      action={<Button variant="secondary" size="sm" iconStart={<Icon name="ArrowClockwise" size="sm" />} onClick={onRetry}>Try again</Button>}
    />
  );
}

/**
 * Shown when the tracker has nothing for the period. Bugfixing and most sites have no data here until
 * someone runs Update data, so this says how data arrives.
 */
export function NoData({ onUpdate, period }: { onUpdate: () => void; period: string }) {
  return (
    <EmptyState
      icon="Scales"
      title={`No classified articles for ${period}`}
      action={<Button iconStart={<Icon name="DownloadSimple" size="sm" />} onClick={onUpdate}>Update data</Button>}
    >
      The tracker counts articles sorted into its ten policy categories. Articles arrive in two ways: Update data sorts the articles already
      collected for the tracker’s keyword group, or imports the Trump Action Tracker list or a CSV file. A longer period may also show
      older articles.
    </EmptyState>
  );
}

/**
 * A square table of category pairs. The diagonal is each category's own count; every other cell is how
 * many articles carry both categories. Shading follows the count, scaled separately for the diagonal
 * and the pairs so the large diagonal doesn't wash the pairs out.
 */
export function Heatmap({ categories, matrix, shortName }: { categories: string[]; matrix: number[][]; shortName: (c: string) => string }) {
  const n = categories.length;
  let maxPair = 0;
  let maxSelf = 0;
  matrix.forEach((row, i) => row.forEach((v, j) => {
    if (i === j) maxSelf = Math.max(maxSelf, v);
    else maxPair = Math.max(maxPair, v);
  }));
  const shade = (v: number, self: boolean) => {
    const top = self ? maxSelf : maxPair;
    return top > 0 ? 0.08 + (v / top) * 0.72 : 0;
  };
  return (
    <div className="policy-heatmap" role="region" aria-label="Category co-occurrence table" tabIndex={0}>
      <table>
        <caption className="visually-hidden">Articles carrying each pair of categories. The diagonal is each category’s own count.</caption>
        <thead>
          <tr>
            <td />
            {categories.map((c) => <th key={c} scope="col" title={c}>{shortName(c)}</th>)}
          </tr>
        </thead>
        <tbody>
          {matrix.slice(0, n).map((row, i) => (
            <tr key={categories[i]}>
              <th scope="row" title={categories[i]}>{shortName(categories[i])}</th>
              {row.slice(0, n).map((v, j) => (
                <td
                  key={j}
                  className={i === j ? 'policy-heatmap__self' : undefined}
                  style={{ ['--heat' as string]: String(shade(v, i === j)) }}
                  title={`${categories[i]} and ${categories[j]}: ${v}`}
                >
                  {v > 0 ? v : ''}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
