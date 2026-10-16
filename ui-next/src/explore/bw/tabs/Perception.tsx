import { useEffect, useMemo, useState } from 'react';
import { Button, Chip, EmptyState, Icon, IconButton, Panel, RadarChart, Select, Skeleton, Stack, Table, Text } from '@aunoo/ui';
import { getPerception, type BWPerceptionBrand } from '@monolith/brandWatcherApi';
import { errorText } from '../../../shell';
import { download } from '../../feed/api';
import type { BwContext } from '../context';
import { periodLabel } from '../context';
import { brandColors, csv, signed, topNOptions } from './analysis/shared';

/*
 * Perception on five surfaces per brand (GET /perception), as the old BrandWatcherPerception.tsx:
 * media, social, community (Reddit), employee (Glassdoor) and investor (Financial Performance news).
 */

type DimKey = 'media' | 'social' | 'community' | 'employee' | 'investor';
const DIMENSIONS: { key: DimKey; label: string; hint: string }[] = [
  { key: 'media', label: 'Media', hint: 'Net sentiment of news coverage in the brand topic.' },
  { key: 'social', label: 'Social', hint: 'Net sentiment of Bluesky, X, Instagram and TikTok posts that mention the brand.' },
  { key: 'community', label: 'Community', hint: 'Net sentiment of Reddit posts and threads that mention the brand.' },
  { key: 'employee', label: 'Employee', hint: 'Glassdoor overall rating scaled to −100…+100, where 3.0 stars is neutral.' },
  { key: 'investor', label: 'Investor', hint: 'Net sentiment of articles in the Financial Performance category.' },
];

type Dim = { score?: number | null; n?: number; positive?: number; neutral?: number; negative?: number; rating?: number | null; outlook?: number | null; review_count?: number | null; reviews_n?: number; reviews_net?: number };
const dimOf = (b: BWPerceptionBrand, k: DimKey) => b.dimensions[k] as unknown as Dim | undefined;

function cellDetail(k: DimKey, d: Dim | undefined): string {
  if (!d) return 'No data in this period';
  if (k === 'employee') {
    const bits = [];
    if (d.rating != null) bits.push(`${d.rating}/5 on Glassdoor`);
    if (d.outlook != null) bits.push(`${Math.round(d.outlook * 100)}% outlook`);
    if (d.reviews_n) bits.push(`${d.reviews_n} reviews, net ${signed(d.reviews_net)}`);
    return bits.length ? bits.join(' · ') : 'Glassdoor not set up for this brand';
  }
  if (!d.n) return 'Nothing in this period';
  return `${d.n} items: ${d.positive} positive, ${d.neutral} neutral, ${d.negative} negative`;
}
const tone = (s: number | null) => (s == null ? 'muted' : s >= 20 ? 'success' : s <= -20 ? 'error' : 'warning');

export function Perception({ bw }: BwContext) {
  const days = bw.config.daysBack;
  const [brands, setBrands] = useState<BWPerceptionBrand[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // null = the default set (the primary plus the top N by volume); once touched, an explicit set
  const [visible, setVisible] = useState<Set<number> | null>(null);
  const [n, setN] = useState(5);

  useEffect(() => {
    let stale = false;
    setBrands(null);
    setError(null);
    getPerception(days).then((d) => !stale && setBrands(d.brands), (e: unknown) => !stale && setError(errorText(e)));
    return () => {
      stale = true;
    };
  }, [days]);
  useEffect(() => setVisible(null), [days, n]);

  const volume = (b: BWPerceptionBrand) =>
    (['media', 'social', 'community', 'investor'] as const).reduce((s, k) => s + (dimOf(b, k)?.n ?? 0), 0) + (dimOf(b, 'employee')?.reviews_n ?? 0);
  const defaults = useMemo(() => {
    const list = brands ?? [];
    const ids = new Set(list.filter((b) => b.is_primary).map((b) => b.brand_id));
    for (const b of [...list].sort((a, c) => volume(c) - volume(a) || a.display_name.localeCompare(c.display_name))) {
      if (ids.size >= n) break;
      ids.add(b.brand_id);
    }
    return ids;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brands, n]);

  if (error) return <Panel title="Perception"><Text tone="error">Perception didn’t load: {error}</Text></Panel>;
  if (!brands) return <Skeleton variant="block" size="chart" />;
  if (!brands.length) return <Panel title="Perception"><EmptyState icon="Target">No brands are set up yet.</EmptyState></Panel>;

  const shownIds = visible ?? defaults;
  const shown = brands.filter((b) => shownIds.has(b.brand_id));
  // Colours follow the full list, so switching a brand off doesn't repaint the others
  const colors = brandColors([...brands].sort((a, b) => Number(b.is_primary) - Number(a.is_primary)).map((b) => b.brand_id));
  const toggle = (id: number) => {
    const next = new Set(shownIds);
    if (next.has(id)) {
      if (next.size > 1) next.delete(id);
    } else next.add(id);
    setVisible(next);
  };

  const exportCsv = () => {
    const lines = ['brand,is_primary,dimension,score,items,positive,neutral,negative,glassdoor_rating,glassdoor_outlook'];
    for (const b of shown) {
      for (const dim of DIMENSIONS) {
        const d = dimOf(b, dim.key);
        lines.push([csv(b.display_name), b.is_primary, dim.label, d?.score ?? '', d?.n ?? 0, d?.positive ?? '', d?.neutral ?? '', d?.negative ?? '',
          dim.key === 'employee' ? d?.rating ?? '' : '', dim.key === 'employee' && d?.outlook != null ? Math.round(d.outlook * 100) : ''].join(','));
      }
    }
    download(`perception-scores-${new Date().toISOString().slice(0, 10)}.csv`, lines.join('\n'), 'text/csv');
  };

  return (
    <>
      <Panel
        title="Perception on five surfaces"
        description={`How each brand is seen in ${periodLabel(days)}. Scores are net sentiment from −100 to +100; the employee score scales the Glassdoor rating.`}
        headerAside={<Select label="Brands shown" hideLabel options={topNOptions(brands.length)} value={String(n)} onValueChange={(v) => setN(Number(v))} />}
      >
        <Stack gap="md">
          <Stack direction="row" gap="sm" label="Brands on the chart">
            {brands.map((b) => {
              const on = shownIds.has(b.brand_id);
              return (
                <Chip key={b.brand_id} tone={on ? 'accent' : 'muted'} variant={on ? 'fill' : 'outline'} onClick={() => toggle(b.brand_id)} label={`${on ? 'Hide' : 'Show'} ${b.display_name}`}
                  icon={on ? <Icon name="Check" size="sm" /> : undefined}>
                  {b.display_name}{b.is_primary ? ' (primary)' : ''}
                </Chip>
              );
            })}
            {visible && <Button variant="ghost" size="sm" onClick={() => setVisible(null)}>Reset</Button>}
          </Stack>
          <RadarChart
            title="Perception radar"
            axes={DIMENSIONS.map((d) => d.label)}
            // The radar runs 0–100 so all five axes share a scale: 50 is neutral
            series={shown.map((b) => ({
              id: String(b.brand_id),
              label: b.display_name,
              color: colors.get(b.brand_id) ?? 0,
              values: DIMENSIONS.map((d) => {
                const s = dimOf(b, d.key)?.score;
                return s == null ? 50 : Math.round((s + 100) / 2);
              }),
            }))}
            formatValue={(v) => `net ${signed(v * 2 - 100)}`}
            emptyText="No perception data in this period."
          />
          <Text variant="caption">On the radar, 50 is neutral; a surface with no data is drawn at 50. The table shows which surfaces have no data.</Text>
        </Stack>
      </Panel>

      <Panel
        title="Scores by surface"
        description="Net sentiment is (positive − negative) ÷ scored × 100 over items that clearly concern the brand. Small counts make scores jumpy: a +100 from two posts means little."
        headerAside={<IconButton icon={<Icon name="DownloadSimple" size="sm" />} label="Download scores as CSV" onClick={exportCsv} />}
      >
        <Table<BWPerceptionBrand>
          caption="Perception scores by surface"
          hideCaption
          rows={shown}
          rowKey={(b) => String(b.brand_id)}
          columns={[
            { key: 'brand', header: 'Brand', rowHeader: true, render: (b) => `${b.display_name}${b.is_primary ? ' (primary)' : ''}` },
            ...DIMENSIONS.map((dim) => ({
              key: dim.key,
              header: dim.label,
              render: (b: BWPerceptionBrand) => {
                const d = dimOf(b, dim.key);
                const s = d?.score ?? null;
                return (
                  <Stack gap="sm">
                    <Chip size="sm" tone={tone(s)}>{s == null ? 'No data' : signed(s)}</Chip>
                    <Text variant="caption" as="span">{cellDetail(dim.key, d)}</Text>
                  </Stack>
                );
              },
            })),
          ]}
        />
        <Stack as="ul" gap="sm" label="What each surface measures">
          {DIMENSIONS.map((d) => <li key={d.key}><Text variant="caption"><strong>{d.label}:</strong> {d.hint}</Text></li>)}
        </Stack>
      </Panel>
    </>
  );
}
