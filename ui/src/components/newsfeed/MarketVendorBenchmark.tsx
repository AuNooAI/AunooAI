/**
 * One vendor against the market it was measured in (spec 4.16).
 *
 * Every row here is a comparison that would render perfectly well as a
 * confident number even when it means nothing, so the component's real job is
 * knowing when not to draw one:
 *
 * - A vendor with no valid value shows why, not a bar at zero.
 * - A market with fewer than five measured peers shows nothing to compare
 *   against, because a median of four is noise and in a registry this size it
 *   also names them.
 * - A percentage against a median of zero is not shown at all. The absolute
 *   difference is, with a line saying why the percentage is missing.
 *
 * No radar chart and no red/green. More posts, more funding and more open
 * roles are activity and scale. Whether that is good depends on things this
 * page cannot see.
 */

import { useEffect, useState } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';
import {
  getVendorBenchmarks, type VendorBenchmark, type VendorBenchmarks,
} from '../../services/marketMonitorApi';

/** How a metric's numbers are written. Headcount and listings are whole
 *  things; a percentage change and a funding total are not. */
function fmt(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined) return '—';
  if (unit === 'percent') return `${value > 0 ? '+' : ''}${value}%`;
  if (unit === 'musd') {
    return value >= 1000 ? `$${(value / 1000).toFixed(2)}B`
      : `$${Math.round(value)}M`;
  }
  return Number.isInteger(value) ? String(value)
    : String(Math.round(value * 10) / 10);
}

/** The clock this metric runs on, said out loud.
 *
 *  The page defaults to thirty days and most metrics on it are thirty-day
 *  flows, so a level — headcount now, listings open now — has to say so or it
 *  reads as a rate. "32 open roles" and "32 roles posted this month" are
 *  different claims about a company. */
function clockOf(b: VendorBenchmark, days: number): string {
  return b.metric.window === 'period'
    ? `Over the last ${days} days`
    : `As of ${b.as_of ? new Date(b.as_of).toLocaleDateString() : 'the latest run'}`
      + (b.metric.as_of_note ? ` — ${b.metric.as_of_note}` : '');
}

/** A horizontal plot of one metric: the vendor's marker, the market median and
 *  average, and the shaded quartile band of the top cohort. Scaled to the
 *  largest of everything shown so the markers cannot fall off the end. */
function Plot({ b }: { b: VendorBenchmark }) {
  const points = [b.vendor_value, b.market_median, b.market_average,
                  b.top_median, b.top_q3].filter(
                    (n): n is number => n !== null && n !== undefined);
  if (!points.length) return null;
  const lo = Math.min(0, ...points);
  const hi = Math.max(...points);
  const span = hi - lo || 1;
  const at = (n: number) => `${((n - lo) / span) * 100}%`;

  return (
    <div className="relative h-7 rounded bg-slate-100 dark:bg-gray-700">
      {b.top_q1 !== null && b.top_q3 !== null && (
        <div className="absolute inset-y-0 bg-slate-300/60 dark:bg-gray-600/60"
             style={{ left: at(b.top_q1), right: `${100 - parseFloat(at(b.top_q3))}%` }}
             title={`Top cohort middle half: ${fmt(b.top_q1, b.metric.unit)} to ${fmt(b.top_q3, b.metric.unit)}`} />
      )}
      {b.market_median !== null && (
        <div className="absolute inset-y-0 w-px bg-slate-600 dark:bg-gray-300"
             style={{ left: at(b.market_median) }}
             title={`Market median ${fmt(b.market_median, b.metric.unit)}`} />
      )}
      {b.market_average !== null && (
        <div className="absolute inset-y-1 w-px bg-slate-400 dark:bg-gray-500"
             style={{ left: at(b.market_average) }}
             title={`Market average ${fmt(b.market_average, b.metric.unit)}`} />
      )}
      {b.vendor_value !== null && (
        <div className="absolute -top-0.5 -bottom-0.5 w-1.5 rounded bg-blue-600 dark:bg-blue-400"
             style={{ left: at(b.vendor_value) }}
             title={`${b.vendor ?? 'This vendor'}: ${fmt(b.vendor_value, b.metric.unit)}`} />
      )}
    </div>
  );
}

/** "Busier than" is right for the Activity Index and wrong for a headcount.
 *  The comparative follows the unit so a level is not described as a pace. */
function aheadOf(unit: string): string {
  if (unit === 'people') return 'larger than';
  if (unit === 'musd') return 'better funded than';
  if (unit === 'index') return 'busier than';
  if (unit === 'percent') return 'grew faster than';
  return 'ahead of';
}

/** Nothing to compare: the vendor, the market median and the top cohort's
 *  median are all zero. Drawing a plot of four zeros and two warnings about
 *  dividing by them says nothing the one line does not. */
function flatZero(b: VendorBenchmark): boolean {
  return !b.suppressed && b.vendor_value === 0
    && (b.market_median ?? 0) === 0 && (b.top_median ?? 0) === 0;
}

function Row({ b, days }: { b: VendorBenchmark; days: number }) {
  const unit = b.metric.unit;
  if (flatZero(b)) {
    return (
      <div className="border-t py-3 first:border-t-0 dark:border-gray-700">
        <div className="flex items-baseline justify-between gap-3 flex-wrap">
          <div>
            <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
              {b.metric.label}
            </div>
            <div className="text-xs text-slate-500 dark:text-gray-400">
              {clockOf(b, days)}
            </div>
          </div>
          <div className="text-xl font-semibold text-slate-800 dark:text-gray-100">0</div>
        </div>
        <p className="text-xs text-slate-500 mt-1 dark:text-gray-400">
          None for this vendor, and none at the market median or the{' '}
          {b.top_label?.toLowerCase()} median either — {b.measured_count} of{' '}
          {b.eligible_count} vendors measured, most of them at zero. There is
          nothing to rank here yet.
        </p>
      </div>
    );
  }
  return (
    <div className="border-t py-3 first:border-t-0 dark:border-gray-700">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <div>
          <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
            {b.metric.label}
          </div>
          <div className="text-xs text-slate-500 dark:text-gray-400">
            {clockOf(b, days)}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xl font-semibold text-slate-800 dark:text-gray-100">
            {fmt(b.vendor_value, unit)}
          </div>
          {b.vendor_percentile !== null && (
            <div className="text-xs text-slate-500 dark:text-gray-400">
              {aheadOf(unit)} {b.vendor_percentile}% of the {b.measured_count}{' '}
              vendors measured
            </div>
          )}
        </div>
      </div>

      {b.suppressed ? (
        <p className="text-xs text-slate-500 mt-2 dark:text-gray-400">
          {b.notes[0]}
        </p>
      ) : (
        <>
          <div className="mt-2"><Plot b={b} /></div>
          <div className="mt-2 grid gap-x-4 gap-y-1 text-xs text-slate-600 sm:grid-cols-2 lg:grid-cols-4 dark:text-gray-400">
            <span>Market median <strong className="text-slate-800 dark:text-gray-200">{fmt(b.market_median, unit)}</strong></span>
            <span>Market average <strong className="text-slate-800 dark:text-gray-200">{fmt(b.market_average, unit)}</strong></span>
            <span>{b.top_label} median <strong className="text-slate-800 dark:text-gray-200">{fmt(b.top_median, unit)}</strong></span>
            <span>{b.top_label} average <strong className="text-slate-800 dark:text-gray-200">{fmt(b.top_average, unit)}</strong></span>
          </div>
          {b.vendor_value !== null && (
            <p className="text-xs text-slate-500 mt-1.5 dark:text-gray-400">
              {fmt(b.delta_from_market_median, unit)} against the market median
              {b.percentage_delta_from_market_median !== null
                && ` (${b.percentage_delta_from_market_median > 0 ? '+' : ''}${b.percentage_delta_from_market_median}%)`}
              {'. '}
              {fmt(b.delta_from_top_median, unit)} against the {b.top_label?.toLowerCase()} median
              {b.percentage_delta_from_top_median !== null
                && ` (${b.percentage_delta_from_top_median > 0 ? '+' : ''}${b.percentage_delta_from_top_median}%)`}.
            </p>
          )}
          <p className="text-xs text-slate-400 mt-1 dark:text-gray-500">
            {b.measured_count} of {b.eligible_count} vendors measured
            {b.collection?.label ? ` · ${b.collection.label}` : ''}
            {b.as_of ? ` · as of ${new Date(b.as_of).toLocaleDateString()}` : ''}
          </p>
        </>
      )}

      {b.notes.filter(n => !b.suppressed || n !== b.notes[0]).map((n, i) => (
        <p key={i} className="text-xs text-amber-700 mt-1 flex items-start gap-1 dark:text-amber-400">
          <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />{n}
        </p>
      ))}

      {b.cohort && b.cohort.length > 0 && (
        <details className="mt-1.5">
          <summary className="text-xs text-blue-600 cursor-pointer hover:underline dark:text-blue-400">
            {b.top_label}
          </summary>
          <ol className="text-xs text-slate-600 mt-1 ml-4 list-decimal dark:text-gray-400">
            {b.cohort.map(c => (
              <li key={c.brand_id}>{c.vendor} — {fmt(c.value, unit)}</li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}

export function MarketVendorBenchmark({ marketId, brandId, days = 30 }: {
  marketId: number; brandId: number; days?: number;
}) {
  const [data, setData] = useState<VendorBenchmarks | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null); setError(null);
    getVendorBenchmarks(marketId, brandId, days)
      .then(setData)
      .catch(e => setError(String(e.message ?? e)));
  }, [marketId, brandId, days]);

  return (
    <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
      <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
        Benchmark
      </div>
      <p className="text-xs text-slate-500 mt-0.5 dark:text-gray-400">
        This vendor against every other vendor in the market that has a valid
        value for the same metric, and against the leading measured vendors on
        it. The vendor is excluded from both comparators, so "above the market
        median" is not partly a statement about itself. Median leads because
        headcount, funding and attention are all skewed — one large vendor
        moves an average and leaves a median alone.
      </p>

      {error && (
        <p className="text-sm text-red-600 mt-3 dark:text-red-400">{error}</p>
      )}
      {!data && !error && (
        <p className="text-sm text-slate-500 mt-6 flex items-center gap-2 justify-center dark:text-gray-400">
          <Loader2 className="w-4 h-4 animate-spin" /> Comparing…
        </p>
      )}
      {data && (
        <>
          <div className="mt-2">
            {data.metrics.map(b => (
              <Row key={b.metric.key} b={b} days={data.period_days} />
            ))}
          </div>
          <p className="text-xs text-slate-400 mt-3 dark:text-gray-500">
            {data.note}
          </p>
        </>
      )}
    </div>
  );
}
