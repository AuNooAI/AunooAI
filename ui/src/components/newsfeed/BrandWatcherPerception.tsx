/**
 * Brand Watcher — Perception dimensions view.
 *
 * One view across the five perception surfaces: media (news sentiment),
 * social (Bluesky/X/Instagram/TikTok), community (Reddit), employee
 * (Glassdoor), investor (Financial Performance category sentiment).
 * Radar overlays every enabled brand for benchmarking; the table below
 * carries the raw numbers with volume context.
 */

import { useState, useEffect } from 'react';
import { Loader2, Info } from 'lucide-react';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Legend, Tooltip,
} from 'recharts';
import { getPerception, BWPerceptionBrand } from '../../services/brandWatcherApi';

const DIMENSIONS: { key: 'media' | 'social' | 'community' | 'employee' | 'investor'; label: string; hint: string }[] = [
  { key: 'media', label: 'Media', hint: 'Net sentiment of news coverage in the brand topic (relevance ≥ 0.4). (positive − negative) ÷ scored × 100.' },
  { key: 'social', label: 'Social', hint: 'Net sentiment of Bluesky / X / Instagram / TikTok posts mentioning the brand (relevance ≥ 0.4).' },
  { key: 'community', label: 'Community', hint: 'Net sentiment of Reddit posts and threads mentioning the brand (relevance ≥ 0.4).' },
  { key: 'employee', label: 'Employee', hint: 'Glassdoor overall rating scaled to −100…+100 (3.0 = neutral). Hover a cell for the raw rating, outlook and landed reviews.' },
  { key: 'investor', label: 'Investor', hint: 'Net sentiment of articles classified into the Financial Performance category for the brand.' },
];

const FALLBACK_COLORS = ['#2563eb', '#9333ea', '#059669', '#d97706', '#dc2626', '#0891b2'];

function scoreChipClass(score: number | null): string {
  if (score === null) return 'bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500';
  if (score >= 20) return 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300';
  if (score <= -20) return 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300';
  return 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300';
}

function cellTitle(dimKey: string, d: any): string {
  if (!d) return 'No data in this window';
  if (dimKey === 'employee') {
    const bits = [];
    if (d.rating != null) bits.push(`Glassdoor rating ${d.rating}/5`);
    if (d.outlook != null) bits.push(`business outlook ${Math.round(d.outlook * 100)}%`);
    if (d.review_count != null) bits.push(`${d.review_count} reviews on Glassdoor`);
    if (d.reviews_n) bits.push(`${d.reviews_n} landed reviews, net ${d.reviews_net > 0 ? '+' : ''}${d.reviews_net}`);
    return bits.length ? bits.join(' · ') : 'Glassdoor not enabled for this brand';
  }
  if (!d.n) return 'No items in this window';
  return `${d.n} items: ${d.positive} positive · ${d.neutral} neutral · ${d.negative} negative`;
}

export function BrandWatcherPerception({ daysBack }: { daysBack: number }) {
  const [brands, setBrands] = useState<BWPerceptionBrand[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Brand toggles: null = all on (default); once touched, an explicit set of visible ids
  const [visibleIds, setVisibleIds] = useState<Set<number> | null>(null);

  const isVisible = (id: number) => visibleIds === null || visibleIds.has(id);
  const toggleBrand = (id: number) => {
    setVisibleIds(prev => {
      const next = new Set(prev === null ? brands.map(b => b.brand_id) : prev);
      if (next.has(id)) {
        if (next.size > 1) next.delete(id); // keep at least one brand visible
      } else {
        next.add(id);
      }
      return next;
    });
  };

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    getPerception(daysBack)
      .then(d => { if (alive) setBrands(d.brands); })
      .catch(e => { if (alive) setError(e instanceof Error ? e.message : 'Failed to load perception data'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [daysBack]);

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div>;
  }
  if (error) {
    return <div className="p-6 text-sm text-red-600 dark:text-red-400">{error}</div>;
  }
  if (!brands.length) {
    return <div className="p-6 text-sm text-gray-500 dark:text-gray-400">No brands configured.</div>;
  }

  // Stable per-brand colors keyed on the full list, so toggling doesn't reshuffle
  const colorById = new Map(brands.map((b, i) => [b.brand_id, b.color || FALLBACK_COLORS[i % FALLBACK_COLORS.length]]));
  const colorOf = (b: BWPerceptionBrand, _i?: number) => colorById.get(b.brand_id)!;
  const shownBrands = brands.filter(b => isVisible(b.brand_id));

  // Radar shows scores normalized to 0–100 so all five axes share a scale
  // (net −100…+100 → 0…100; 50 = neutral).
  const radarData = DIMENSIONS.map(dim => {
    const row: Record<string, any> = { dimension: dim.label };
    for (const b of shownBrands) {
      const s = b.dimensions[dim.key]?.score;
      row[b.display_name] = s === null || s === undefined ? undefined : Math.round((s + 100) / 2);
    }
    return row;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Perception dimensions</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            How each brand is perceived across five surfaces over the last {daysBack} days.
            Scores are net sentiment (−100…+100); the employee score scales the Glassdoor rating.
          </p>
        </div>
      </div>

      {/* Brand toggles */}
      <div className="flex flex-wrap items-center gap-2">
        {brands.map((b, i) => {
          const on = isVisible(b.brand_id);
          return (
            <button
              key={b.brand_id}
              onClick={() => toggleBrand(b.brand_id)}
              title={on ? `Hide ${b.display_name}` : `Show ${b.display_name}`}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                on
                  ? 'border-transparent text-white'
                  : 'border-gray-300 dark:border-gray-600 text-gray-400 dark:text-gray-500 bg-transparent'
              }`}
              style={on ? { backgroundColor: colorOf(b, i) } : undefined}
            >
              <span className="w-2 h-2 rounded-full inline-block"
                style={{ backgroundColor: on ? 'rgba(255,255,255,0.85)' : colorOf(b, i) }} />
              {b.display_name}
              {b.is_primary && <span className="opacity-75 text-[10px]">primary</span>}
            </button>
          );
        })}
      </div>

      {/* Radar: all brands overlaid, axes = dimensions */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-center gap-1.5 mb-1">
          <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Perception radar</h4>
          <span title="Axes are normalized to 0–100 so all dimensions share a scale: 50 = neutral, above = net positive perception, below = net negative. Dimensions with no data in the window are left blank.">
            <Info className="w-3.5 h-3.5 text-gray-400" />
          </span>
        </div>
        <ResponsiveContainer width="100%" height={380}>
          <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="75%">
            <PolarGrid stroke="#9ca3af55" />
            <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 12 }} />
            <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 10 }} tickCount={5} />
            {shownBrands.map((b, i) => (
              <Radar key={b.brand_id} name={b.display_name} dataKey={b.display_name}
                stroke={colorOf(b, i)} fill={colorOf(b, i)} fillOpacity={0.12} strokeWidth={2} />
            ))}
            <Legend />
            <Tooltip formatter={(v: any) => [`${v}/100 (net ${(v as number) * 2 - 100})`, undefined]} />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* Table: raw scores + volumes */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 overflow-x-auto">
        <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Scores by dimension</h4>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-700">
              <th className="py-2 pr-4">Brand</th>
              {DIMENSIONS.map(dim => (
                <th key={dim.key} className="py-2 px-3">
                  <span className="inline-flex items-center gap-1" title={dim.hint}>
                    {dim.label}
                    <Info className="w-3 h-3 text-gray-300 dark:text-gray-600" />
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shownBrands.map((b, i) => (
              <tr key={b.brand_id} className="border-b border-gray-50 dark:border-gray-750 last:border-0">
                <td className="py-2.5 pr-4">
                  <span className="inline-flex items-center gap-2 font-medium text-gray-900 dark:text-gray-100">
                    <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ backgroundColor: colorOf(b, i) }} />
                    {b.display_name}
                    {b.is_primary && <span className="text-[10px] font-normal text-blue-600 dark:text-blue-400">primary</span>}
                  </span>
                </td>
                {DIMENSIONS.map(dim => {
                  const d = b.dimensions[dim.key];
                  const score = d?.score ?? null;
                  return (
                    <td key={dim.key} className="py-2.5 px-3">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium cursor-help ${scoreChipClass(score)}`}
                        title={cellTitle(dim.key, d)}
                      >
                        {score === null ? 'no data' : `${score > 0 ? '+' : ''}${score}`}
                      </span>
                      {dim.key !== 'employee' && d?.n ? (
                        <span className="ml-1.5 text-[11px] text-gray-400 dark:text-gray-500">{d.n}</span>
                      ) : null}
                      {dim.key === 'employee' && d?.rating != null ? (
                        <span className="ml-1.5 text-[11px] text-gray-400 dark:text-gray-500">{d.rating}/5</span>
                      ) : null}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-3">
          Net sentiment = (positive − negative) ÷ scored × 100 over items with relevance ≥ 0.4.
          Small counts (grey number = volume) make scores volatile — read a +100 from 2 posts accordingly.
          Employee perception comes from the Glassdoor overview (rating, outlook), not article sentiment.
        </p>
      </div>
    </div>
  );
}
