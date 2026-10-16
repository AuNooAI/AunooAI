import { useState } from 'react';
import { Button, Chip, Stack, Text } from '@aunoo/ui';
import type { Comparison, Facets as FacetMap } from './api';
import { token } from './query';

/*
 * What the results are made of (the old page's Active Filters panel): the counts per topic,
 * category, source, driver and sentiment. Clicking a value adds it as a filter, clicking it again
 * removes it. The filter impact line says how many results the filters kept.
 */

const LABEL: Record<string, string> = { topic: 'Topic', category: 'Category', news_source: 'Source', driver_type: 'Driver', sentiment: 'Sentiment' };

function Group({ field, values, query, onToggle }: { field: string; values: Record<string, number>; query: string; onToggle: (t: string) => void }) {
  const [all, setAll] = useState(false);
  const entries = Object.entries(values).sort((a, b) => b[1] - a[1]);
  const shown = all ? entries : entries.slice(0, 10);
  return (
    <Stack gap="sm">
      <Text variant="label">{LABEL[field] ?? field}</Text>
      <Stack direction="row" gap="sm">
        {shown.map(([v, n]) => {
          const t = token(field, v);
          const on = query.includes(t);
          return (
            <Chip key={v} tone={on ? 'accent' : 'neutral'} label={on ? `Remove the filter ${t}` : `Add the filter ${t}`} onClick={() => onToggle(t)}>
              {`${v} (${n})`}
            </Chip>
          );
        })}
      </Stack>
      {entries.length > 10 && <div><Button variant="ghost" size="sm" onClick={() => setAll((a) => !a)}>{all ? 'Show fewer' : `Show ${entries.length - 10} more`}</Button></div>}
    </Stack>
  );
}

export function Facets({ facets, comparison, query, onToggle }: { facets: FacetMap; comparison?: Comparison | null; query: string; onToggle: (t: string) => void }) {
  const fields = Object.keys(facets).filter((f) => Object.keys(facets[f] ?? {}).length);
  const impact = comparison && comparison.total_before ? comparison : null;
  const kept = impact ? Math.round((impact.total_after / impact.total_before) * 100) : null;
  const moved = impact
    ? Object.entries(impact.facet_impact ?? {}).flatMap(([f, vals]) => Object.entries(vals).map(([v, i]) => ({ f, v, d: i.diff }))).filter((x) => x.d !== 0).sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(0, 5)
    : [];
  return (
    <Stack gap="md">
      {impact && (
        <Stack gap="sm">
          <Text variant="label">{`Your filters kept ${impact.total_after.toLocaleString()} of ${impact.total_before.toLocaleString()} results (${kept}%)`}</Text>
          {moved.length > 0 && <Text variant="caption">{`Biggest changes: ${moved.map((x) => `${x.v} ${x.d > 0 ? '+' : ''}${x.d}`).join(', ')}`}</Text>}
        </Stack>
      )}
      {!fields.length ? <Text variant="caption">Nothing to break down yet.</Text> : fields.map((f) => <Group key={f} field={f} values={facets[f]} query={query} onToggle={onToggle} />)}
    </Stack>
  );
}
