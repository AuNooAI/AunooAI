/**
 * Country placement and scaling for the vendor map.
 *
 * Two decisions here are worth stating, because both are ways a map of this
 * data would otherwise mislead.
 *
 * **Area, not radius, carries the number.** Scaling a circle's radius by a
 * count makes 53 look roughly eleven times bigger than 5 in linear terms but
 * over a hundred times bigger by area, which is what the eye actually reads.
 * The radius is therefore proportional to the square root.
 *
 * **A country with no disclosed funding is not a country with no funding.**
 * Most vendors here never published an amount — every one of India's five is
 * "Undisclosed", as are 22 of the 53 in the United States. Drawing those as
 * small or empty circles would say something about those companies that the
 * data does not support, so they get their own visual treatment and their own
 * label, and are never given a zero.
 *
 * Placement is at country centroids because `hq_country` is a country name.
 * There is no city in the data, so nothing may be drawn at city precision.
 */

/** Rough centroids, good enough to place a country-level bubble. */
export const COUNTRY_CENTROIDS: Record<string, [number, number]> = {
  'United States': [39.8, -98.6],
  'United Kingdom': [54.0, -2.0],
  Israel: [31.5, 34.8],
  India: [22.4, 78.9],
  France: [46.6, 2.5],
  Spain: [40.2, -3.6],
  Italy: [42.8, 12.6],
  Netherlands: [52.2, 5.3],
  Romania: [45.9, 24.9],
  Turkey: [39.0, 35.2],
  'Saudi Arabia': [23.9, 45.1],
  'United Arab Emirates': [24.0, 54.0],
  Bahrain: [26.0, 50.5],
  Australia: [-25.3, 133.8],
  Germany: [51.2, 10.4],
  Canada: [56.1, -106.3],
  Ireland: [53.4, -8.2],
  Singapore: [1.35, 103.8],
  Japan: [36.2, 138.3],
  Sweden: [60.1, 18.6],
  Switzerland: [46.8, 8.2],
  Poland: [51.9, 19.1],
  Portugal: [39.4, -8.2],
  Czechia: [49.8, 15.5],
  Austria: [47.5, 14.6],
  Belgium: [50.5, 4.5],
  Denmark: [56.3, 9.5],
  Finland: [61.9, 25.7],
  Norway: [60.5, 8.5],
};

export interface CountryRow {
  country: string;
  vendors: number;
  vendors_with_amount: number;
  not_disclosed: number;
  status_unknown: number;
  /** Null when no vendor in this country has published an amount. */
  total_musd: number | null;
  largest_musd: number | null;
  funding_coverage: number;
  staff: number | null;
}

export type Overlay = 'concentration' | 'funding';

export function centroid(country: string): [number, number] | null {
  return COUNTRY_CENTROIDS[country] ?? null;
}

/** Countries we hold vendors for but cannot place. Never silently dropped. */
export function unplaceable(rows: CountryRow[]): CountryRow[] {
  return rows.filter(r => centroid(r.country) === null);
}

const MIN_RADIUS = 8;
const MAX_RADIUS = 42;

/**
 * Circle radius in pixels, by area rather than by radius.
 *
 * Returns MIN_RADIUS for a country with no value on this overlay, so it stays
 * visible and clickable — a country that vanishes reads as "no vendors here",
 * which is the opposite of what an undisclosed funding figure means.
 */
export function radiusFor(value: number | null, max: number): number {
  if (value === null || value <= 0 || max <= 0) return MIN_RADIUS;
  const scaled = Math.sqrt(value) / Math.sqrt(max);
  return MIN_RADIUS + scaled * (MAX_RADIUS - MIN_RADIUS);
}

export function maxValue(rows: CountryRow[], overlay: Overlay): number {
  const values = rows.map(r => valueFor(r, overlay) ?? 0);
  return values.length ? Math.max(...values) : 0;
}

export function valueFor(row: CountryRow, overlay: Overlay): number | null {
  return overlay === 'concentration' ? row.vendors : row.total_musd;
}

/** Whether this country has nothing to say on the funding overlay. */
export function isUndisclosed(row: CountryRow, overlay: Overlay): boolean {
  return overlay === 'funding' && row.total_musd === null;
}

export function formatMusd(value: number | null): string {
  if (value === null) return 'not disclosed';
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}bn`;
  return `$${value.toFixed(value < 10 ? 1 : 0)}m`;
}

/**
 * The sentence under a funding figure, naming what it covers.
 *
 * A total is meaningless without its denominator here: "$949.8m" across 53
 * vendors sounds like the market, when it is 31 companies' disclosed rounds
 * and 22 companies who never said.
 */
export function fundingCaveat(row: CountryRow): string {
  if (row.total_musd === null) {
    return row.vendors === 1
      ? 'The one vendor here has not disclosed funding.'
      : `None of the ${row.vendors} vendors here have disclosed funding.`;
  }
  const parts = [`covers ${row.vendors_with_amount} of ${row.vendors} vendors`];
  if (row.not_disclosed) parts.push(`${row.not_disclosed} undisclosed`);
  if (row.status_unknown) parts.push(`${row.status_unknown} unknown`);
  return parts.join(', ');
}

/** Colour ramp. Undisclosed is a separate colour, not the bottom of the ramp. */
export const UNDISCLOSED_COLOR = '#94a3b8';

export function colorFor(row: CountryRow, overlay: Overlay,
                         max: number): string {
  if (isUndisclosed(row, overlay)) return UNDISCLOSED_COLOR;
  const value = valueFor(row, overlay);
  if (value === null || max <= 0) return UNDISCLOSED_COLOR;
  const t = Math.sqrt(value) / Math.sqrt(max);
  if (overlay === 'concentration') {
    return t > 0.66 ? '#1d4ed8' : t > 0.33 ? '#3b82f6' : '#93c5fd';
  }
  return t > 0.66 ? '#047857' : t > 0.33 ? '#10b981' : '#6ee7b7';
}
