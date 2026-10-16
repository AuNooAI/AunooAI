import { Panel, Sparkline, Stack, Table, Text } from '@aunoo/ui';
import type { BWAllAppRatings, BWAppRating } from '@monolith/brandWatcherApi';

/*
 * App ratings for every brand (GET /app-ratings), as the old AppRatingsComparison: Google Play's
 * own rating, and for both stores the 30-day average of the reviews we collected, with its count.
 */

type Row = BWAllAppRatings['brands'][number];

function StoreCell({ a, storeRated }: { a: BWAppRating | undefined; storeRated: boolean }) {
  if (!a) return <Text variant="caption" as="span">Not tracked</Text>;
  const c = a.collected;
  const weeks = (c?.weekly ?? []).filter((w) => w.avg != null);
  return (
    <Stack gap="sm">
      {storeRated && a.rating != null && <Text variant="label" as="span">{a.rating.toFixed(2)} stars on the store</Text>}
      <Text variant="caption" as="span">
        {c?.avg_30d != null ? `${c.avg_30d.toFixed(2)} stars` : 'No reviews'} from {c?.n_30d ?? 0} reviews in 30 days
        {(c?.n_30d ?? 0) > 0 && (c?.n_30d ?? 0) < 5 ? ' (too few to read much into)' : ''}
      </Text>
      {weeks.length >= 2 && (
        <Sparkline
          label={`Weekly average of collected reviews over ${weeks.length} weeks with reviews, latest ${weeks[weeks.length - 1].avg?.toFixed(2)} stars`}
          values={weeks.map((w) => w.avg as number)}
        />
      )}
    </Stack>
  );
}

export function AppRatingsComparison({ brands }: { brands: Row[] }) {
  const pick = (b: Row, store: string) => b.apps.find((a) => a.store === store);
  const play = (b: Row) => pick(b, 'google_play')?.rating ?? -1;
  const rows = [...brands].sort((a, b) => (a.is_primary === b.is_primary ? play(b) - play(a) : a.is_primary ? -1 : 1));
  return (
    <Panel title="App ratings" description="The store rating comes from Google Play; the App Store gives none. The 30-day averages come from the reviews we collected." headingLevel={3}>
      <Table<Row>
        caption="App ratings by brand"
        hideCaption
        rows={rows}
        rowKey={(b) => String(b.brand_id)}
        columns={[
          { key: 'brand', header: 'Brand', rowHeader: true, render: (b) => `${b.brand_name}${b.is_primary ? ' (primary)' : ''}` },
          { key: 'play', header: 'Android (Google Play)', wrap: true, render: (b) => <StoreCell a={pick(b, 'google_play')} storeRated /> },
          { key: 'ios', header: 'iPhone (App Store)', wrap: true, render: (b) => <StoreCell a={pick(b, 'app_store')} storeRated={false} /> },
          {
            key: 'low', header: '1–2 stars in 30 days', align: 'end',
            render: (b) => {
              const low = b.apps.reduce((t, a) => t + (a.collected?.stars_30d?.['1'] ?? 0) + (a.collected?.stars_30d?.['2'] ?? 0), 0);
              const n = b.apps.reduce((t, a) => t + (a.collected?.n_30d ?? 0), 0);
              return `${low} of ${n}${n >= 10 ? ` (${Math.round((100 * low) / n)}%)` : ''}`;
            },
          },
        ]}
      />
    </Panel>
  );
}
