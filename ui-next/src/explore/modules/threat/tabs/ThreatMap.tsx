import { useMemo } from 'react';
import type { ThreatMapData } from '../api';
import { categoryLabel, severityLabel } from '../labels';

/*
 * Threats placed by the target location the AI recorded, on a plain longitude/latitude grid. Leaflet
 * and its street tiles aren't available here; the grid shows where, and the table under the map gives
 * the names. Threats at the same spot (the AI often records only a country) fan out in a small ring
 * so none hides another.
 */

const W = 960;
const H = 440;
const LAT_TOP = 80;
const LAT_BOTTOM = -60;
const x = (lon: number) => ((lon + 180) / 360) * W;
const y = (lat: number) => ((LAT_TOP - Math.max(LAT_BOTTOM, Math.min(LAT_TOP, lat))) / (LAT_TOP - LAT_BOTTOM)) * H;
const RADIUS: Record<string, number> = { critical: 10, high: 9, medium: 7, low: 6, info: 6 };

export function ThreatMap({ threats, showLabels, onPick }: { threats: ThreatMapData[]; showLabels: boolean; onPick: (t: ThreatMapData) => void }) {
  const placed = useMemo(() => {
    const groups = new Map<string, ThreatMapData[]>();
    for (const t of threats) {
      const k = `${t.latitude.toFixed(2)},${t.longitude.toFixed(2)}`;
      groups.set(k, [...(groups.get(k) ?? []), t]);
    }
    const out: { t: ThreatMapData; cx: number; cy: number }[] = [];
    for (const list of groups.values()) {
      const cx0 = x(list[0].longitude);
      const cy0 = y(list[0].latitude);
      list.forEach((t, i) => {
        if (list.length === 1) out.push({ t, cx: cx0, cy: cy0 });
        else {
          const a = (2 * Math.PI * i) / list.length;
          const r = 10 + list.length * 2;
          out.push({ t, cx: cx0 + r * Math.cos(a), cy: cy0 + r * Math.sin(a) });
        }
      });
    }
    // Draw the most serious last, so it sits on top
    const rank: Record<string, number> = { info: 0, low: 1, medium: 2, high: 3, critical: 4 };
    return out.sort((a, b) => (rank[a.t.severity_level] ?? 0) - (rank[b.t.severity_level] ?? 0));
  }, [threats]);

  const lons = [-120, -60, 0, 60, 120];
  const lats = [60, 30, -30];
  return (
    <svg className="threat-map" viewBox={`0 0 ${W} ${H}`} role="group" aria-label={`Map of ${threats.length} threats by target location`}>
      {lons.map((l) => <line key={`lon${l}`} className="threat-map__grid" x1={x(l)} x2={x(l)} y1={0} y2={H} />)}
      {lats.map((l) => <line key={`lat${l}`} className="threat-map__grid" x1={0} x2={W} y1={y(l)} y2={y(l)} />)}
      <line className="threat-map__equator" x1={0} x2={W} y1={y(0)} y2={y(0)} />
      <text className="threat-map__axis" x={6} y={y(0) - 6}>Equator</text>
      {lons.map((l) => <text key={`t${l}`} className="threat-map__axis" x={x(l) + 4} y={H - 6}>{`${Math.abs(l)}°${l < 0 ? 'W' : l > 0 ? 'E' : ''}`}</text>)}
      {placed.map(({ t, cx, cy }) => (
        <g key={t.id}>
          <circle
            className={`threat-map__dot threat-map__dot--${t.severity_level}`}
            cx={cx}
            cy={cy}
            r={RADIUS[t.severity_level] ?? 6}
            tabIndex={0}
            role="button"
            aria-label={`${t.threat_name}: ${severityLabel(t.severity_level)}, ${categoryLabel(t.threat_type)}. Show its articles.`}
            onClick={() => onPick(t)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onPick(t);
              }
            }}
          >
            <title>{`${t.threat_name} · ${severityLabel(t.severity_level)} · ${categoryLabel(t.threat_type)}${t.threat_actor_name ? ` · ${t.threat_actor_name}` : ''}`}</title>
          </circle>
          {showLabels && (
            <text className="threat-map__label" x={cx + 12} y={cy + 4}>{t.threat_name.length > 28 ? `${t.threat_name.slice(0, 27)}…` : t.threat_name}</text>
          )}
        </g>
      ))}
    </svg>
  );
}
