import { useMemo, useState } from 'react';
import { FilterChipRow, Panel, Skeleton, Stack, Table, Text } from '@aunoo/ui';
import type { Hotspot, RiskLevel, ThreatCategory } from '@monolith/geopoliticalHotspotsApi';
import { MapViews } from '../MapViews';
import { CATEGORIES, RISK_LABEL, RISK_ORDER, TREND_LABEL, cap, fmtDate } from '../labels';
import '../geo.css';

/*
 * The whole map with its filters, as the old Global view: street map, 3D globe or plain grid. The filters change which
 * hotspots the server returns, for the Overview too. A table under the map lists every hotspot shown,
 * so the figures can be read exactly and sorted.
 */

type SortKey = 'location_name' | 'risk_level' | 'intensity_score' | 'article_count' | 'last_article_date';
const RISK_RANK: Record<RiskLevel, number> = { critical: 4, high: 3, medium: 2, low: 1, info: 0 };

export function GlobalView({ hotspots, categories, riskLevels, onCategories, onRiskLevels, onHotspot }: {
  hotspots: Hotspot[] | null;
  categories: ThreatCategory[];
  riskLevels: RiskLevel[];
  onCategories: (c: ThreatCategory[]) => void;
  onRiskLevels: (r: RiskLevel[]) => void;
  onHotspot: (h: Hotspot) => void;
}) {
  const [sort, setSort] = useState<{ key: SortKey; direction: 'asc' | 'desc' }>({ key: 'intensity_score', direction: 'desc' });
  const [showAll, setShowAll] = useState(false);
  const rows = useMemo(() => {
    const val = (h: Hotspot): string | number =>
      sort.key === 'risk_level' ? RISK_RANK[h.risk_level] : sort.key === 'last_article_date' ? h.last_article_date ?? '' : (h[sort.key] as string | number);
    const out = [...(hotspots ?? [])].sort((a, b) => {
      const x = val(a);
      const y = val(b);
      const c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y));
      return sort.direction === 'asc' ? c : -c;
    });
    return out;
  }, [hotspots, sort]);
  const shown = showAll ? rows : rows.slice(0, 25);

  return (
    <>
      <Panel title="Filters" description="Changes which hotspots appear here and on the Overview.">
        <Stack gap="sm">
          <FilterChipRow label="Risk level" options={RISK_ORDER.map((r) => ({ value: r, label: RISK_LABEL[r] }))} selected={riskLevels} onChange={(v) => onRiskLevels(v as RiskLevel[])} />
          <FilterChipRow label="Category" options={CATEGORIES.map((c) => ({ value: c, label: cap(c) }))} selected={categories} onChange={(v) => onCategories(v as ThreatCategory[])} maxVisible={7} />
        </Stack>
      </Panel>
      <Panel title="Global view" description={hotspots ? `${hotspots.length} hotspots. Click one to see its articles.` : undefined}>
        {!hotspots ? <Skeleton variant="block" size="card" /> : hotspots.length === 0 ? <Text>No hotspots match these filters.</Text> : (
          <Stack gap="md">
            <MapViews hotspots={hotspots} onHotspot={onHotspot} title="Global map of hotspots" labelTop={12} globe />
            <Table<Hotspot>
              caption="Hotspots on the map"
              hideCaption
              scroll
              rows={shown}
              rowKey={(h) => String(h.id)}
              sort={sort}
              onSortChange={(key) => setSort((s) => (s.key === key ? { key, direction: s.direction === 'asc' ? 'desc' : 'asc' } : { key: key as SortKey, direction: key === 'location_name' ? 'asc' : 'desc' }))}
              columns={[
                {
                  key: 'location_name', header: 'Hotspot', rowHeader: true, sortable: true, wrap: true,
                  render: (h) => <button type="button" className="text-link geo-linkbutton" onClick={() => onHotspot(h)}>{h.location_name}</button>,
                },
                { key: 'country_name', header: 'Country', render: (h) => h.country_name ?? '—' },
                { key: 'risk_level', header: 'Risk', sortable: true, render: (h) => RISK_LABEL[h.risk_level] },
                { key: 'trend', header: 'Trend', render: (h) => (h.trend ? TREND_LABEL[h.trend] : '—') },
                { key: 'primary_category', header: 'Category', render: (h) => cap(h.primary_category) || '—' },
                { key: 'intensity_score', header: 'Intensity', align: 'end', sortable: true, render: (h) => Math.round(h.intensity_score) },
                { key: 'article_count', header: 'Articles', align: 'end', sortable: true },
                { key: 'last_article_date', header: 'Latest article', sortable: true, render: (h) => fmtDate(h.last_article_date) || '—' },
              ]}
            />
            {rows.length > 25 && (
              <button type="button" className="text-link geo-linkbutton" onClick={() => setShowAll((s) => !s)}>
                {showAll ? 'Show the first 25' : `Show all ${rows.length} hotspots`}
              </button>
            )}
          </Stack>
        )}
      </Panel>
    </>
  );
}
