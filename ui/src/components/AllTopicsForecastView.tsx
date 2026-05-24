/**
 * All-topics Forecast Tracker view.
 *
 * Rendered when the user selects "ALL Topics" in the topic selector on the
 * Forecast Tracker tab. Shows a one-card-per-topic grid summarising each
 * topic's latest assessment, plus a global "download bundle" affordance so
 * the user can grab a multi-topic PPTX covering everything in one click.
 *
 * Each card is a compact gap-analysis summary: topic name, last assessed,
 * baseline-corrected verdict distribution, evidence/surprise counts. Clicking
 * a card switches the parent topic selector to that topic for the drill-in.
 */

import { useCallback, useEffect, useState } from 'react';
import { Loader2, Download, RefreshCw, AlertTriangle, CheckCircle2, MinusCircle, TrendingDown, TrendingUp, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { DeliverablePreview, DeliverablePreviewTopic } from '@/types/forecastAssessment';

interface Props {
  onSelectTopic?: (topic: string) => void;
}

const BASELINE_BADGE: Record<string, { bg: string; text: string; icon: JSX.Element }> = {
  'Above baseline': {
    bg: 'bg-emerald-100 dark:bg-emerald-900/40',
    text: 'text-emerald-800 dark:text-emerald-200',
    icon: <TrendingUp className="w-3 h-3" />,
  },
  'At baseline': {
    bg: 'bg-gray-100 dark:bg-gray-800',
    text: 'text-gray-700 dark:text-gray-200',
    icon: <MinusCircle className="w-3 h-3" />,
  },
  'Below baseline': {
    bg: 'bg-amber-100 dark:bg-amber-900/40',
    text: 'text-amber-800 dark:text-amber-200',
    icon: <TrendingDown className="w-3 h-3" />,
  },
  // Fallback for assessments with no baseline correction yet
  'Accelerating': {
    bg: 'bg-emerald-100 dark:bg-emerald-900/40',
    text: 'text-emerald-800 dark:text-emerald-200',
    icon: <TrendingUp className="w-3 h-3" />,
  },
  'On-track': {
    bg: 'bg-blue-100 dark:bg-blue-900/40',
    text: 'text-blue-800 dark:text-blue-200',
    icon: <CheckCircle2 className="w-3 h-3" />,
  },
  'Stalled': {
    bg: 'bg-amber-100 dark:bg-amber-900/40',
    text: 'text-amber-800 dark:text-amber-200',
    icon: <MinusCircle className="w-3 h-3" />,
  },
  'Off-track': {
    bg: 'bg-red-100 dark:bg-red-900/40',
    text: 'text-red-800 dark:text-red-200',
    icon: <TrendingDown className="w-3 h-3" />,
  },
  'Inconclusive': {
    bg: 'bg-gray-100 dark:bg-gray-800',
    text: 'text-gray-700 dark:text-gray-200',
    icon: <AlertTriangle className="w-3 h-3" />,
  },
};


export function AllTopicsForecastView({ onSelectTopic }: Props) {
  const [preview, setPreview] = useState<DeliverablePreview | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/forecast/deliverables/preview?cadence=all');
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const data: DeliverablePreview = await r.json();
      setPreview(data);
    } catch (e: any) {
      setError(e?.message || 'Failed to load topics');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center text-gray-500">
        <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading topics…
      </div>
    );
  }

  const topics = preview?.topics || [];
  const ready = topics.filter(t => t.ready);

  return (
    <div className="space-y-6">
      <div className="p-5 bg-gradient-to-r from-indigo-50 to-purple-50 dark:from-indigo-900/30 dark:to-purple-900/30 border-l-4 border-indigo-500 rounded-r-lg">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-indigo-600 dark:text-indigo-300" />
              Forecast Tracker — all topics
            </h2>
            <p className="text-sm text-gray-700 dark:text-gray-200 mt-1">
              {ready.length} {ready.length === 1 ? 'topic' : 'topics'} with stored assessments. Click a card to drill in, or download a multi-topic bundle covering all of them.
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <a
              href="/api/forecast/deliverables/bundle.pptx?cadence=all&updates_only=false"
              className={`inline-flex items-center text-xs px-3 py-2 border border-indigo-300 text-indigo-700 dark:text-indigo-200 dark:border-indigo-700 rounded hover:bg-indigo-50 dark:hover:bg-indigo-900/40 ${ready.length === 0 ? 'opacity-50 pointer-events-none' : ''}`}
              download
              title="Full bundle PPTX covering every topic with a stored assessment"
            >
              <Download className="w-3.5 h-3.5 mr-1" /> Bundle .pptx
            </a>
            <a
              href="/api/forecast/deliverables/bundle.pptx?cadence=all&updates_only=true"
              className={`inline-flex items-center text-xs px-3 py-2 border border-pink-300 text-pink-700 dark:text-pink-200 dark:border-pink-700 rounded hover:bg-pink-50 dark:hover:bg-pink-900/40 ${ready.length === 0 ? 'opacity-50 pointer-events-none' : ''}`}
              download
              title="Bundle showing only what's changed in each topic since its prior snapshot"
            >
              <Download className="w-3.5 h-3.5 mr-1" /> Updates only
            </a>
            <button
              type="button"
              onClick={refresh}
              className="text-xs text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 inline-flex items-center"
            >
              <RefreshCw className="w-3 h-3 mr-1" /> Refresh
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 dark:bg-red-900/30 border border-red-300 rounded text-red-800 dark:text-red-200 text-sm">
          {error}
        </div>
      )}

      {topics.length === 0 ? (
        <div className="p-6 bg-gray-50 dark:bg-gray-900/40 border border-gray-200 dark:border-gray-700 rounded text-center">
          <div className="text-gray-700 dark:text-gray-100 font-medium">No assessments stored yet</div>
          <div className="text-sm text-gray-600 dark:text-gray-300 mt-2 max-w-xl mx-auto">
            Run a Forecast Tracker assessment for at least one topic first — pick a topic from the selector and click "Run assessment".
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {topics.map((t) => (
            <TopicCard key={t.topic} topic={t} onSelect={onSelectTopic} />
          ))}
        </div>
      )}
    </div>
  );
}


function TopicCard({ topic, onSelect }: { topic: DeliverablePreviewTopic; onSelect?: (topic: string) => void }) {
  const handleClick = () => {
    if (!topic.ready) return;
    onSelect?.(topic.topic);
  };

  return (
    <div
      role={topic.ready && onSelect ? 'button' : undefined}
      tabIndex={topic.ready && onSelect ? 0 : undefined}
      onClick={handleClick}
      onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && topic.ready && onSelect) { e.preventDefault(); handleClick(); } }}
      className={`p-4 bg-white dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm transition ${topic.ready && onSelect ? 'cursor-pointer hover:border-indigo-400 dark:hover:border-indigo-600 hover:shadow' : ''}`}
    >
      <div className="font-semibold text-gray-900 dark:text-gray-100 leading-snug line-clamp-2">
        {topic.topic}
      </div>

      {!topic.ready ? (
        <div className="mt-3 text-xs text-amber-700 dark:text-amber-300 flex items-center gap-1">
          <AlertTriangle className="w-3 h-3" />
          {topic.reason || 'Not assessed yet'}
        </div>
      ) : (
        <>
          <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Assessed {topic.assessed_at ? new Date(topic.assessed_at).toLocaleDateString() : '—'}
          </div>

          {topic.label_distribution && Object.keys(topic.label_distribution).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1">
              {Object.entries(topic.label_distribution)
                .sort((a, b) => (b[1] as number) - (a[1] as number))
                .map(([label, count]) => {
                  const style = BASELINE_BADGE[label] || BASELINE_BADGE['Inconclusive'];
                  return (
                    <span
                      key={label}
                      className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded ${style.bg} ${style.text}`}
                    >
                      {style.icon}
                      {label} <span className="font-semibold">{count as number}</span>
                    </span>
                  );
                })}
            </div>
          )}

          <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
            <Stat label="Scenarios" value={topic.scenarios_count} />
            <Stat label="Articles" value={topic.evidence_count} />
            <Stat label="Surprises" value={topic.surprises_count} />
          </div>

          <div className="mt-3 flex items-center justify-between text-[11px] text-gray-500 dark:text-gray-400">
            <span>
              Cadence: <span className="font-medium text-gray-700 dark:text-gray-200">{topic.cadence || 'none'}</span>
            </span>
            {topic.recipient_email && (
              <span className="truncate max-w-[140px]" title={topic.recipient_email}>
                → {topic.recipient_email}
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}


function Stat({ label, value }: { label: string; value?: number }) {
  return (
    <div className="p-2 bg-gray-50 dark:bg-gray-900/40 border border-gray-200 dark:border-gray-700 rounded text-center">
      <div className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">{label}</div>
      <div className="font-semibold text-gray-800 dark:text-gray-100">{value ?? '—'}</div>
    </div>
  );
}
