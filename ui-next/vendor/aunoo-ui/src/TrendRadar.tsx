import { useId } from 'react';
import './TrendRadar.css';

export interface RadarTrend {
  id: string;
  label: string;
  /** 0–100; distance from the centre (higher = further out = stronger). */
  score: number;
  /** Index into `sectors`. */
  sector: number;
  momentum: 'accelerating' | 'stable' | 'decelerating';
}

export interface TrendRadarProps {
  title: string;
  /** Up to three sector names, e.g. ["Power", "Attention", "Money"]. Colour = sector (data-viz slots 1–3). */
  sectors: string[];
  trends: RadarTrend[];
  selectedId?: string;
  /** `(id) => void` — each trend is a button. */
  onSelect: (id: string) => void;
  className?: string;
}

const RINGS = [25, 50, 75, 100];
const MOMENTUM_LABEL = { accelerating: 'Accelerating', stable: 'Stable', decelerating: 'Decelerating' };

/**
 * Radar of trends by sector and strength. Sector = colour, momentum = shape (filled / ring /
 * dashed ring), so neither relies on colour alone. Trends are focusable buttons; the legends and
 * the trend list say everything the picture does.
 */
export function TrendRadar({ title, sectors, trends, selectedId, onSelect, className }: TrendRadarProps) {
  const id = useId();
  const count = Math.max(1, sectors.length);
  const wedge = 360 / count;
  // Position: angle inside the trend's sector (spread when several share one), radius from score
  const placed = trends.map((t) => {
    const siblings = trends.filter((x) => x.sector === t.sector);
    const k = siblings.indexOf(t);
    const angle = (t.sector * wedge + (wedge * (k + 1)) / (siblings.length + 1) - 90) * (Math.PI / 180);
    const r = (Math.max(8, Math.min(100, t.score)) / 100) * 46; // % of the box, leaving room for labels
    return { ...t, left: 50 + r * Math.cos(angle), top: 50 + r * Math.sin(angle) };
  });

  return (
    <div className={['trend-radar', className].filter(Boolean).join(' ')}>
      <div className="trend-radar__plot" role="group" aria-labelledby={`${id}-title`}>
        <span id={`${id}-title`} className="visually-hidden">{title}. Each trend is a button; the list below the chart has the same details.</span>
        <svg className="trend-radar__svg" viewBox="0 0 100 100" aria-hidden="true">
          {RINGS.map((ring) => (
            <circle key={ring} className="trend-radar__ring" cx="50" cy="50" r={(ring / 100) * 46} />
          ))}
          {sectors.map((_, i) => {
            const a = (i * wedge - 90) * (Math.PI / 180);
            return <line key={i} className="trend-radar__spoke" x1="50" y1="50" x2={50 + 46 * Math.cos(a)} y2={50 + 46 * Math.sin(a)} />;
          })}
        </svg>
        {sectors.map((name, i) => {
          const a = ((i + 0.5) * wedge - 90) * (Math.PI / 180);
          return (
            <span key={name} className="trend-radar__sector-label" style={{ left: `${50 + 49 * Math.cos(a)}%`, top: `${50 + 49 * Math.sin(a)}%` }} aria-hidden="true">
              {name}
            </span>
          );
        })}
        {placed.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`trend-radar__point trend-radar__point--${t.momentum} trend-radar__sector--${(t.sector % 3) + 1}`}
            style={{ left: `${t.left}%`, top: `${t.top}%` }}
            aria-pressed={t.id === selectedId}
            aria-label={`${t.id}: ${t.label}, ${sectors[t.sector]}, score ${t.score}, ${MOMENTUM_LABEL[t.momentum]}`}
            onClick={() => onSelect(t.id)}
          >
            <span className="trend-radar__mark" aria-hidden="true" />
            <span className="trend-radar__point-label" aria-hidden="true">{t.id}</span>
          </button>
        ))}
      </div>
      <div className="trend-radar__legends">
        <ul className="trend-radar__legend" aria-label="Sectors">
          {sectors.map((s, i) => (
            <li key={s}><span className={`trend-radar__swatch trend-radar__sector--${(i % 3) + 1}`} aria-hidden="true" />{s}</li>
          ))}
        </ul>
        <ul className="trend-radar__legend" aria-label="Momentum">
          {(Object.keys(MOMENTUM_LABEL) as RadarTrend['momentum'][]).map((m) => (
            <li key={m}><span className={`trend-radar__mark trend-radar__point--${m} trend-radar__legend-mark`} aria-hidden="true" />{MOMENTUM_LABEL[m]}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
