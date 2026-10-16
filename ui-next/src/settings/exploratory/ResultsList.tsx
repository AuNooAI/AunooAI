import { ArticleCard, Button, Checkbox, Chip, Stack, Text } from '@aunoo/ui';
import type { SearchHit } from './api';
import './exploratory.css';

/*
 * The results, 20 at a time (the old page's paging), each with a tick box for the AI summary of the
 * selection. Clicking a title opens the article's details.
 */

export const PAGE = 20;

function fmtDate(v: unknown) {
  if (!v) return null;
  const d = new Date(String(v));
  return Number.isNaN(d.getTime()) ? null : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

/** Time to impact by urgency, as the old page coloured its badges (immediate red, short-term amber, mid-term blue) */
const timeTone = (v: string) => (/immediate/i.test(v) ? 'error' : /short/i.test(v) ? 'warning' : /mid/i.test(v) ? 'info' : 'muted');

export function ResultsList({ hits, shown, onMore, selected, onToggle, onOpen, compact, onFilter }: {
  hits: SearchHit[];
  shown: number;
  onMore: () => void;
  selected: Set<string>;
  onToggle: (id: string, on: boolean) => void;
  onOpen: (h: SearchHit) => void;
  compact: boolean;
  /** A card's badge was clicked: filter the results by that field and value (the old badges did this) */
  onFilter?: (field: string, value: string) => void;
}) {
  if (!hits.length) return <Text>Nothing matched. Try fewer filters or other words.</Text>;
  return (
    <Stack gap="sm">
      <Stack as="ul" gap="sm" label="Results">
        {hits.slice(0, shown).map((h) => {
          const m = h.metadata ?? {};
          const title = m.title || 'Untitled';
          return (
            <ArticleCard
              key={h.id}
              as="li"
              variant={compact ? 'row' : 'card'}
              leading={<Checkbox label={`Select “${title}”`} hideLabel checked={selected.has(h.id)} onCheckedChange={(on) => onToggle(h.id, on)} />}
              title={<button type="button" className="text-link xa-link" onClick={() => onOpen(h)}>{title}</button>}
              meta={[m.news_source, fmtDate(m.publication_date), h.score ? `distance ${h.score.toFixed(3)} (lower is closer)` : null].filter(Boolean).join(' · ')}
              summary={compact ? undefined : (m.summary ? String(m.summary).slice(0, 260) + (String(m.summary).length > 260 ? '…' : '') : undefined)}
              tags={compact ? undefined : (
                <>
                  {([
                    ['category', 'Category', m.category, 'muted'],
                    ['sentiment', 'Sentiment', m.sentiment, m.sentiment ? (/pos/i.test(String(m.sentiment)) ? 'success' : /neg|crit/i.test(String(m.sentiment)) ? 'error' : 'muted') : 'muted'],
                    ['time_to_impact', 'Time to impact', m.time_to_impact, m.time_to_impact ? timeTone(String(m.time_to_impact)) : 'muted'],
                    ['future_signal', 'Future signal', m.future_signal, 'info'],
                    ['driver_type', 'Driver type', m.driver_type, 'muted'],
                  ] as const).filter(([, , v]) => v).map(([field, name, v, tone]) => (
                    <Chip
                      key={field}
                      size="sm"
                      tone={tone as 'muted' | 'success' | 'error' | 'warning' | 'info'}
                      label={onFilter ? `${name}: ${String(v)}. Filter the results by it` : `${name}: ${String(v)}`}
                      onClick={onFilter ? () => onFilter(field, String(v)) : undefined}
                    >
                      {String(v)}
                    </Chip>
                  ))}
                </>
              )}
            />
          );
        })}
      </Stack>
      {shown < hits.length && <div><Button variant="secondary" onClick={onMore}>{`Show ${Math.min(PAGE, hits.length - shown)} more of ${hits.length - shown}`}</Button></div>}
    </Stack>
  );
}
