/**
 * Showing whether a number was measured.
 *
 * The rule these components exist to enforce: a zero on the page must mean a
 * collector ran, finished across the stated population, and found nothing.
 * Every other empty-looking outcome — never collected, still collecting,
 * failed, only part of the market reached — gets said out loud instead of being
 * rendered as `0`. Before this, all of them printed the same digit.
 *
 * The server decides. `MetricMeta.measured` and `data_state` come from
 * app/services/market_metrics.py, and nothing here re-derives them; a second
 * copy of that rule in the browser is a second thing to get out of step.
 */

import React, { useState } from 'react';
import type { DataState, MetricMeta, SourceLegendRow } from '../../services/marketMonitorApi';

// Colour carries the same three tiers everywhere: measured is unremarkable,
// partly-measured is worth a glance, unmeasured is worth stopping at. Failed
// and stale share the warning tier rather than getting a red of their own,
// because a red badge on a stale weekly source trains people to ignore reds.
const STATE_TONE: Record<DataState, string> = {
  healthy: 'text-slate-500 dark:text-gray-400',
  observed_zero: 'text-slate-500 dark:text-gray-400',
  partial: 'text-amber-700 dark:text-amber-400',
  stale: 'text-amber-700 dark:text-amber-400',
  collecting: 'text-sky-700 dark:text-sky-400',
  never_collected: 'text-slate-600 dark:text-gray-300',
  not_configured: 'text-slate-600 dark:text-gray-300',
  failed: 'text-red-700 dark:text-red-400',
};

const STATE_BG: Record<DataState, string> = {
  healthy: 'bg-slate-100 dark:bg-gray-700',
  observed_zero: 'bg-slate-100 dark:bg-gray-700',
  partial: 'bg-amber-50 dark:bg-amber-950',
  stale: 'bg-amber-50 dark:bg-amber-950',
  collecting: 'bg-sky-50 dark:bg-sky-950',
  never_collected: 'bg-slate-100 dark:bg-gray-700',
  not_configured: 'bg-slate-100 dark:bg-gray-700',
  failed: 'bg-red-50 dark:bg-red-950',
};

/** What to print where a figure would go.
 *
 *  Returns the number only when it is a measurement. An em dash is used for the
 *  unmeasured cases rather than a zero or a blank: blank reads as a rendering
 *  bug, zero reads as a fact.
 */
export function metricValue(meta: MetricMeta | null | undefined,
                            value: number | null | undefined): string {
  if (meta && !meta.measured) return '—';
  if (value === null || value === undefined) return '—';
  return value.toLocaleString();
}

export function DataStateBadge({ meta, className = '' }: {
  meta: MetricMeta | null | undefined; className?: string;
}) {
  if (!meta) return null;
  // A plain healthy measurement needs no badge. Labelling the normal case
  // makes the abnormal cases harder to spot, not easier.
  if (meta.data_state === 'healthy') return null;
  const state = meta.data_state;
  return (
    <span title={meta.state_detail ?? undefined}
          className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium
                      ${STATE_BG[state]} ${STATE_TONE[state]} ${className}`}>
      {meta.data_state_label}
    </span>
  );
}

/** The "What this means" control required on every metric header.
 *
 *  A popover rather than a tooltip, because the content includes the
 *  denominator, the provider, the last successful collection and the
 *  limitations, and a reader needs to be able to keep it open while looking at
 *  the chart behind it.
 */
export function MetricHelp({ meta }: { meta: MetricMeta | null | undefined }) {
  const [open, setOpen] = useState(false);
  if (!meta) return null;
  return (
    <span className="relative inline-block">
      <button type="button" onClick={() => setOpen(o => !o)}
              aria-expanded={open}
              aria-label={`What "${meta.label}" means`}
              className="ml-1.5 h-4 w-4 rounded-full border border-slate-300 dark:border-gray-600
                         text-[10px] leading-none text-slate-500 dark:text-gray-400
                         hover:bg-slate-100 dark:hover:bg-gray-700
                         focus:outline-none focus:ring-2 focus:ring-sky-500">
        ?
      </button>
      {open && (
        <>
          {/* Click-away target. Sits under the panel so the panel stays
              clickable, and covers the viewport so a stray click closes it. */}
          <span className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute z-50 mt-1 w-80 max-w-[85vw] rounded-lg border
                          border-slate-200 dark:border-gray-700 bg-white dark:bg-gray-800
                          p-3 text-left shadow-lg">
            <div className="text-xs font-semibold text-slate-800 dark:text-gray-100">
              {meta.label}
            </div>
            <p className="mt-1 text-[11px] leading-snug text-slate-600 dark:text-gray-300">
              {meta.definition}
            </p>

            <dl className="mt-2 space-y-1 text-[11px]">
              <Row label="Counts">{meta.numerator}</Row>
              {meta.denominator && <Row label="Out of">{meta.denominator}</Row>}
              {meta.window?.days != null && (
                <Row label="Period">the last {meta.window.days} days</Row>
              )}
              {meta.coverage && (
                <Row label="Collected">
                  {meta.coverage.label}
                  {meta.coverage.pct_of_eligible != null &&
                    ` (${meta.coverage.pct_of_eligible}%)`}
                </Row>
              )}
              {meta.freshness?.last_success_at && (
                <Row label="Last collected">
                  {new Date(meta.freshness.last_success_at).toLocaleString()}
                </Row>
              )}
              <Row label="State">
                {meta.data_state_label}
                {meta.state_detail ? ` — ${meta.state_detail}` : ''}
              </Row>
            </dl>

            {meta.sources.length > 0 && (
              <div className="mt-2 border-t border-slate-200 dark:border-gray-700 pt-2">
                <div className="text-[10px] font-semibold uppercase tracking-wide
                                text-slate-500 dark:text-gray-400">
                  Where it comes from
                </div>
                {meta.sources.map((s, i) => (
                  <div key={i} className="mt-1 text-[11px] text-slate-600 dark:text-gray-300">
                    {s.dataset} on {s.platform}, collected via {s.provider}
                    {' · '}{s.ownership}
                    {s.truncated && ' · provider limit reached'}
                  </div>
                ))}
              </div>
            )}

            {meta.limitations.length > 0 && (
              <div className="mt-2 border-t border-slate-200 dark:border-gray-700 pt-2">
                <div className="text-[10px] font-semibold uppercase tracking-wide
                                text-slate-500 dark:text-gray-400">
                  What it does not tell you
                </div>
                <ul className="mt-1 list-disc pl-4 text-[11px] text-slate-600 dark:text-gray-300">
                  {meta.limitations.map((l, i) => <li key={i}>{l}</li>)}
                </ul>
              </div>
            )}
          </div>
        </>
      )}
    </span>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2">
      <dt className="w-24 shrink-0 text-slate-500 dark:text-gray-400">{label}</dt>
      <dd className="text-slate-700 dark:text-gray-200">{children}</dd>
    </div>
  );
}

/** A metric header: title, the help control, and the state when it is not a
 *  plain measurement. Used so no panel has to remember the three of them. */
export function MetricHeading({ title, meta, className = '' }: {
  title: string; meta: MetricMeta | null | undefined; className?: string;
}) {
  return (
    <div className={`flex items-center gap-1.5 ${className}`}>
      <span className="text-sm font-medium text-slate-800 dark:text-gray-100">{title}</span>
      <MetricHelp meta={meta} />
      <DataStateBadge meta={meta} />
    </div>
  );
}

/** Shown in place of a chart when there is no defensible value to plot.
 *  Says which state it is in and what would change it. */
export function UnmeasuredNotice({ meta }: { meta: MetricMeta | null | undefined }) {
  if (!meta || meta.measured) return null;
  return (
    <div className="mt-2 rounded border border-dashed border-slate-300 dark:border-gray-600
                    p-3 text-xs text-slate-600 dark:text-gray-300">
      <div className="font-medium">{meta.data_state_label}</div>
      {meta.state_detail && <div className="mt-0.5">{meta.state_detail}</div>}
      <div className="mt-1 text-slate-500 dark:text-gray-400">
        No figure is shown because none was measured.
      </div>
    </div>
  );
}

/** The platform/provider/ownership table from the spec's source legend.
 *  Rendered from server data so the live page and the downloadable report
 *  cannot describe the same source two different ways. */
export function SourceLegend({ rows }: { rows: SourceLegendRow[] }) {
  if (!rows?.length) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="text-left text-slate-500 dark:text-gray-400">
            <th className="py-1 pr-3 font-medium">Content</th>
            <th className="py-1 pr-3 font-medium">Platform</th>
            <th className="py-1 pr-3 font-medium">Collected by</th>
            <th className="py-1 font-medium">Whose voice</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.key} className="border-t border-slate-100 dark:border-gray-700">
              <td className="py-1 pr-3 text-slate-700 dark:text-gray-200">{r.content}</td>
              <td className="py-1 pr-3 text-slate-600 dark:text-gray-300">{r.platform}</td>
              <td className="py-1 pr-3 text-slate-600 dark:text-gray-300">{r.provider}</td>
              <td className="py-1 text-slate-600 dark:text-gray-300">{r.ownership}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
