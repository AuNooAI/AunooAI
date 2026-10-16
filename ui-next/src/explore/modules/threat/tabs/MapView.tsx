import { lazy, Suspense, useState } from 'react';
import { EmptyState, FilterChipRow, Panel, SegmentedControl, Skeleton, Stack, Switch, Table, Text } from '@aunoo/ui';
import type { SeverityLevel } from '../api';
import type { ThreatCtx } from '../context';
import { categoryLabel, SEVERITY_LABELS, SEVERITY_LEVELS, THREAT_CATEGORIES } from '../labels';
import { LinkButton, SeverityChip } from '../parts';
import { ThreatMap } from './ThreatMap';

// Loaded only when shown, so Leaflet stays out of the main Explore bundle
const StreetMap = lazy(() => import('../../../shared/StreetMap'));
const SEVERITY_VAR: Record<string, string> = { critical: 'var(--error)', high: 'var(--warning)', medium: 'var(--warning)', low: 'var(--success)', info: 'var(--info)' };
const RADIUS: Record<string, number> = { critical: 11, high: 10, medium: 8, low: 7, info: 7 };
const VIEW_KEY = 'aunoo.threat.mapView';
const loadView = (): 'street' | 'grid' => {
  try {
    return localStorage.getItem(VIEW_KEY) === 'grid' ? 'grid' : 'street';
  } catch {
    return 'street';
  }
};

/*
 * Where threats are aimed, as the old ThreatMapTab, filtered by severity and type. Only threats the AI
 * gave a target location appear; the count says how many that is. A street map with nearby threats
 * grouped (the old page's Leaflet map), or the plain grid; the choice is remembered in this browser.
 */
export function MapView({ ctx, types, severities, onTypes, onSeverities }: {
  ctx: ThreatCtx;
  types: string[];
  severities: SeverityLevel[];
  onTypes: (t: string[]) => void;
  onSeverities: (s: SeverityLevel[]) => void;
}) {
  const [labels, setLabels] = useState(false);
  const [view, setView] = useState<'street' | 'grid'>(loadView);
  const pickView = (v: string) => {
    setView(v as 'street' | 'grid');
    try {
      localStorage.setItem(VIEW_KEY, v);
    } catch {
      // per visit only
    }
  };
  const threats = ctx.mapThreats;
  const pick = (t: { id: number; threat_name: string }) => ctx.showArticles({ threat: { id: t.id, name: t.threat_name } });
  const total = ctx.stats?.total_threats;

  return (
    <Panel
      title="Threat map"
      description={`${threats.length} threat${threats.length === 1 ? '' : 's'} with a target location${total !== undefined && !types.length && !severities.length ? ` out of ${total} in this period; the rest have no location recorded` : ''}. Pick a dot to read its articles.`}
    >
      <Stack gap="md">
        <FilterChipRow label="Severity" options={SEVERITY_LEVELS.map((l) => ({ value: l, label: SEVERITY_LABELS[l] }))} selected={severities} onChange={(v) => onSeverities(v as SeverityLevel[])} />
        <FilterChipRow label="Threat type" options={THREAT_CATEGORIES.map((c) => ({ value: c, label: categoryLabel(c) }))} selected={types} onChange={onTypes} maxVisible={8} />
        <SegmentedControl label="Map style" options={[{ value: 'street', label: 'Street map', icon: 'Globe' }, { value: 'grid', label: 'Plain grid', icon: 'SquaresFour' }]} value={view} onValueChange={pickView} />
        {view === 'grid' && <Switch label="Show names on the map" checked={labels} onCheckedChange={setLabels} />}
        {ctx.loading && !threats.length ? <Skeleton variant="block" size="card" /> : !threats.length ? (
          <EmptyState icon="Globe" title="Nothing to place">No threat in this period and these filters has a target location.</EmptyState>
        ) : (
          <>
            {view === 'grid' ? <ThreatMap threats={threats} showLabels={labels} onPick={pick} /> : (
              <Suspense fallback={<Skeleton variant="block" size="card" />}>
                <StreetMap
                  title="Threats by target location"
                  cluster
                  points={threats.map((t) => ({
                    id: String(t.id),
                    lat: t.latitude,
                    lon: t.longitude,
                    radius: RADIUS[t.severity_level] ?? 7,
                    color: SEVERITY_VAR[t.severity_level],
                    label: t.threat_name,
                    detail: `${SEVERITY_LABELS[t.severity_level as SeverityLevel] ?? t.severity_level} · ${categoryLabel(t.threat_type)} · ${t.article_count} article${t.article_count === 1 ? '' : 's'}${t.target_countries?.length ? ` · ${t.target_countries.join(', ')}` : ''}`,
                    onSelect: () => pick(t),
                  }))}
                />
              </Suspense>
            )}
            <Text variant="caption">
              {view === 'grid'
                ? 'Dot colour shows severity: red critical, amber high, then medium, green low and blue information only. A ring of dots means several threats recorded at the same place.'
                : 'Dot colour shows severity: red critical, amber high and medium, green low, blue information only. Threats close together are grouped into a numbered circle; zoom in to separate them. Click a dot to read its articles.'}
            </Text>
            <Table
              caption="Threats on the map"
              hideCaption
              rows={threats}
              rowKey={(t) => String(t.id)}
              columns={[
                { key: 'threat_name', header: 'Threat', rowHeader: true, wrap: true, render: (t) => <LinkButton onClick={() => pick(t)}>{t.threat_name}</LinkButton> },
                { key: 'severity_level', header: 'Severity', render: (t) => <SeverityChip level={t.severity_level} /> },
                { key: 'threat_type', header: 'Type', render: (t) => categoryLabel(t.threat_type) },
                { key: 'where', header: 'Targets', wrap: true, render: (t) => t.target_countries?.join(', ') || `${t.latitude.toFixed(1)}, ${t.longitude.toFixed(1)}` },
                { key: 'article_count', header: 'Articles', align: 'end' },
              ]}
            />
          </>
        )}
      </Stack>
    </Panel>
  );
}
