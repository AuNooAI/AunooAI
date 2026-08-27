/**
 * Top voices: the outside accounts posting about this market.
 *
 * Its own tab. It sat at the bottom of Analysis, after a dozen panels about
 * the vendors, and a reader asking "who is driving this conversation" had to
 * scroll past hiring charts to find out. The data is the same ``/voices``
 * call; the table is the one that was on Analysis.
 */

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { getTopVoices, type TopVoices } from '../../services/marketMonitorApi';
import { DataTable } from './DataTable';
import { CoverageLine, Panel } from './MarketAnalysisView';
import type { DrilldownSpec } from './MarketDrilldownHost';

export function MarketVoicesView({ marketId, days, onRecords }: {
  marketId: number;
  days?: number;
  onRecords?: (spec: DrilldownSpec) => void;
}) {
  const [voices, setVoices] = useState<TopVoices | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setVoices(null);
    setError(null);
    getTopVoices(marketId, days, 50)
      .then(v => { if (live) setVoices(v); })
      .catch(e => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [marketId, days]);

  if (error) {
    return <div className="text-sm text-red-600 dark:text-red-400">{error}</div>;
  }

  return (
    <div className="space-y-4">
        <Panel title="Top voices">
          {voices ? (
            <>
              <CoverageLine
                coverage={voices.coverage}
                note="Accounts posting about the market. Vendors' own company posts are excluded — they are counted under Analysis." />
              <DataTable
                rows={voices.voices}
                rowKey={v => `${v.platform}:${v.author}`}
                initialSort="engagement" initialDir="desc"
                columns={[
                  { key: 'author', label: 'Account', groupable: false,
                    // Opens every relevant post by this account. A ranked
                    // handle whose posts cannot be read is an assertion.
                    render: v => onRecords ? (
                      <button
                        onClick={e => { e.stopPropagation();
                                        onRecords({
                                          kind: 'voice',
                                          title: `@${v.author}: posts about this market`,
                                          author: v.author, days,
                                          expectedTotal: v.posts,
                                        }); }}
                        className="text-sky-700 dark:text-sky-400 hover:underline">
                        @{v.author}
                      </button>
                    ) : `@${v.author}` },
                  { key: 'platform', label: 'Platform', groupable: true },
                  // A ranked list of handles with no subject is a list of
                  // strangers. What they talk about is the useful part.
                  { key: 'about', label: 'Talking about', sortable: false,
                    // Capped, or an account naming a dozen terms and
                    // vendors pushes its row tall enough that the table
                    // becomes an endless scroll instead of a scan.
                    render: v => {
                      const terms = v.terms.slice(0, 4);
                      const vendors = v.vendors.slice(0, 3);
                      const extra = (v.terms.length - terms.length)
                        + (v.vendors.length - vendors.length);
                      return (
                        <span className="flex flex-wrap gap-1">
                          {terms.length === 0 && vendors.length === 0 && (
                            <span className="text-slate-400 dark:text-gray-500">—</span>)}
                          {terms.map(t => (
                            <span key={t.term}
                                  className="text-xs px-1 py-0.5 rounded border
                                             bg-slate-50 text-slate-600 dark:bg-gray-700 dark:text-gray-400">
                              {t.term}
                            </span>
                          ))}
                          {vendors.map(x => (
                            <span key={x.vendor}
                                  className="text-xs px-1 py-0.5 rounded border
                                             bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-900/20 dark:text-sky-400 dark:border-sky-800">
                              {x.vendor}
                            </span>
                          ))}
                          {extra > 0 && (
                            <span className="text-xs text-slate-400 dark:text-gray-500">+{extra} more</span>
                          )}
                        </span>
                      );
                    } },
                  { key: 'posts', label: 'Posts', align: 'right' },
                  { key: 'engagement', label: 'Reactions', align: 'right' },
                  { key: 'last_seen', label: 'Last seen', align: 'right',
                    render: v => (v.last_seen ?? '').slice(0, 10) || '—' },
                ]} />
            </>
          ) : (
            <div className="py-10 text-center text-slate-400 dark:text-gray-500">
              <Loader2 className="w-4 h-4 animate-spin mx-auto" />
            </div>
          )}
        </Panel>
    </div>
  );
}
