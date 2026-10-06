/**
 * Brand Watcher — coverage split for one brand.
 *
 * Shows how the brand topic's articles were classified under the brand
 * labels (docs/BRAND_RELEVANCE_SPEC.md): earned coverage, the brand's own
 * content, sector stories, passing mentions and the rest, each counted once.
 * Selecting a bucket lists its articles with the reason for the decision,
 * the name that matched and where, and whether only the headline was known.
 * Missing measurements show as unavailable, never as zero.
 */

import { useEffect, useState } from 'react';
import { Loader2, Info } from 'lucide-react';
import { getCoverageSplit, BWCoverageBucket, BWCoverageSplit, Brand } from '../../services/brandWatcherApi';

const BUCKETS: { key: BWCoverageBucket; label: string; hint: string }[] = [
  { key: 'earned', label: 'Earned coverage', hint: 'Independent sources where the brand is the subject or plays a real part. Only these count in metrics and alerts.' },
  { key: 'owned', label: "Brand's own content", hint: "Published on the brand's own sites. Shown here, never counted as press." },
  { key: 'sector', label: 'Sector stories', hint: "About the brand's market without the brand playing a part. Not counted as brand coverage." },
  { key: 'passing', label: 'Passing mentions', hint: 'The brand is named only in passing.' },
  { key: 'other', label: 'Not coverage', hint: 'Unrelated, a different company with the same name, a deal listing or a valuation page.' },
  { key: 'deferred', label: 'Waiting', hint: 'Not decided yet: the company identity or the publisher could not be settled.' },
  { key: 'unavailable', label: 'Judgment unavailable', hint: 'The model did not answer. The article stays in the queue and is retried.' },
  { key: 'unlabelled', label: 'Decided before labels', hint: 'Decided under the earlier scoring. Not reclassified automatically.' },
  { key: 'invalid', label: 'Invalid label', hint: 'A stored label outside the allowed set. Not counted; needs repair.' },
];

const FIELD_LABEL: Record<string, string> = { title: 'headline', summary: 'summary', text: 'article text' };

interface Props {
  brand: Brand | undefined;
  daysBack: number;
}

export function BrandWatcherCoverage({ brand, daysBack }: Props) {
  const [split, setSplit] = useState<BWCoverageSplit | null>(null);
  const [bucket, setBucket] = useState<BWCoverageBucket | null>(null);
  const [rows, setRows] = useState<BWCoverageSplit['rows']>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!brand) return;
    let cancelled = false;
    setLoading(true); setError(null); setBucket(null); setRows([]);
    getCoverageSplit(brand.id, daysBack)
      .then(s => { if (!cancelled) setSplit(s); })
      .catch(e => { if (!cancelled) setError(String(e.message || e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [brand?.id, daysBack]);

  useEffect(() => {
    if (!brand || !bucket) return;
    let cancelled = false;
    getCoverageSplit(brand.id, daysBack, bucket)
      .then(s => { if (!cancelled) setRows(s.rows); })
      .catch(e => { if (!cancelled) setError(String(e.message || e)); });
    return () => { cancelled = true; };
  }, [brand?.id, daysBack, bucket]);

  if (!brand) return null;
  if (loading) {
    return <div className="flex items-center gap-2 text-xs text-gray-500"><Loader2 className="w-3 h-3 animate-spin" />Loading coverage breakdown…</div>;
  }
  if (error) {
    return <div className="text-xs text-gray-500">Coverage breakdown unavailable: {error}</div>;
  }
  if (!split) return null;
  if (!split.available) {
    return <div className="text-xs text-gray-500">Coverage breakdown unavailable: {split.reason}</div>;
  }
  const present = BUCKETS.filter(b => (split.counts[b.key] || 0) > 0);
  if (present.length === 0) {
    return <div className="text-xs text-gray-500">No brand-topic articles were decided for {brand.display_name} in this window.</div>;
  }
  const onlyLegacy = present.length === 1 && present[0].key === 'unlabelled';

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-2">
      <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-200">
        Coverage breakdown for {brand.display_name}
        <span title={split.note || ''}><Info className="w-3.5 h-3.5 text-gray-400" /></span>
      </div>
      {onlyLegacy && (
        <div className="text-xs text-gray-500">
          These articles were decided before brand labels existed. New articles get a breakdown as they arrive.
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {present.map(b => {
          const active = bucket === b.key;
          return (
            <button key={b.key} title={b.hint} onClick={() => setBucket(active ? null : b.key)}
              className={`px-3 py-1 text-xs rounded-full border transition-colors ${active
                ? 'bg-blue-100 dark:bg-blue-900/30 border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300'
                : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50'}`}>
              {b.label} ({split.counts[b.key]})
            </button>
          );
        })}
      </div>
      {bucket && (
        <ul className="divide-y divide-gray-100 dark:divide-gray-700">
          {rows.length === 0 && <li className="py-2 text-xs text-gray-500">No articles in this bucket.</li>}
          {rows.map(r => (
            <li key={r.uri} className="py-2 text-sm">
              <a href={r.uri} target="_blank" rel="noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline">
                {r.title || r.uri}
              </a>
              <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                {r.source && <span>{r.source}</span>}
                {r.source_relation === 'owned' && <span className="px-1.5 rounded bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300">brand's own site</span>}
                {r.source_relation === 'unknown' && <span className="px-1.5 rounded bg-gray-100 dark:bg-gray-700">publisher unknown</span>}
                {r.limited_evidence && <span className="px-1.5 rounded bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300">headline only</span>}
                {r.matched && <span>named as “{r.matched}” in the {FIELD_LABEL[r.evidence_field || ''] || r.evidence_field || 'text'}</span>}
              </div>
              {r.reason && <div className="mt-0.5 text-xs text-gray-600 dark:text-gray-400">{r.reason}</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
