/* Number wording and chart scales for the Pulse panels. */

/** "+3" / "-1" / "0" */
export const signed = (v: number) => `${v > 0 ? '+' : ''}${v}`;

/** "+12%" or a dash when there's no figure */
export const signedPct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${signed(v)}%`);

/**
 * "Attention up 3" / "Attention unchanged". Never a bare "attention 0", which reads as a score of
 * zero rather than no change.
 */
export function scoreDelta(label: string, v: number): string {
  if (v === 0) return `${label} unchanged`;
  return `${label} ${v > 0 ? 'up' : 'down'} ${Math.abs(v)}`;
}

/** $1.234B or $450M; a dash when nothing was disclosed */
export function money(musd: number | null | undefined): string {
  if (musd === null || musd === undefined) return '—';
  return musd >= 1000 ? `$${(musd / 1000).toFixed(3)}B` : `$${musd.toFixed(0)}M`;
}

/** A y scale over the values, in whole steps of 1, 2, 2.5 or 5 × 10ⁿ, with zero always inside */
export function scale(values: (number | null | undefined)[]): { domain: [number, number]; ticks: number[] } {
  const real = values.filter((v): v is number => typeof v === 'number');
  let lo = Math.min(0, ...real);
  let hi = Math.max(0, ...real);
  if (lo === hi) hi = lo + 1;
  const raw = (hi - lo) / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  lo = Math.floor(lo / step) * step;
  hi = Math.ceil(hi / step) * step;
  const ticks: number[] = [];
  for (let t = lo; t <= hi + step / 2; t += step) ticks.push(Math.round(t * 100) / 100);
  return { domain: [lo, hi], ticks };
}
