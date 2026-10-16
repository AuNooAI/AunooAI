import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Globe, { type GlobeMethods } from 'react-globe.gl';
import type { Hotspot } from '@monolith/geopoliticalHotspotsApi';
import { RISK_LABEL, RISK_ORDER, cap } from './labels';
import './geo.css';

/*
 * The hotspots on a 3D globe, as the old HotspotGlobe (react-globe.gl). Loaded only when the reader
 * picks "Globe", because the 3D library is large. The earth images come from unpkg.com in the
 * reader's browser, as on the old page. Dot size follows the risk level and the article count;
 * colour follows the risk. Click a dot to open its articles.
 *
 * The old globe put hotspot names into its HTML labels unescaped, so a location name containing
 * markup would have run as HTML; names are escaped here.
 */

// Fixed colours, because WebGL can't read the page's CSS variables
const RISK_COLOR: Record<string, string> = { critical: '#DC2626', high: '#F97316', medium: '#EAB308', low: '#22C55E', info: '#3B82F6' };
const RISK_SIZE: Record<string, number> = { critical: 1.2, high: 1.0, medium: 0.8, low: 0.6, info: 0.4 };
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

type Point = Hotspot & { lat: number; lng: number; size: number; color: string };

export default function GeoGlobe({ hotspots, onHotspot }: { hotspots: Hotspot[]; onHotspot?: (h: Hotspot) => void }) {
  const ref = useRef<GlobeMethods | undefined>(undefined);
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 640, height: 480 });

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ width: el.clientWidth, height: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const stopSpin = useCallback(() => {
    const c = ref.current?.controls() as { autoRotate?: boolean } | undefined;
    if (c) c.autoRotate = false;
  }, []);

  const onReady = useCallback(() => {
    ref.current?.pointOfView({ lat: 30, lng: 20, altitude: 2.5 }, 1000);
    const c = ref.current?.controls() as { autoRotate?: boolean; autoRotateSpeed?: number } | undefined;
    // No spinning for readers who asked the system for less motion
    if (c && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      c.autoRotate = true;
      c.autoRotateSpeed = 0.5;
    }
  }, []);

  const points = useMemo<Point[]>(
    () => hotspots
      .filter((h) => Number.isFinite(h.latitude) && Number.isFinite(h.longitude))
      .map((h) => ({ ...h, lat: h.latitude, lng: h.longitude, size: (RISK_SIZE[h.risk_level] ?? 0.6) * (1 + Math.log10(h.article_count + 1) * 0.3), color: RISK_COLOR[h.risk_level] ?? RISK_COLOR.info })),
    [hotspots],
  );

  const label = useCallback((p: object) => {
    const h = p as Point;
    return `<div class="geo-globe__tip"><strong>${esc(h.location_name)}</strong>${h.country_name ? `<div>${esc(h.country_name)}</div>` : ''}<div>${esc(RISK_LABEL[h.risk_level] ?? h.risk_level)} risk${h.primary_category ? ` · ${esc(cap(h.primary_category))}` : ''}</div><div>Intensity ${Math.round(h.intensity_score)} · ${h.article_count.toLocaleString()} articles</div></div>`;
  }, []);

  return (
    <figure className="geo-globe-figure">
      <div ref={box} className="geo-globe" onPointerDown={stopSpin} role="img" aria-label={`3D globe of ${points.length} hotspots. The list under the map has the same hotspots.`}>
        <Globe
          ref={ref}
          width={size.width}
          height={size.height}
          onGlobeReady={onReady}
          globeImageUrl="https://unpkg.com/three-globe/example/img/earth-night.jpg"
          bumpImageUrl="https://unpkg.com/three-globe/example/img/earth-topology.png"
          backgroundColor="rgba(0,0,0,0)"
          pointsData={points}
          pointLat="lat"
          pointLng="lng"
          pointColor="color"
          pointAltitude={0.01}
          pointRadius="size"
          pointLabel={label}
          pointsMerge={false}
          onPointClick={onHotspot ? (p) => onHotspot(p as Point) : undefined}
          atmosphereColor="#4299e1"
          atmosphereAltitude={0.15}
        />
      </div>
      <figcaption>
        <ul className="geo-legend" aria-label="Risk levels on the globe">
          {RISK_ORDER.filter((r) => points.some((p) => p.risk_level === r)).map((r) => (
            <li key={r}><span className="geo-legend__key geo-legend__key--fixed" style={{ background: RISK_COLOR[r] }} aria-hidden="true" />{RISK_LABEL[r]}</li>
          ))}
          <li>Drag to turn, scroll to zoom, click a dot for its articles</li>
        </ul>
      </figcaption>
    </figure>
  );
}
