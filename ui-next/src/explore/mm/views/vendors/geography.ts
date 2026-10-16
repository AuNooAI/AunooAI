import type { MarketGeographyCountry } from '@monolith/marketMonitorApi';

/*
 * Country placement and scaling for the vendor map, as the old map/marketGeography.ts.
 *
 * Circle area, not radius, carries the number: the radius goes with the square root, because the eye
 * reads area. And a country where no vendor published a funding amount isn't a country with no
 * funding, so on the funding view it gets its own grey dashed circle and the words "not disclosed",
 * never a small circle or a zero. Placement is at country centroids because the data records a
 * country, not a city.
 */

export type Overlay = 'concentration' | 'funding';

/** Rough centroids [latitude, longitude], good enough for a country-level circle */
const CENTROIDS: Record<string, [number, number]> = {
  'United States': [39.8, -98.6], 'United Kingdom': [54.0, -2.0], Israel: [31.5, 34.8], India: [22.4, 78.9],
  France: [46.6, 2.5], Spain: [40.2, -3.6], Italy: [42.8, 12.6], Netherlands: [52.2, 5.3], 'The Netherlands': [52.2, 5.3],
  Romania: [45.9, 24.9], Turkey: [39.0, 35.2], 'Saudi Arabia': [23.9, 45.1], 'United Arab Emirates': [24.0, 54.0],
  Bahrain: [26.0, 50.5], Australia: [-25.3, 133.8], Germany: [51.2, 10.4], Canada: [56.1, -106.3], Ireland: [53.4, -8.2],
  Singapore: [1.35, 103.8], Japan: [36.2, 138.3], Sweden: [60.1, 18.6], Switzerland: [46.8, 8.2], Poland: [51.9, 19.1],
  Portugal: [39.4, -8.2], Czechia: [49.8, 15.5], Austria: [47.5, 14.6], Belgium: [50.5, 4.5], Denmark: [56.3, 9.5],
  Finland: [61.9, 25.7], Norway: [60.5, 8.5], Estonia: [58.6, 25.0], China: [35.9, 104.2], 'South Korea': [36.5, 127.8],
};

export const centroid = (country: string) => CENTROIDS[country] ?? null;

const MIN_R = 8;
const MAX_R = 42;

export const valueFor = (r: MarketGeographyCountry, o: Overlay) => (o === 'concentration' ? r.vendors : r.total_musd);
export const isUndisclosed = (r: MarketGeographyCountry, o: Overlay) => o === 'funding' && r.total_musd === null;

/** Minimum size for a country with no value, so it stays visible: vanishing would read as "no vendors here" */
export function radiusFor(value: number | null, max: number) {
  if (value === null || value <= 0 || max <= 0) return MIN_R;
  return MIN_R + (Math.sqrt(value) / Math.sqrt(max)) * (MAX_R - MIN_R);
}

export const maxValue = (rows: MarketGeographyCountry[], o: Overlay) => Math.max(0, ...rows.map((r) => valueFor(r, o) ?? 0));

export function formatMusd(v: number | null) {
  if (v === null) return 'not disclosed';
  if (v >= 1000) return `$${(v / 1000).toFixed(1)}bn`;
  return `$${v.toFixed(v < 10 ? 1 : 0)}m`;
}

/** What a funding total covers. "$949.8m" across 53 vendors sounds like the market when it's 31 companies' rounds */
export function fundingCaveat(r: MarketGeographyCountry) {
  if (r.total_musd === null) return r.vendors === 1 ? 'The one vendor here hasn’t disclosed funding.' : `None of the ${r.vendors} vendors here have disclosed funding.`;
  const parts = [`covers ${r.vendors_with_amount} of ${r.vendors} vendors`];
  if (r.not_disclosed) parts.push(`${r.not_disclosed} undisclosed`);
  if (r.status_unknown) parts.push(`${r.status_unknown} unknown`);
  return parts.join(', ');
}
