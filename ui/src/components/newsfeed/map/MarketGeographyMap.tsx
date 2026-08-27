/**
 * Where a market's vendors are, and what is disclosed about their funding.
 *
 * Two overlays over the same circles. **Concentration** counts companies per
 * country and is complete — every vendor has a resolved country, so a five is
 * a five. **Disclosed funding** is not complete, and the map says so rather
 * than implying otherwise: a country where nobody published an amount is drawn
 * in its own grey and labelled "not disclosed", never as a small circle or a
 * zero. India's five vendors are all undisclosed; on a naive funding map they
 * would look like the least-funded place on earth.
 *
 * Circles are placed at country centroids because the data is country-level.
 * Anything finer would be invented precision.
 */

import { useEffect, useMemo, useState } from 'react';
import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet';
import { useTheme } from 'next-themes';
import 'leaflet/dist/leaflet.css';

import { getMarketGeography } from '../../../services/marketMonitorApi';
import {
  centroid, colorFor, formatMusd, fundingCaveat, maxValue, radiusFor,
  unplaceable, valueFor, isUndisclosed, UNDISCLOSED_COLOR,
  type CountryRow, type Overlay,
} from './marketGeography';

// Leaflet tiles versus Tailwind's image reset. Without this the tiles are
// scaled to the container and the map renders as a smear; the existing
// hotspot map carries the same fix.
if (typeof document !== 'undefined'
    && !document.getElementById('leaflet-tailwind-fix-v2')) {
  const fix = document.createElement('style');
  fix.id = 'leaflet-tailwind-fix-v2';
  fix.textContent = `
    .leaflet-pane > img, img.leaflet-tile,
    .leaflet-container .leaflet-tile-pane img {
      max-width: none !important; max-height: none !important;
    }
    .leaflet-tile-pane .leaflet-tile { position: absolute !important; }`;
  document.body.appendChild(fix);
}

const ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
  + 'contributors';

// CARTO's basemaps started requiring an API key and stamp "API KEY REQUIRED"
// across every tile without one, which is what this map showed. OpenStreetMap's
// own tiles need no key. They have no dark variant, so dark mode inverts the
// tile pane in CSS — the markers sit in a separate pane and keep their colour.
const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const DARK_TILE_CSS = `
    .market-map-dark .leaflet-tile-pane {
      filter: invert(1) hue-rotate(180deg) brightness(0.85) contrast(0.9);
    }`;

export function MarketGeographyMap({ marketId }: { marketId: number }) {
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === 'dark';
  const [rows, setRows] = useState<CountryRow[]>([]);
  const [meta, setMeta] = useState<{ placed: number; total: number;
                                     missing: number } | null>(null);
  const [overlay, setOverlay] = useState<Overlay>('concentration');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getMarketGeography(marketId).then((data) => {
      if (cancelled || data === null) return;
      setRows(data.countries);
      setMeta({ placed: data.vendors_placed, total: data.vendors_total,
                missing: data.vendors_without_country });
    }).catch((e: unknown) => {
      if (!cancelled) setError(e instanceof Error ? e.message : String(e));
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [marketId]);

  const max = useMemo(() => maxValue(rows, overlay), [rows, overlay]);
  const missingFromMap = useMemo(() => unplaceable(rows), [rows]);
  const undisclosed = useMemo(
    () => rows.filter(r => r.total_musd === null), [rows]);

  if (loading) {
    return <Shell><p className="text-sm text-slate-500 py-10 text-center
      dark:text-gray-400">Loading map…</p></Shell>;
  }
  if (error) {
    return <Shell><p className="text-sm text-amber-600 py-10 text-center
      dark:text-amber-400">Could not load the map: {error}</p></Shell>;
  }
  if (!rows.length) {
    return <Shell><p className="text-sm text-slate-500 py-10 text-center
      dark:text-gray-400">No vendor has a resolved country yet.</p></Shell>;
  }


  return (
    <Shell>
      <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
        <div className="inline-flex rounded-md border overflow-hidden
                        dark:border-gray-700">
          {(['concentration', 'funding'] as Overlay[]).map(key => (
            <button
              key={key}
              onClick={() => setOverlay(key)}
              className={`px-3 py-1.5 text-sm ${overlay === key
                ? 'bg-slate-800 text-white dark:bg-gray-600'
                : 'bg-white text-slate-600 dark:bg-gray-800 dark:text-gray-300'}`}
            >
              {key === 'concentration' ? 'Where vendors are'
                                       : 'Disclosed funding'}
            </button>
          ))}
        </div>
        {meta && (
          <p className="text-xs text-slate-500 dark:text-gray-400">
            {meta.placed} of {meta.total} vendors placed
            {meta.missing > 0 && `, ${meta.missing} without a country`}
          </p>
        )}
      </div>

      <div className="h-[420px] rounded-lg overflow-hidden border
                      dark:border-gray-700">
        {/* minZoom matches zoom: below it the world does not fill the
            container and Leaflet renders a grey band across the top. */}
        <MapContainer center={[25, 5]} zoom={2} minZoom={2} zoomSnap={0.5}
                      scrollWheelZoom={false} worldCopyJump
                      className={dark ? 'market-map-dark' : undefined}
                      style={{ height: '100%', width: '100%' }}>
          {dark && <style>{DARK_TILE_CSS}</style>}
          <TileLayer url={TILE_URL} attribution={ATTRIBUTION} />
          {rows.map((row) => {
            const at = centroid(row.country);
            if (!at) return null;
            const value = valueFor(row, overlay);
            const grey = isUndisclosed(row, overlay);
            return (
              <CircleMarker
                key={row.country}
                center={at}
                radius={radiusFor(grey ? null : value, max)}
                pathOptions={{
                  color: colorFor(row, overlay, max),
                  fillColor: colorFor(row, overlay, max),
                  fillOpacity: grey ? 0.25 : 0.55,
                  weight: grey ? 1 : 2,
                  // A dashed outline marks "we have no figure" so it cannot be
                  // mistaken for a genuinely small amount.
                  dashArray: grey ? '4 3' : undefined,
                }}
              >
                <Popup>
                  <div className="text-sm">
                    <div className="font-medium">{row.country}</div>
                    <div>{row.vendors} vendor{row.vendors === 1 ? '' : 's'}</div>
                    <div className="mt-1">
                      Funding: {formatMusd(row.total_musd)}
                    </div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      {fundingCaveat(row)}
                    </div>
                    {row.staff != null && (
                      <div className="text-xs text-slate-500 mt-1">
                        {row.staff.toLocaleString()} staff across vendors with a
                        known headcount
                      </div>
                    )}
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}
        </MapContainer>
      </div>

      <div className="mt-3 text-xs text-slate-500 dark:text-gray-400 space-y-1">
        <p>
          Circle area is proportional to{' '}
          {overlay === 'concentration' ? 'the number of vendors'
                                       : 'disclosed funding'}. Placement is at
          country centroids — the data records a country, not a city.
        </p>
        {overlay === 'funding' && undisclosed.length > 0 && (
          <p>
            <span className="inline-block w-3 h-3 rounded-full align-middle mr-1
                             border border-dashed"
                  style={{ background: UNDISCLOSED_COLOR, opacity: 0.4 }} />
            Dashed grey means no vendor in that country has published an
            amount, which is not the same as no funding:{' '}
            {undisclosed.map(r => r.country).join(', ')}.
          </p>
        )}
        {missingFromMap.length > 0 && (
          <p className="text-amber-600 dark:text-amber-400">
            Not shown, no centroid on file:{' '}
            {missingFromMap.map(r => `${r.country} (${r.vendors})`).join(', ')}.
          </p>
        )}
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
      <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
        Vendor geography
      </div>
      <p className="text-xs text-slate-500 mt-0.5 dark:text-gray-400">
        Where the market's vendors are headquartered, and what they have
        disclosed about funding.
      </p>
      <div className="mt-3">{children}</div>
    </div>
  );
}
