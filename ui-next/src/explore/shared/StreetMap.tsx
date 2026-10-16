import { useEffect, useMemo } from 'react';
import { MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import L from 'leaflet';
import { EmptyState, Text } from '@aunoo/ui';
import 'leaflet/dist/leaflet.css';
import 'react-leaflet-cluster/dist/assets/MarkerCluster.css';
import 'react-leaflet-cluster/dist/assets/MarkerCluster.Default.css';
import './StreetMap.css';

/*
 * A real street map (Leaflet with OpenStreetMap tiles), with optional marker clustering. Used by
 * GeoHotSpots, Threat Intelligence and the Market Monitor vendor geography. Tiles load from
 * tile.openstreetmap.org in the reader's browser, as the old pages did.
 *
 * Every point is drawn as a small round marker (a Leaflet divIcon), not a CircleMarker, because
 * the cluster library only groups markers. The marker carries the radius, colour and dashed outline.
 */

export interface StreetMapPoint {
  id: string;
  lat: number;
  lon: number;
  /** Circle radius in pixels; omit for a default marker size */
  radius?: number;
  /** Fill colour (a CSS colour or var(--token)); omit for the default */
  color?: string;
  /** Dashed outline, e.g. "not disclosed" in the vendor funding view */
  dashed?: boolean;
  label: string;
  /** Shown in the popup under the label */
  detail?: React.ReactNode;
  onSelect?: () => void;
}
export interface StreetMapProps {
  title: string;
  points: StreetMapPoint[];
  /** Group nearby points into clusters */
  cluster?: boolean;
  /** CSS height, default 420px */
  height?: string;
  /** Initial view; defaults to fitting the points */
  center?: [number, number];
  zoom?: number;
  caption?: React.ReactNode;
  emptyText?: string;
}

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

function iconFor(p: StreetMapPoint) {
  const r = Math.max(4, Math.min(40, p.radius ?? 7));
  const size = r * 2;
  const style = [
    `width:${size}px`, `height:${size}px`,
    p.color ? `background:${esc(p.color)}` : '',
    p.dashed ? 'border-style:dashed' : '',
  ].filter(Boolean).join(';');
  return L.divIcon({
    className: 'street-map__marker-wrap',
    html: `<span class="street-map__marker${p.dashed ? ' street-map__marker--dashed' : ''}" style="${style}"></span>`,
    iconSize: [size, size],
    iconAnchor: [r, r],
    popupAnchor: [0, -r],
  });
}

/** Fits the view to the points once they're known (unless a centre was given) */
function FitToPoints({ points, center, zoom }: { points: StreetMapPoint[]; center?: [number, number]; zoom?: number }) {
  const map = useMap();
  const key = points.map((p) => `${p.id}:${p.lat}:${p.lon}`).join('|');
  useEffect(() => {
    if (center) {
      map.setView(center, zoom ?? 3);
      return;
    }
    if (!points.length) return;
    if (points.length === 1) {
      map.setView([points[0].lat, points[0].lon], zoom ?? 5);
      return;
    }
    map.fitBounds(L.latLngBounds(points.map((p) => [p.lat, p.lon] as [number, number])), { padding: [24, 24], maxZoom: 6 });
  }, [map, key, center, zoom]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

export function StreetMap({ title, points, cluster = false, height = '420px', center, zoom, caption, emptyText = 'Nothing to place on the map.' }: StreetMapProps) {
  const valid = useMemo(() => points.filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lon) && Math.abs(p.lat) <= 90 && Math.abs(p.lon) <= 180), [points]);
  if (!valid.length) return <EmptyState icon="Globe" title="Nothing to place">{emptyText}</EmptyState>;

  const markers = valid.map((p) => (
    <Marker
      key={p.id}
      position={[p.lat, p.lon]}
      icon={iconFor(p)}
      title={p.label}
      alt={p.label}
      keyboard
      eventHandlers={p.onSelect ? { click: () => p.onSelect!() } : undefined}
    >
      <Popup>
        <div className="street-map__popup">
          <strong>{p.label}</strong>
          {p.detail && <div>{p.detail}</div>}
        </div>
      </Popup>
    </Marker>
  ));

  return (
    <figure className="street-map" aria-label={title}>
      <div className="street-map__frame" style={{ height }}>
        <MapContainer
          center={center ?? [20, 0]}
          zoom={zoom ?? 2}
          minZoom={1}
          worldCopyJump
          scrollWheelZoom={false}
          className="street-map__map"
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <FitToPoints points={valid} center={center} zoom={zoom} />
          {cluster ? <MarkerClusterGroup chunkedLoading>{markers}</MarkerClusterGroup> : markers}
        </MapContainer>
      </div>
      {caption && <figcaption><Text variant="caption">{caption}</Text></figcaption>}
    </figure>
  );
}

export default StreetMap;
