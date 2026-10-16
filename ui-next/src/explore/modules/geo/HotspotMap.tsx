import type { Hotspot } from '@monolith/geopoliticalHotspotsApi';
import { RISK_LABEL, RISK_ORDER, cap } from './labels';
import './geo.css';

/*
 * The hotspots as points on a plain longitude and latitude grid. The old page drew them on map
 * tiles (Leaflet) and a 3D globe; neither library is in this app. Each dot sits at the hotspot's
 * own coordinates, its size follows the intensity score and its colour the risk level; the legend
 * and the lists beside the map carry the exact figures. Dots are buttons: click or Enter opens the
 * hotspot's articles.
 */

const W = 1000;
const LAT_TOP = 80;
const LAT_BOTTOM = -60;
const H = Math.round(((LAT_TOP - LAT_BOTTOM) / 360) * W);
const px = (lng: number) => ((lng + 180) / 360) * W;
const py = (lat: number) => ((LAT_TOP - Math.max(LAT_BOTTOM, Math.min(LAT_TOP, lat))) / (LAT_TOP - LAT_BOTTOM)) * H;
const radius = (intensity: number) => 4 + (Math.max(0, Math.min(100, intensity)) / 100) * 10;

export function HotspotMap({ hotspots, onHotspot, title = 'Hotspots by location', labelTop = 0 }: {
  hotspots: Hotspot[];
  onHotspot?: (h: Hotspot) => void;
  title?: string;
  /** Name this many of the most intense hotspots on the map itself */
  labelTop?: number;
}) {
  const placed = hotspots.filter((h) => Number.isFinite(h.latitude) && Number.isFinite(h.longitude));
  // Least intense first, so the biggest dots are drawn last and the small ones under them stay visible at the edges
  const ordered = [...placed].sort((a, b) => a.intensity_score - b.intensity_score);
  const labelled = new Set([...placed].sort((a, b) => b.intensity_score - a.intensity_score).slice(0, labelTop).map((h) => h.id));
  const counts = RISK_ORDER.map((r) => ({ r, n: placed.filter((h) => h.risk_level === r).length })).filter((x) => x.n > 0);

  return (
    <figure className="geo-map-figure">
      <svg className="geo-map" viewBox={`0 0 ${W} ${H}`} role="group" aria-label={`${title}: ${placed.length} hotspots`}>
        {[-150, -120, -90, -60, -30, 0, 30, 60, 90, 120, 150].map((lng) => <line key={`x${lng}`} className="geo-map__grid" x1={px(lng)} x2={px(lng)} y1={0} y2={H} />)}
        {[60, 30, -30].map((lat) => <line key={`y${lat}`} className="geo-map__grid" x1={0} x2={W} y1={py(lat)} y2={py(lat)} />)}
        <line className="geo-map__equator" x1={0} x2={W} y1={py(0)} y2={py(0)} />
        {ordered.map((h) => {
          const label = `${h.location_name}${h.country_name && h.country_name !== h.location_name ? `, ${h.country_name}` : ''}: ${RISK_LABEL[h.risk_level]} risk, intensity ${Math.round(h.intensity_score)}, ${h.article_count} articles${h.primary_category ? `, ${cap(h.primary_category)}` : ''}`;
          return (
            <g key={h.id}>
              <circle
                className={`geo-map__dot geo-risk--${h.risk_level}`}
                cx={px(h.longitude)}
                cy={py(h.latitude)}
                r={radius(h.intensity_score)}
                role={onHotspot ? 'button' : undefined}
                tabIndex={onHotspot ? 0 : undefined}
                aria-label={onHotspot ? `${label}. Show its articles` : label}
                onClick={onHotspot ? () => onHotspot(h) : undefined}
                onKeyDown={onHotspot ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onHotspot(h); } } : undefined}
              >
                <title>{label}</title>
              </circle>
              {labelled.has(h.id) && (
                <text className="geo-map__label" x={px(h.longitude) + radius(h.intensity_score) + 3} y={py(h.latitude) + 4}>{h.location_name}</text>
              )}
            </g>
          );
        })}
      </svg>
      <figcaption>
        <ul className="geo-legend" aria-label="Risk levels on the map">
          {counts.map(({ r, n }) => (
            <li key={r}><span className={`geo-legend__key geo-risk--${r}`} aria-hidden="true" />{`${RISK_LABEL[r]} (${n})`}</li>
          ))}
          <li>Bigger dot = higher intensity</li>
          {placed.length < hotspots.length && <li>{`${hotspots.length - placed.length} without coordinates not shown`}</li>}
        </ul>
      </figcaption>
    </figure>
  );
}
