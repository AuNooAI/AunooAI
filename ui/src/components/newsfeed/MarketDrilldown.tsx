/**
 * The records behind a number.
 *
 * One component for every list, because every list endpoint returns the same
 * envelope. The alternative -- a bespoke panel per figure -- is how the
 * pagination ends up implemented five times and wrong in two of them.
 *
 * Three things are always on screen, and each exists because its absence was a
 * real defect:
 *
 *   the true total, from the server, not the number of rows on this page;
 *   the filters the server actually applied, so a reader can see the list is
 *     the one the card opened rather than a similar one;
 *   the metric's state, so an empty list says whether it is empty because
 *     nothing matched or because nothing was collected.
 */

import React, { useCallback, useEffect, useState } from 'react';
import type { ListEnvelope } from '../../services/marketMonitorApi';
import { MetricHelp, DataStateBadge, UnmeasuredNotice } from './MarketMetric';

export interface DrilldownColumn<T> {
  key: string;
  label: string;
  align?: 'left' | 'right';
  /** Rendered cell. Falls back to the raw value when omitted. */
  render?: (row: T) => React.ReactNode;
  /** Hidden on narrow screens, for detail that is not the point of the row. */
  secondary?: boolean;
}

interface Props<T> {
  title: string;
  /** Fetches one page. Re-created by the caller when the filters change, so a
   *  filter change reloads rather than silently paging a stale query. */
  fetchPage: (page: number) => Promise<ListEnvelope<T>>;
  columns: DrilldownColumn<T>[];
  rowKey: (row: T, index: number) => string;
  onRowClick?: (row: T) => void;
  /** Direct CSV link. Uses the same server-side filters and authorization. */
  csvUrl?: string;
  /** What the aggregate said. Shown beside the list total so a disagreement is
   *  visible rather than something a reader has to notice. */
  expectedTotal?: number;
  onClose?: () => void;
  emptyMessage?: string;
}

export function MarketDrilldown<T>({
  title, fetchPage, columns, rowKey, onRowClick, csvUrl, expectedTotal,
  onClose, emptyMessage,
}: Props<T>) {
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<ListEnvelope<T> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // fetchPage identity is the cache key: a caller that rebuilds it on a filter
  // change gets a reload, and page resets to 1 so the reader is not left on
  // page 7 of a different list.
  useEffect(() => { setPage(1); }, [fetchPage]);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    fetchPage(page)
      .then(r => { if (live) setResult(r); })
      .catch(e => { if (live) setError(String(e?.message ?? e)); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [fetchPage, page]);

  const pag = result?.meta.pagination;
  const meta = result?.meta.metric ?? null;
  const filters = result?.meta.applied_filters ?? {};
  const disagrees = expectedTotal !== undefined && pag
                    && pag.total !== expectedTotal;

  return (
    <div className="border rounded-lg bg-white dark:bg-gray-800">
      <div className="flex items-start justify-between gap-3 p-3 border-b
                      border-slate-200 dark:border-gray-700">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium text-slate-800 dark:text-gray-100">
              {title}
            </span>
            <MetricHelp meta={meta} />
            <DataStateBadge meta={meta} />
          </div>
          <div className="mt-0.5 text-xs text-slate-500 dark:text-gray-400 tabular-nums">
            {pag ? (
              <>
                {pag.total.toLocaleString()} record{pag.total === 1 ? '' : 's'}
                {pag.pages > 1 && ` · page ${pag.page} of ${pag.pages}`}
              </>
            ) : loading ? 'loading…' : ''}
          </div>
          {Object.keys(filters).length > 0 && (
            /* The server's own account of what it filtered on. Shown rather
               than the parameters we sent, so a filter the server ignored
               cannot pass unnoticed. */
            <div className="mt-1 flex flex-wrap gap-1">
              {Object.entries(filters).map(([k, v]) => (
                <span key={k}
                      className="rounded bg-slate-100 dark:bg-gray-700 px-1.5 py-0.5
                                 text-[10px] text-slate-600 dark:text-gray-300">
                  {k.replace(/_/g, ' ')}: {String(v)}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {csvUrl && (
            <a href={csvUrl}
               className="text-xs text-sky-700 dark:text-sky-400 hover:underline">
              CSV
            </a>
          )}
          {onClose && (
            <button onClick={onClose} aria-label="Close"
                    className="text-slate-400 hover:text-slate-600
                               dark:hover:text-gray-200 text-sm px-1">
              ✕
            </button>
          )}
        </div>
      </div>

      {disagrees && (
        /* Loud on purpose. If the list and the card disagree, one of them is
           wrong and a reader is entitled to know before quoting either. */
        <div className="mx-3 mt-3 rounded border border-amber-300 dark:border-amber-800
                        bg-amber-50 dark:bg-amber-950 p-2 text-xs
                        text-amber-800 dark:text-amber-300">
          This list holds {pag!.total.toLocaleString()} records but the figure
          that opened it said {expectedTotal!.toLocaleString()}. The filters may
          not match — treat both numbers as unconfirmed.
        </div>
      )}

      {result && result.meta.notes.length > 0 && (
        <div className="mx-3 mt-3 rounded border border-slate-200 dark:border-gray-700
                        p-2 text-xs text-slate-600 dark:text-gray-300">
          {result.meta.notes.map((n, i) => <div key={i}>{n}</div>)}
        </div>
      )}

      {error && (
        <p className="p-3 text-sm text-red-700 dark:text-red-400">{error}</p>
      )}

      {!error && result && result.data.length === 0 && (
        <div className="p-3">
          {meta && !meta.measured ? (
            /* An empty list from a source that never ran is not an empty
               result. */
            <UnmeasuredNotice meta={meta} />
          ) : (
            <p className="text-sm text-slate-500 dark:text-gray-400">
              {emptyMessage ?? 'Nothing matched these filters.'}
            </p>
          )}
        </div>
      )}

      {!error && result && result.data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500 dark:text-gray-400">
                {columns.map(c => (
                  <th key={c.key}
                      className={`px-3 py-2 font-medium whitespace-nowrap
                                  ${c.align === 'right' ? 'text-right' : ''}
                                  ${c.secondary ? 'hidden md:table-cell' : ''}`}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.data.map((row, i) => (
                <tr key={rowKey(row, i)}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    className={`border-t border-slate-100 dark:border-gray-700
                                ${onRowClick ? 'cursor-pointer hover:bg-slate-50 '
                                             + 'dark:hover:bg-gray-700' : ''}`}>
                  {columns.map(c => (
                    <td key={c.key}
                        className={`px-3 py-2 align-top
                                    ${c.align === 'right'
                                      ? 'text-right tabular-nums' : ''}
                                    ${c.secondary ? 'hidden md:table-cell' : ''}`}>
                      {c.render
                        ? c.render(row)
                        : String((row as Record<string, unknown>)[c.key] ?? '—')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pag && pag.pages > 1 && (
        <div className="flex items-center justify-between gap-2 p-3 border-t
                        border-slate-200 dark:border-gray-700">
          <button disabled={page <= 1 || loading}
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  className="text-xs px-2 py-1 rounded border
                             border-slate-300 dark:border-gray-600
                             disabled:opacity-40 disabled:cursor-not-allowed
                             text-slate-700 dark:text-gray-200">
            Previous
          </button>
          <span className="text-xs text-slate-500 dark:text-gray-400 tabular-nums">
            {loading ? 'loading…'
                     : `${(pag.page - 1) * pag.page_size + 1}–${
                          Math.min(pag.page * pag.page_size, pag.total)
                        } of ${pag.total.toLocaleString()}`}
          </span>
          <button disabled={!pag.has_more || loading}
                  onClick={() => setPage(p => p + 1)}
                  className="text-xs px-2 py-1 rounded border
                             border-slate-300 dark:border-gray-600
                             disabled:opacity-40 disabled:cursor-not-allowed
                             text-slate-700 dark:text-gray-200">
            Next
          </button>
        </div>
      )}
    </div>
  );
}

/** Shared cell renderers, so a date or a link looks the same in every list. */
export const cell = {
  date(value: string | null | undefined): string {
    if (!value) return '—';
    return String(value).slice(0, 10);
  },
  link(url: string | null | undefined, label: string | null | undefined) {
    const text = label || url || '—';
    if (!url) return <span>{text}</span>;
    return (
      <a href={url} target="_blank" rel="noopener noreferrer"
         onClick={e => e.stopPropagation()}
         className="text-sky-700 dark:text-sky-400 hover:underline">
        {text}
      </a>
    );
  },
  excerpt(value: string | null | undefined, chars = 160) {
    if (!value) return <span className="text-slate-400">—</span>;
    const trimmed = value.length > chars ? `${value.slice(0, chars)}…` : value;
    return <span className="text-slate-600 dark:text-gray-300">{trimmed}</span>;
  },
  number(value: number | null | undefined): string {
    return value === null || value === undefined
      ? '—' : value.toLocaleString();
  },
};

/** The four job states, in words. `first_observation` is deliberately not
 *  "new": with one run of history there is no earlier state to have been absent
 *  from, so calling it new would be a claim about a change we cannot see. */
export const JOB_STATUS_LABELS: Record<string, string> = {
  currently_observed: 'currently observed',
  newly_observed: 'newly observed',
  no_longer_observed: 'no longer observed',
  first_observation: 'first observation',
};

/** Which collector found a listing. Named for what a reader recognises: the
 *  company's own hiring system, rather than the internal source key. */
export const JOB_SOURCE_LABELS: Record<string, string> = {
  linkedin_jobs: 'LinkedIn',
  ats_jobs: "the company's own board",
};
