/**
 * Topics dashboard — single source of truth for which topics are tracked,
 * their lifecycle state, and the next action needed on each.
 *
 * Reads /api/forecast/topics which merges metadata + delivery + latest
 * assessment per topic so the table doesn't need N round trips.
 *
 * Row click switches the parent topic selector to that topic and jumps
 * to the Forecast Tracker tab — no UX regression from the existing
 * AllTopicsForecastView grid.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Loader2, Plus, RefreshCw, AlertTriangle, CheckCircle2, MinusCircle,
  ChevronRight, Tag, User,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

interface TopicRow {
  topic: string;
  display_name: string | null;
  description: string | null;
  owner: string | null;
  status: 'draft' | 'active' | 'archived';
  tags: string[] | null;
  overlay_status: 'missing' | 'auto_generated' | 'human_reviewed';
  created_at: string | null;
  updated_at: string | null;
  cadence: 'monthly' | 'quarterly' | 'none' | null;
  recipient_email: string | null;
  last_delivered_at: string | null;
  assessment_id: string | null;
  assessed_at: string | null;
  evidence_count: number | null;
  scenarios_count: number | null;
  surprises: any;
  summary: any;
}

interface Props {
  onSelectTopic?: (topic: string) => void;
  onAddTopic?: () => void;
}

type Health = 'green' | 'amber' | 'red';

function daysSince(iso: string | null): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / (1000 * 60 * 60 * 24));
}

function computeHealth(r: TopicRow): { dot: Health; reason: string } {
  if (r.status === 'archived') return { dot: 'amber', reason: 'Archived — excluded from bundles' };
  if (!r.assessment_id) return { dot: 'red', reason: 'No assessment yet — run paired assessment to track' };
  if (r.overlay_status === 'missing') return { dot: 'red', reason: 'No deck overlay — bundle will warn' };
  const d = daysSince(r.assessed_at);
  if (d === null) return { dot: 'amber', reason: 'Assessment date missing' };
  if (d > 90) return { dot: 'red', reason: `Last assessed ${d}d ago — stale` };
  if (d > 30) return { dot: 'amber', reason: `Last assessed ${d}d ago` };
  if (r.overlay_status === 'auto_generated') return { dot: 'amber', reason: 'Overlay auto-generated — pending human review' };
  if (!r.cadence || r.cadence === 'none') return { dot: 'amber', reason: 'No delivery cadence set' };
  return { dot: 'green', reason: 'Healthy — fresh assessment, reviewed overlay, cadence set' };
}

const STATUS_BADGE: Record<TopicRow['status'], string> = {
  draft:    'bg-amber-100 text-amber-900 dark:bg-amber-800/50 dark:text-amber-100',
  active:   'bg-emerald-100 text-emerald-900 dark:bg-emerald-800/50 dark:text-emerald-100',
  archived: 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-200',
};

const OVERLAY_BADGE: Record<TopicRow['overlay_status'], string> = {
  missing:        'bg-red-100 text-red-900 dark:bg-red-800/50 dark:text-red-100',
  auto_generated: 'bg-amber-100 text-amber-900 dark:bg-amber-800/50 dark:text-amber-100',
  human_reviewed: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-800/50 dark:text-emerald-100',
};

const HEALTH_DOT: Record<Health, string> = {
  green: 'bg-emerald-500',
  amber: 'bg-amber-500',
  red:   'bg-red-500',
};

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '—';
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  } catch {
    return '—';
  }
}

export function TopicsDashboard({ onSelectTopic, onAddTopic }: Props) {
  const [topics, setTopics] = useState<TopicRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<'all' | 'draft' | 'active' | 'archived'>('active');
  const [search, setSearch] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/forecast/topics');
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const data = await r.json();
      setTopics((data.topics || []) as TopicRow[]);
    } catch (e: any) {
      setError(e?.message || 'Failed to load topics');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const filtered = useMemo(() => {
    let rows = topics || [];
    if (statusFilter !== 'all') rows = rows.filter(r => r.status === statusFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter(r =>
        (r.display_name || r.topic).toLowerCase().includes(q) ||
        (r.owner || '').toLowerCase().includes(q) ||
        (r.tags || []).some(t => (t || '').toLowerCase().includes(q))
      );
    }
    return rows;
  }, [topics, statusFilter, search]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Topics</h2>
          <p className="text-xs text-gray-600 dark:text-gray-300 mt-0.5">
            {topics?.length ?? 0} total · click a row to drill into its Forecast Tracker view
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <input
            type="text"
            placeholder="Search topic, owner, tag…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as any)}
            className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100"
          >
            <option value="active">Active</option>
            <option value="draft">Draft</option>
            <option value="archived">Archived</option>
            <option value="all">All</option>
          </select>
          <button
            type="button"
            onClick={refresh}
            className="inline-flex items-center text-xs px-2 py-1 border border-gray-300 dark:border-gray-700 rounded text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <RefreshCw className="w-3 h-3 mr-1" /> Refresh
          </button>
          <Button
            type="button"
            onClick={onAddTopic}
            className="text-xs bg-pink-600 hover:bg-pink-700 text-white h-7 py-0 px-3"
          >
            <Plus className="w-3 h-3 mr-1" /> Add topic
          </Button>
        </div>
      </div>

      {error && (
        <div className="text-xs bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 rounded p-2">
          {error}
        </div>
      )}

      {loading && !topics ? (
        <div className="flex items-center text-xs text-gray-600 dark:text-gray-300">
          <Loader2 className="w-3 h-3 mr-2 animate-spin" /> Loading topics…
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-xs text-gray-600 dark:text-gray-300 italic p-6 border border-dashed border-gray-300 dark:border-gray-700 rounded text-center">
          No topics match. Try "All" status or add one.
        </div>
      ) : (
        <div className="overflow-x-auto border border-gray-200 dark:border-gray-700 rounded">
          <table className="min-w-full text-xs">
            <thead className="bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
              <tr>
                <Th>Health</Th>
                <Th>Topic</Th>
                <Th>Owner</Th>
                <Th>Tags</Th>
                <Th>Last assessed</Th>
                <Th>Cadence</Th>
                <Th>Last delivered</Th>
                <Th>Overlay</Th>
                <Th>Status</Th>
                <Th>{''}</Th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-800">
              {filtered.map(r => {
                const h = computeHealth(r);
                const days = daysSince(r.assessed_at);
                const daysDeliv = daysSince(r.last_delivered_at);
                return (
                  <tr
                    key={r.topic}
                    onClick={() => onSelectTopic && onSelectTopic(r.topic)}
                    className="hover:bg-gray-50 dark:hover:bg-gray-800/60 cursor-pointer"
                  >
                    <Td><span className={`inline-block w-2.5 h-2.5 rounded-full ${HEALTH_DOT[h.dot]}`} title={h.reason} /></Td>
                    <Td>
                      <div className="font-medium text-gray-900 dark:text-gray-100">{r.display_name || r.topic}</div>
                      {r.description && (
                        <div className="text-[10px] text-gray-500 dark:text-gray-400 line-clamp-1 max-w-xs">{r.description}</div>
                      )}
                    </Td>
                    <Td>
                      {r.owner ? (
                        <span className="inline-flex items-center gap-1 text-gray-700 dark:text-gray-200">
                          <User className="w-3 h-3" /> {r.owner}
                        </span>
                      ) : <span className="text-gray-400">—</span>}
                    </Td>
                    <Td>
                      {(r.tags || []).slice(0, 3).map(t => (
                        <span key={t} className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 mr-1 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200">
                          <Tag className="w-2.5 h-2.5" /> {t}
                        </span>
                      ))}
                      {(r.tags || []).length === 0 && <span className="text-gray-400">—</span>}
                    </Td>
                    <Td>
                      <div className="text-gray-700 dark:text-gray-200">{fmtDate(r.assessed_at)}</div>
                      {days !== null && (
                        <div className={`text-[10px] ${days > 90 ? 'text-red-600' : days > 30 ? 'text-amber-600' : 'text-gray-500'}`}>
                          {days}d ago
                        </div>
                      )}
                    </Td>
                    <Td>
                      <span className="capitalize text-gray-700 dark:text-gray-200">{r.cadence || 'none'}</span>
                      {r.recipient_email && (
                        <div className="text-[10px] text-gray-500 dark:text-gray-400 line-clamp-1">{r.recipient_email}</div>
                      )}
                    </Td>
                    <Td>
                      <div className="text-gray-700 dark:text-gray-200">{fmtDate(r.last_delivered_at)}</div>
                      {daysDeliv !== null && (
                        <div className="text-[10px] text-gray-500 dark:text-gray-400">{daysDeliv}d ago</div>
                      )}
                    </Td>
                    <Td>
                      <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${OVERLAY_BADGE[r.overlay_status]}`}>
                        {r.overlay_status.replace(/_/g, ' ')}
                      </span>
                    </Td>
                    <Td>
                      <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${STATUS_BADGE[r.status]}`}>
                        {r.status}
                      </span>
                    </Td>
                    <Td>
                      <ChevronRight className="w-3 h-3 text-gray-400" />
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Th({ children }: { children: any }) {
  return <th className="text-left font-medium px-3 py-2 whitespace-nowrap">{children}</th>;
}
function Td({ children }: { children: any }) {
  return <td className="px-3 py-2 align-top">{children}</td>;
}
