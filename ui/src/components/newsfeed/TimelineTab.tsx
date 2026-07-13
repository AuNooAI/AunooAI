/**
 * Timeline Tab — per-brand / per-topic mementos.
 *
 * A memento is one concrete, dated development on a scope's timeline
 * (timeline_events). Recurring stories bump one memento's occurrence count
 * instead of repeating; weekly/monthly rollups absorb dailies. This tab is
 * the monolith port of the saas /timeline page.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Loader2,
  RefreshCw,
  AlertCircle,
  CalendarDays,
  Layers,
  ExternalLink,
  Sparkles,
  Pin,
  Trash2,
} from 'lucide-react';

const BASE = '/api/timeline';

interface TimelineScope {
  scope_type: 'topic' | 'brand';
  scope_id: string;
  label: string;
  event_count: number;
  latest_event_date: string | null;
}

interface TimelineEvent {
  id: number;
  event_type: string;
  event_subtype: string | null;
  title: string;
  description: string | null;
  significance: 'low' | 'medium' | 'high' | 'critical';
  event_data: Record<string, any>;
  entities: string[];
  article_uris: string[];
  article_count: number;
  event_date: string;
  last_seen_date: string | null;
  occurrence_count: number;
  granularity: string;
}

interface TimelineSummary {
  label: string;
  state_doc: {
    summary: string;
    key_entities: string[];
    current_trend: string | null;
    generated_at: string | null;
  } | null;
  monthly: TimelineEvent[];
  weekly: TimelineEvent[];
  analyst_notes: TimelineEvent[];
  daily: TimelineEvent[];
}

const SIG_COLORS: Record<string, string> = {
  critical: 'bg-red-100 text-red-800 border-red-300',
  high: 'bg-orange-100 text-orange-800 border-orange-300',
  medium: 'bg-blue-100 text-blue-800 border-blue-300',
  low: 'bg-gray-100 text-gray-600 border-gray-300',
};

const TYPE_LABELS: Record<string, string> = {
  new_development: 'Development',
  volume_spike: 'Coverage spike',
  sentiment_shift: 'Sentiment shift',
  source_shift: 'New sources',
  story_emergence: 'Syndicated story',
  risk_finding: 'Risk finding',
  alert: 'Alert',
  analyst_note: 'Analyst note',
};

function EventCard({ evt }: { evt: TimelineEvent }) {
  const [open, setOpen] = useState(false);
  const links = (evt.article_uris || []).filter(u => u && u.startsWith('http'));
  return (
    <div className="border border-gray-200 rounded-lg p-3 bg-white hover:shadow-sm transition-shadow">
      <div className="flex items-start gap-2 cursor-pointer" onClick={() => setOpen(!open)}>
        <span className={`text-xs px-2 py-0.5 rounded border whitespace-nowrap ${SIG_COLORS[evt.significance] || SIG_COLORS.medium}`}>
          {TYPE_LABELS[evt.event_type] || evt.event_type}
        </span>
        <div className="flex-1 min-w-0">
          <div className="font-medium text-sm text-gray-900">{evt.title}</div>
          <div className="text-xs text-gray-500 mt-0.5 flex items-center gap-2 flex-wrap">
            <span>{evt.event_date}</span>
            {evt.occurrence_count > 1 && (
              <span className="px-1.5 py-0.5 bg-amber-50 text-amber-700 border border-amber-200 rounded"
                    title={`First seen ${evt.event_date}, last seen ${evt.last_seen_date}`}>
                ongoing · seen {evt.occurrence_count}×
              </span>
            )}
            {evt.article_count > 1 && <span>{evt.article_count} articles</span>}
            {(evt.entities || []).slice(0, 3).map(e => (
              <span key={e} className="px-1.5 py-0.5 bg-gray-50 border border-gray-200 rounded">{e}</span>
            ))}
          </div>
        </div>
      </div>
      {open && (
        <div className="mt-2 pl-1 text-sm text-gray-700 space-y-2">
          {evt.description && <p>{evt.description}</p>}
          {Array.isArray(evt.event_data?.key_developments) && evt.event_data.key_developments.length > 0 && (
            <ul className="list-disc pl-5 text-xs text-gray-600">
              {evt.event_data.key_developments.map((k: string, i: number) => <li key={i}>{k}</li>)}
            </ul>
          )}
          {links.length > 0 && (
            <div className="space-y-1">
              {links.slice(0, 5).map(u => (
                <a key={u} href={u} target="_blank" rel="noopener noreferrer"
                   className="flex items-center gap-1 text-xs text-blue-600 hover:underline truncate">
                  <ExternalLink className="w-3 h-3 shrink-0" />{u}
                </a>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function TimelineTab() {
  const [scopes, setScopes] = useState<TimelineScope[]>([]);
  const [selected, setSelected] = useState<TimelineScope | null>(null);
  const [summary, setSummary] = useState<TimelineSummary | null>(null);
  const [allEvents, setAllEvents] = useState<TimelineEvent[] | null>(null);
  const [view, setView] = useState<'summary' | 'daily' | 'weekly' | 'monthly'>('summary');
  const [loading, setLoading] = useState(true);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [noteFormOpen, setNoteFormOpen] = useState(false);
  const [noteTitle, setNoteTitle] = useState('');
  const [noteBody, setNoteBody] = useState('');
  const [savingNote, setSavingNote] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${BASE}/scopes`, { credentials: 'include' });
        if (!res.ok) throw new Error(`scopes: HTTP ${res.status}`);
        const data = await res.json();
        const s: TimelineScope[] = data.scopes || [];
        setScopes(s);
        // Default to the scope with the most mementos, else first brand.
        const best = [...s].sort((a, b) => (b.event_count || 0) - (a.event_count || 0))[0];
        if (best) setSelected(best);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load scopes');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const loadScope = useCallback(async (scope: TimelineScope, granularity?: string) => {
    setLoadingSummary(true);
    setError(null);
    try {
      const p = new URLSearchParams({ scope_type: scope.scope_type, scope_id: scope.scope_id });
      if (granularity && granularity !== 'summary') {
        const res = await fetch(`${BASE}/events?${p}&granularity=${granularity}&include_stale=true&limit=100`,
          { credentials: 'include' });
        if (!res.ok) throw new Error(`events: HTTP ${res.status}`);
        setAllEvents((await res.json()).events || []);
      } else {
        const res = await fetch(`${BASE}/summary?${p}`, { credentials: 'include' });
        if (!res.ok) throw new Error(`summary: HTTP ${res.status}`);
        setSummary(await res.json());
        setAllEvents(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load timeline');
    } finally {
      setLoadingSummary(false);
    }
  }, []);

  useEffect(() => {
    if (selected) loadScope(selected, view);
  }, [selected, view, loadScope]);

  const handleGenerate = async () => {
    if (!selected || generating) return;
    setGenerating(true);
    setError(null);
    try {
      const res = await fetch(`${BASE}/generate`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scope_type: selected.scope_type,
          scope_id: selected.scope_id,
          days_back: 14,
        }),
      });
      if (!res.ok) throw new Error(`generate: HTTP ${res.status}`);
      await loadScope(selected, view);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  const handleAddNote = async () => {
    if (!selected || noteTitle.trim().length < 3) return;
    setSavingNote(true);
    try {
      const res = await fetch(`${BASE}/notes`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scope_type: selected.scope_type,
          scope_id: selected.scope_id,
          title: noteTitle.trim(),
          description: noteBody.trim(),
        }),
      });
      if (!res.ok) throw new Error(`note: HTTP ${res.status}`);
      setNoteTitle('');
      setNoteBody('');
      setNoteFormOpen(false);
      await loadScope(selected, view);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save note');
    } finally {
      setSavingNote(false);
    }
  };

  const handleDeleteNote = async (id: number) => {
    if (!selected || !confirm('Delete this analyst note?')) return;
    try {
      const res = await fetch(`${BASE}/notes/${id}`, { method: 'DELETE', credentials: 'include' });
      if (!res.ok) throw new Error(`delete: HTTP ${res.status}`);
      await loadScope(selected, view);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete note');
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64">
      <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
    </div>;
  }

  const brands = scopes.filter(s => s.scope_type === 'brand');
  const topics = scopes.filter(s => s.scope_type === 'topic');
  const trend = summary?.state_doc?.current_trend;

  return (
    <div className="px-6 py-4 space-y-4">
      {/* Scope picker + actions */}
      <div className="flex items-center gap-3 flex-wrap">
        <CalendarDays className="w-5 h-5 text-gray-500" />
        <h2 className="text-lg font-semibold text-gray-900">Timeline</h2>
        <select
          className="border border-gray-300 rounded-md px-3 py-1.5 text-sm bg-white"
          value={selected ? `${selected.scope_type}:${selected.scope_id}` : ''}
          onChange={e => {
            const [st, ...rest] = e.target.value.split(':');
            const sid = rest.join(':');
            const scope = scopes.find(s => s.scope_type === st && s.scope_id === sid);
            if (scope) { setSelected(scope); setView('summary'); }
          }}
        >
          {brands.length > 0 && (
            <optgroup label="Brands">
              {brands.map(s => (
                <option key={`b:${s.scope_id}`} value={`brand:${s.scope_id}`}>
                  {s.label}{s.event_count ? ` (${s.event_count})` : ''}
                </option>
              ))}
            </optgroup>
          )}
          {topics.length > 0 && (
            <optgroup label="Topics">
              {topics.map(s => (
                <option key={`t:${s.scope_id}`} value={`topic:${s.scope_id}`}>
                  {s.label}{s.event_count ? ` (${s.event_count})` : ''}
                </option>
              ))}
            </optgroup>
          )}
        </select>
        <div className="flex rounded-md border border-gray-300 overflow-hidden text-sm">
          {(['summary', 'daily', 'weekly', 'monthly'] as const).map(v => (
            <button key={v}
              className={`px-3 py-1.5 capitalize ${view === v ? 'bg-blue-600 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'}`}
              onClick={() => setView(v)}>
              {v}
            </button>
          ))}
        </div>
        <button
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-300 rounded-md bg-white hover:bg-gray-50 disabled:opacity-50"
          onClick={handleGenerate}
          disabled={generating}
          title="Extract mementos for the last 14 days now"
        >
          {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          {generating ? 'Extracting…' : 'Extract now'}
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
          <AlertCircle className="w-4 h-4" />{error}
        </div>
      )}

      {loadingSummary ? (
        <div className="flex items-center justify-center h-40">
          <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
        </div>
      ) : view !== 'summary' && allEvents ? (
        <div className="space-y-2">
          {allEvents.length === 0 && (
            <div className="text-sm text-gray-500 py-8 text-center">
              No {view} mementos yet for this scope.
            </div>
          )}
          {allEvents.map(evt => <EventCard key={evt.id} evt={evt} />)}
        </div>
      ) : summary ? (
        <div className="space-y-4">
          {/* State doc */}
          {summary.state_doc && (
            <div className="border border-indigo-200 bg-indigo-50 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-1">
                <Sparkles className="w-4 h-4 text-indigo-600" />
                <span className="text-sm font-semibold text-indigo-900">
                  State of {summary.label}
                </span>
                {trend && (
                  <span className="text-xs px-2 py-0.5 bg-white border border-indigo-200 rounded text-indigo-700 capitalize">
                    {trend}
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-800">{summary.state_doc.summary}</p>
              {summary.state_doc.key_entities?.length > 0 && (
                <div className="mt-2 flex gap-1.5 flex-wrap">
                  {summary.state_doc.key_entities.slice(0, 10).map(e => (
                    <span key={e} className="text-xs px-1.5 py-0.5 bg-white border border-indigo-200 rounded text-indigo-800">{e}</span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Rollups */}
          {(summary.monthly.length > 0 || summary.weekly.length > 0) && (
            <div>
              <div className="flex items-center gap-2 mb-2 text-sm font-semibold text-gray-700">
                <Layers className="w-4 h-4" /> Rollups
              </div>
              <div className="space-y-2">
                {summary.monthly.map(evt => <EventCard key={evt.id} evt={evt} />)}
                {summary.weekly.map(evt => <EventCard key={evt.id} evt={evt} />)}
              </div>
            </div>
          )}

          {/* Analyst notes */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-semibold text-gray-700">Analyst notes</span>
              <button
                className="text-xs flex items-center gap-1 px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-50"
                onClick={() => setNoteFormOpen(!noteFormOpen)}
              >
                <Pin className="w-3 h-3" /> {noteFormOpen ? 'Cancel' : 'Pin note'}
              </button>
            </div>
            {noteFormOpen && (
              <div className="border border-gray-200 rounded-lg p-3 bg-gray-50 mb-2 space-y-2">
                <input
                  className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
                  placeholder="Note title (permanent — feeds the state doc and agent context)"
                  value={noteTitle}
                  onChange={e => setNoteTitle(e.target.value)}
                  maxLength={300}
                />
                <textarea
                  className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
                  placeholder="Detail (optional)"
                  rows={2}
                  value={noteBody}
                  onChange={e => setNoteBody(e.target.value)}
                  maxLength={2000}
                />
                <button
                  className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded disabled:opacity-50"
                  disabled={noteTitle.trim().length < 3 || savingNote}
                  onClick={handleAddNote}
                >
                  {savingNote ? 'Saving…' : 'Save note'}
                </button>
              </div>
            )}
            {summary.analyst_notes.length > 0 && (
              <div className="space-y-2">
                {summary.analyst_notes.map(evt => (
                  <div key={evt.id} className="flex items-start gap-2">
                    <div className="flex-1"><EventCard evt={evt} /></div>
                    <button
                      className="mt-3 text-gray-400 hover:text-red-600"
                      title="Delete note"
                      onClick={() => handleDeleteNote(evt.id)}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent mementos */}
          <div>
            <div className="text-sm font-semibold text-gray-700 mb-2">Recent mementos</div>
            <div className="space-y-2">
              {summary.daily.length === 0 && (
                <div className="text-sm text-gray-500 py-6 text-center">
                  No mementos yet — the scheduler extracts daily at 01:00 UTC,
                  or use "Extract now" to bootstrap the last 14 days.
                </div>
              )}
              {summary.daily.map(evt => <EventCard key={evt.id} evt={evt} />)}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
