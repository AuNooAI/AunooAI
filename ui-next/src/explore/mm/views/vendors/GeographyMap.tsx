import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { Banner, Panel, SegmentedControl, Skeleton, Stack, Table, Text } from '@aunoo/ui';
import { getMarketGeography, type MarketGeography, type MarketGeographyCountry } from '@monolith/marketMonitorApi';
import { errorText } from '../../../../shell';
// Loaded only when the map is shown, so Leaflet stays out of the main Explore bundle
const StreetMap = lazy(() => import('../../../shared/StreetMap'));
import { centroid, formatMusd, fundingCaveat, isUndisclosed, maxValue, radiusFor, valueFor, type Overlay } from './geography';
import './vendors.css';

/*
 * Where the market's vendors are headquartered, and what they've disclosed about funding. Circles
 * sit on a street map (shared/StreetMap, OpenStreetMap tiles) as on the old page, with a plain
 * longitude and latitude grid as the alternative; the table under it gives the exact figures.
 */

const W = 1000;
const LAT_TOP = 75;
const LAT_BOTTOM = -50;
const H = Math.round(((LAT_TOP - LAT_BOTTOM) / 360) * W);
const px = (lng: number) => ((lng + 180) / 360) * W;
const py = (lat: number) => ((LAT_TOP - lat) / (LAT_TOP - LAT_BOTTOM)) * H;

export function GeographyMap({ marketId }: { marketId: number }) {
  const [data, setData] = useState<MarketGeography | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [overlay, setOverlay] = useState<Overlay>('concentration');
  // The street map is the main view; the plain grid stays for a quick look without map tiles
  const [view, setView] = useState<'map' | 'grid'>('map');

  useEffect(() => {
    let live = true;
    setData(undefined);
    setError(null);
    getMarketGeography(marketId).then((d) => live && setData(d), (e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [marketId]);

  const rows = useMemo(() => data?.countries ?? [], [data]);
  const max = useMemo(() => maxValue(rows, overlay), [rows, overlay]);
  // Biggest first, so small circles are drawn on top and stay clickable
  const placed = useMemo(
    () => rows.filter((r) => centroid(r.country)).sort((a, b) => (valueFor(b, overlay) ?? 0) - (valueFor(a, overlay) ?? 0)),
    [rows, overlay],
  );
  const unplaced = rows.filter((r) => !centroid(r.country));
  const undisclosed = rows.filter((r) => r.total_musd === null);

  // The entity layer is switched off on this site: the old page showed nothing either
  if (data === null) return null;

  return (
    <Panel title="Vendor geography" description="Where the market’s vendors are headquartered, and what they have disclosed about funding.">
      {error ? <Banner tone="error" title="The map didn’t load" description={error} /> : data === undefined ? <Skeleton variant="block" size="card" /> : !rows.length ? (
        <Text>No vendor has a resolved country yet.</Text>
      ) : (
        <Stack gap="md">
          <Stack direction="row" justify="between" gap="sm">
            <SegmentedControl
              label="What the circles show"
              value={overlay}
              onValueChange={(v) => setOverlay(v as Overlay)}
              options={[{ value: 'concentration', label: 'Where vendors are' }, { value: 'funding', label: 'Disclosed funding' }]}
            />
            <SegmentedControl
              label="Map style"
              value={view}
              onValueChange={(v) => setView(v as 'map' | 'grid')}
              options={[{ value: 'map', label: 'Street map' }, { value: 'grid', label: 'Plain grid' }]}
            />
            <Text variant="caption">
              {data.vendors_placed} of {data.vendors_total} vendors placed{data.vendors_without_country > 0 ? `, ${data.vendors_without_country} without a country` : ''}
            </Text>
          </Stack>
          {view === 'map' ? (
            <Suspense fallback={<Skeleton variant="block" size="card" />}>
            <StreetMap
              title={`Vendor ${overlay === 'concentration' ? 'counts' : 'disclosed funding'} by country`}
              points={placed.map((r) => {
                const [lat, lng] = centroid(r.country)!;
                const grey = isUndisclosed(r, overlay);
                return {
                  id: r.country,
                  lat,
                  lon: lng,
                  radius: radiusFor(grey ? null : valueFor(r, overlay), max),
                  // A country where nobody disclosed an amount is its own grey, dashed circle, never a small or zero one
                  color: grey ? 'var(--viz-neutral)' : overlay === 'funding' ? 'var(--viz-series-2)' : 'var(--viz-series-1)',
                  dashed: grey,
                  label: grey ? `${r.country}: not disclosed` : r.country,
                  detail: `${r.vendors} vendor${r.vendors === 1 ? '' : 's'}; funding ${formatMusd(r.total_musd)} (${fundingCaveat(r)})`,
                };
              })}
              height="380px"
            />
            </Suspense>
          ) : (
          <svg className="mm-geo" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Vendor ${overlay === 'concentration' ? 'counts' : 'disclosed funding'} by country`}>
            {[-150, -120, -90, -60, -30, 0, 30, 60, 90, 120, 150].map((lng) => <line key={`x${lng}`} className="mm-geo__grid" x1={px(lng)} x2={px(lng)} y1={0} y2={H} />)}
            {[60, 30, 0, -30].map((lat) => <line key={`y${lat}`} className="mm-geo__grid" x1={0} x2={W} y1={py(lat)} y2={py(lat)} />)}
            {placed.map((r) => {
              const [lat, lng] = centroid(r.country)!;
              const grey = isUndisclosed(r, overlay);
              const radius = radiusFor(grey ? null : valueFor(r, overlay), max);
              const cls = grey ? 'mm-geo__bubble mm-geo__bubble--undisclosed' : overlay === 'funding' ? 'mm-geo__bubble mm-geo__bubble--funding' : 'mm-geo__bubble';
              return (
                <g key={r.country}>
                  <circle className={cls} cx={px(lng)} cy={py(lat)} r={radius}>
                    <title>{`${r.country}: ${r.vendors} vendor${r.vendors === 1 ? '' : 's'}; funding ${formatMusd(r.total_musd)} (${fundingCaveat(r)})`}</title>
                  </circle>
                  <text className="mm-geo__label" x={px(lng) + radius + 4} y={py(lat) + 4}>{r.country}</text>
                </g>
              );
            })}
          </svg>
          )}
          <Text variant="caption">
            Circle area is proportional to {overlay === 'concentration' ? 'the number of vendors' : 'disclosed funding'}. Circles sit at the middle of each country,
            because the data records a country, not a city.
          </Text>
          {overlay === 'funding' && undisclosed.length > 0 && (
            <Text variant="caption">
              Dashed grey means no vendor in that country has published an amount, which is not the same as no funding: {undisclosed.map((r) => r.country).join(', ')}.
            </Text>
          )}
          {unplaced.length > 0 && (
            <Banner tone="warning" title="Some countries aren’t on the map" description={`No map position on file for: ${unplaced.map((r) => `${r.country} (${r.vendors})`).join(', ')}. They are in the table below.`} />
          )}
          <Table<MarketGeographyCountry>
            caption="Vendors and disclosed funding by country"
            hideCaption
            scroll
            rows={[...rows].sort((a, b) => b.vendors - a.vendors)}
            rowKey={(r) => r.country}
            columns={[
              { key: 'country', header: 'Country', rowHeader: true },
              { key: 'vendors', header: 'Vendors', align: 'end' },
              { key: 'total_musd', header: 'Disclosed funding', align: 'end', render: (r) => formatMusd(r.total_musd) },
              { key: 'covers', header: 'What the total covers', wrap: true, render: (r) => fundingCaveat(r) },
              { key: 'staff', header: 'Staff (known headcounts)', align: 'end', render: (r) => (r.staff != null ? r.staff.toLocaleString() : '—') },
            ]}
          />
        </Stack>
      )}
    </Panel>
  );
}
