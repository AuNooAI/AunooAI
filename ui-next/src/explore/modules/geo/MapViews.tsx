import { Component, lazy, Suspense, useState, type ReactNode } from 'react';
import { Banner, SegmentedControl, Skeleton, Stack } from '@aunoo/ui';
import type { Hotspot } from '@monolith/geopoliticalHotspotsApi';
import { HotspotMap } from './HotspotMap';
import { RISK_LABEL, RISK_ORDER, cap } from './labels';
import './geo.css';

/*
 * The hotspots as a street map (the default, as the old page's Leaflet map), a 3D globe (Global view
 * only, as the old page) or the plain grid. The street map and globe load only when shown, so their
 * libraries stay out of the main Explore bundle. The choice is remembered in this browser.
 */

const StreetMap = lazy(() => import('../../shared/StreetMap'));
const GeoGlobe = lazy(() => import('./GeoGlobe'));

/** The globe needs WebGL, which some machines (remote desktops, locked-down laptops) don't offer */
function webglAvailable(): boolean {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl2') || c.getContext('webgl'));
  } catch {
    return false;
  }
}

/** If the globe still fails to start, fall back to the street map instead of blanking the page */
class GlobeBoundary extends Component<{ onFail: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onFail();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

type View = 'street' | 'globe' | 'grid';
const KEY = 'aunoo.geo.mapView';
const RISK_VAR: Record<string, string> = { critical: 'var(--error)', high: 'var(--warning)', medium: 'var(--warning)', low: 'var(--success)', info: 'var(--info)' };
const radius = (intensity: number) => 5 + (Math.max(0, Math.min(100, intensity)) / 100) * 11;

function load(globe: boolean): View {
  try {
    const v = localStorage.getItem(KEY);
    if (v === 'street' || v === 'grid' || (v === 'globe' && globe)) return v;
  } catch {
    // per visit only
  }
  return 'street';
}

export function MapViews({ hotspots, onHotspot, title, labelTop = 0, globe = false }: {
  hotspots: Hotspot[];
  onHotspot?: (h: Hotspot) => void;
  title: string;
  labelTop?: number;
  /** Offer the 3D globe (the Global view) */
  globe?: boolean;
}) {
  const [globeOk, setGlobeOk] = useState(() => globe && webglAvailable());
  const [view, setView] = useState<View>(() => {
    const v = load(globe);
    return v === 'globe' && !webglAvailable() ? 'street' : v;
  });
  const [globeFailed, setGlobeFailed] = useState(false);
  const pick = (v: string) => {
    setView(v as View);
    try {
      localStorage.setItem(KEY, v);
    } catch {
      // per visit only
    }
  };
  const placed = hotspots.filter((h) => Number.isFinite(h.latitude) && Number.isFinite(h.longitude));
  const counts = RISK_ORDER.map((r) => ({ r, n: placed.filter((h) => h.risk_level === r).length })).filter((x) => x.n > 0);

  return (
    <Stack gap="sm">
      <SegmentedControl
        label="Map style"
        options={[{ value: 'street', label: 'Street map', icon: 'Globe' }, ...(globeOk ? [{ value: 'globe', label: '3D globe', icon: 'Globe' as const }] : []), { value: 'grid', label: 'Plain grid', icon: 'SquaresFour' }]}
        value={view}
        onValueChange={pick}
      />
      {globeFailed && <Banner tone="info" title="The 3D globe couldn’t start" description="This browser didn’t allow the 3D graphics it needs, so the street map is shown instead." />}
      {view === 'grid' ? <HotspotMap hotspots={hotspots} onHotspot={onHotspot} title={title} labelTop={labelTop} /> : (
        <Suspense fallback={<Skeleton variant="block" size="card" />}>
          {view === 'globe' ? (
            <GlobeBoundary onFail={() => { setGlobeFailed(true); setGlobeOk(false); setView('street'); }}>
              <GeoGlobe hotspots={hotspots} onHotspot={onHotspot} />
            </GlobeBoundary>
          ) : (
            <StreetMap
              title={title}
              cluster={placed.length > 40}
              points={placed.map((h) => ({
                id: String(h.id),
                lat: h.latitude,
                lon: h.longitude,
                radius: radius(h.intensity_score),
                color: RISK_VAR[h.risk_level],
                label: `${h.location_name}${h.country_name && h.country_name !== h.location_name ? `, ${h.country_name}` : ''}`,
                detail: `${RISK_LABEL[h.risk_level]} risk · intensity ${Math.round(h.intensity_score)} · ${h.article_count} articles${h.primary_category ? ` · ${cap(h.primary_category)}` : ''}`,
                onSelect: onHotspot ? () => onHotspot(h) : undefined,
              }))}
              caption={
                <>
                  {counts.map(({ r, n }) => `${RISK_LABEL[r]} ${n}`).join(' · ')}
                  {' · bigger dot = higher intensity'}
                  {placed.length < hotspots.length ? ` · ${hotspots.length - placed.length} without coordinates not shown` : ''}
                  {placed.length > 40 ? ' · nearby hotspots are grouped; zoom in to separate them' : ''}
                </>
              }
            />
          )}
        </Suspense>
      )}
    </Stack>
  );
}
