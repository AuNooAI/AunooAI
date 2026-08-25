/**
 * "Not enough data yet" — one shared collapsible for every panel on this
 * page that didn't clear its own sample-size floor.
 *
 * Before this, a thin panel either drew its chart anyway (a two-point flat
 * line, a percentage of nine mentions) or wrote its own bespoke placeholder
 * paragraph with its own wording and its own threshold. Both make a market
 * with real gaps in its data look wrong, or make the reader read five
 * near-identical "not enough data" paragraphs at full panel size to learn
 * nothing five times over. This collapses all of them into one line each,
 * in one place, naming the instrument and what it's waiting for.
 */

export interface DataConfidence {
  /** Sample size actually available. */
  n: number;
  /** The floor `n` needs to clear. */
  min: number;
  ok: boolean;
}

/** `n >= min` — the floor a panel's own data has to clear before it draws a
 *  chart instead of folding into the shared strip below. */
export function useDataConfidence(n: number, min: number): DataConfidence {
  return { n, min, ok: n >= min };
}

export interface ThinPanel {
  /** Stable key — panel name is fine, this list is never long enough to
   *  need anything else. */
  id: string;
  /** The instrument's name, as it would read as a panel title. */
  title: string;
  /** What it measures, one sentence. */
  why: string;
  /** How far short of the floor it is, in the same units a reader would use
   *  to judge for themselves — "2 of 6 weeks read", not "insufficient n". */
  need: string;
}

export function ConfidenceGate({ panels }: { panels: ThinPanel[] }) {
  if (panels.length === 0) return null;
  return (
    <details className="border border-dashed rounded-lg bg-slate-50 dark:bg-gray-800
                         border-slate-300 dark:border-gray-600 mt-4">
      <summary className="px-4 py-3 cursor-pointer list-none flex items-center
                           justify-between gap-3 flex-wrap">
        <span className="text-sm font-medium text-slate-800 dark:text-gray-100
                          flex items-center gap-2">
          Not enough data yet
          <span className="text-xs font-normal text-slate-500 dark:text-gray-400
                            border border-slate-300 dark:border-gray-600 rounded-full
                            px-2 py-0.5">
            {panels.length} panel{panels.length === 1 ? '' : 's'}
          </span>
        </span>
        <span className="text-xs text-slate-500 dark:text-gray-400">
          expand ↓
        </span>
      </summary>
      <div className="px-4 pb-3 divide-y divide-slate-200 dark:divide-gray-700">
        {panels.map(p => (
          <div key={p.id}
               className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-2.5">
            <span className="font-medium text-sm text-slate-800 dark:text-gray-100
                              min-w-[180px] flex-1 basis-[180px]">
              {p.title}
            </span>
            <span className="text-sm text-slate-600 dark:text-gray-400 flex-[2] basis-[280px]">
              {p.why}
            </span>
            <span className="text-xs text-amber-700 dark:text-amber-400
                              whitespace-nowrap font-medium">
              {p.need}
            </span>
          </div>
        ))}
      </div>
    </details>
  );
}
