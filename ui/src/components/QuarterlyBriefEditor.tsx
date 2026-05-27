/**
 * Quarterly Brief Editor — full-page editor that lets the analyst review,
 * edit, lock, and ship the Wiley quarterly bundle before it goes out.
 *
 * Wiley pays for the brief. Before this editor, every fabricated number
 * or off-tone briefing meant "regenerate everything and hope". Now the
 * analyst can edit any section inline, lock approved content so a
 * regenerate doesn't clobber it, curate events, preview rendered PPTX,
 * and self-approve to unblock the bundle download.
 *
 * Backend contract: /api/forecast/brief/{cadence}/{period_label}/*
 * (see app/routes/forecast_assessment_routes.py).
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Loader2, X, Lock, Unlock, RefreshCw, Eye, Send,
  FileText, Layers, Compass, History, Users, Calendar, CheckCircle2,
  AlertTriangle, Save, Plus, Trash2,
} from 'lucide-react';

type Tab =
  | 'exec_summary'
  | 'cross_cutting'
  | 'decision_framework'
  | 'whats_changed'
  | 'per_topic'
  | 'events'
  | 'approval';

interface ReviewFinding {
  stage?: string;
  artefact_key?: string;
  severity?: 'info' | 'warning' | 'error';
  finding?: string;
  suggested_fix?: string;
}

interface BriefPayload {
  cadence: string;
  period_label: string;
  payload: any;
  topics: any[];
  locked_keys: string[];
  edit_history: any[];
  updated_at?: string;
  review: {
    status?: string;
    reviewer_findings?: ReviewFinding[];
    approved_by?: string | null;
    approved_at?: string | null;
  };
  per_topic: Array<{
    topic: string;
    assessment_id: string;
    assessed_at?: string;
    summary: any;
    summary_locked_keys: string[];
  }>;
}

interface ExtractedEvent {
  id: number;
  topic: string;
  actor: string;
  action: string;
  subject: string;
  magnitude_value?: number | null;
  magnitude_unit?: string | null;
  event_date?: string | null;
  source_urls?: string[];
  confidence?: number | null;
  requires_review?: boolean;
  include_in_deck?: boolean;
  // v2: [{scenario, direction}] (confirms|counters|neutral). Older rows may
  // still hold bare strings — normalized in the UI helper below.
  scenario_relevance?: Array<{ scenario: string; direction?: string } | string>;
  origin?: 'auto' | 'manual';
}

interface Props {
  cadence: string;          // 'quarterly' | 'monthly' | 'all'
  periodLabel: string;      // e.g. '2026-Q2'
  onClose: () => void;
  editorIdentity?: string;  // e.g. user email
}

const TABS: { id: Tab; label: string; icon: any }[] = [
  { id: 'exec_summary', label: 'Exec Summary', icon: FileText },
  { id: 'cross_cutting', label: 'Cross-Cutting Themes', icon: Layers },
  { id: 'decision_framework', label: 'Decision Framework', icon: Compass },
  { id: 'whats_changed', label: "What's Changed", icon: History },
  { id: 'per_topic', label: 'Per-Topic', icon: Users },
  { id: 'events', label: 'Events', icon: Calendar },
  { id: 'approval', label: 'Approval', icon: CheckCircle2 },
];

export function QuarterlyBriefEditor({ cadence, periodLabel, onClose, editorIdentity }: Props) {
  const [tab, setTab] = useState<Tab>('exec_summary');
  const [brief, setBrief] = useState<BriefPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState<{ stage: string; taskId: string } | null>(null);

  const briefUrl = `/api/forecast/brief/${encodeURIComponent(cadence)}/${encodeURIComponent(periodLabel)}`;

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(briefUrl);
      if (!r.ok) {
        if (r.status === 404) {
          throw new Error(`No bundle generated yet for ${cadence} ${periodLabel}. Generate the bundle first.`);
        }
        throw new Error(`${r.status} ${r.statusText}`);
      }
      setBrief(await r.json());
    } catch (e: any) {
      setError(e?.message || 'Failed to load brief');
    } finally {
      setLoading(false);
    }
  }, [briefUrl, cadence, periodLabel]);

  useEffect(() => { refresh(); }, [refresh]);

  const showToast = (msg: string, ms = 3000) => {
    setToast(msg);
    setTimeout(() => setToast(null), ms);
  };

  const isLocked = useCallback((path: string) => {
    if (!brief) return false;
    return brief.locked_keys.includes(path);
  }, [brief]);

  const toggleLock = useCallback(async (path: string, locked: boolean) => {
    try {
      const r = await fetch(`${briefUrl}/lock`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, locked }),
      });
      if (!r.ok) throw new Error(`${r.status}`);
      await refresh();
      showToast(locked ? `Locked ${path}` : `Unlocked ${path}`);
    } catch (e: any) {
      showToast(`Lock toggle failed: ${e?.message || e}`);
    }
  }, [briefUrl, refresh]);

  const patchField = useCallback(async (path: string, value: any, lock?: boolean) => {
    try {
      const r = await fetch(`${briefUrl}/field`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path, value,
          lock: lock ?? undefined,
          edited_by: editorIdentity || 'analyst',
        }),
      });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      setBrief(await r.json());
      showToast(`Saved ${path}`);
    } catch (e: any) {
      showToast(`Save failed: ${e?.message || e}`);
    }
  }, [briefUrl, editorIdentity]);

  const patchTopicField = useCallback(async (
    topic: string, assessmentId: string, path: string, value: any, lock?: boolean,
  ) => {
    try {
      const r = await fetch(`${briefUrl}/topic-field`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic, assessment_id: assessmentId, path, value,
          lock: lock ?? undefined,
          edited_by: editorIdentity || 'analyst',
        }),
      });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      await refresh();
      showToast(`Saved ${topic} → ${path}`);
    } catch (e: any) {
      showToast(`Save failed: ${e?.message || e}`);
    }
  }, [briefUrl, editorIdentity, refresh]);

  const regenerateStage = useCallback(async (stage: string, topic?: string) => {
    try {
      const r = await fetch(`${briefUrl}/regenerate-stage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stage, topic, actor: editorIdentity || 'analyst' }),
      });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const data = await r.json();
      setRegenerating({ stage, taskId: data.task_id });
      showToast(`Regenerating ${stage}…`);
      // Poll for completion
      const poll = async () => {
        try {
          const jr = await fetch(`/api/forecast/assessment/job/${data.task_id}`);
          if (!jr.ok) return;
          const job = await jr.json();
          if (job.status === 'completed' || job.status === 'failed') {
            setRegenerating(null);
            showToast(`${stage}: ${job.status}`);
            await refresh();
            return;
          }
          setTimeout(poll, 1500);
        } catch {
          setTimeout(poll, 3000);
        }
      };
      setTimeout(poll, 1500);
    } catch (e: any) {
      showToast(`Regenerate failed: ${e?.message || e}`);
    }
  }, [briefUrl, editorIdentity, refresh]);

  const approveAndShip = useCallback(async () => {
    if (!confirm('Approve this brief and unlock the bundle download for Wiley?')) return;
    try {
      const r = await fetch(`${briefUrl}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved_by: editorIdentity || 'analyst' }),
      });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      await refresh();
      showToast('Approved — bundle now downloadable.');
    } catch (e: any) {
      showToast(`Approve failed: ${e?.message || e}`);
    }
  }, [briefUrl, editorIdentity, refresh]);

  const previewUrl = `${briefUrl}/preview.pptx`;

  return (
    <div
      className="fixed inset-0 z-[100] bg-gray-50 dark:bg-gray-950 flex flex-col"
      role="dialog"
      aria-label={`Quarterly Brief Editor — ${cadence} ${periodLabel}`}
    >
      {/* Header */}
      <div className="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100"
            title="Close editor"
          >
            <X className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Quarterly Brief Editor
            </h1>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {cadence} · {periodLabel}
              {brief?.updated_at && <> · last update {new Date(brief.updated_at).toLocaleString()}</>}
              {brief?.review?.status && (
                <> · review: <span className="font-medium">{brief.review.status}</span></>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={previewUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center text-sm px-3 py-1.5 border border-gray-300 dark:border-gray-700 rounded hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <Eye className="w-4 h-4 mr-1.5" /> Preview .pptx
          </a>
          <Button
            onClick={approveAndShip}
            className="inline-flex items-center bg-emerald-600 hover:bg-emerald-700 text-white"
          >
            <Send className="w-4 h-4 mr-1.5" /> Approve & ship
          </Button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 flex">
        {/* Vertical tab strip */}
        <nav className="w-56 border-r border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 py-3 overflow-y-auto">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`w-full text-left px-4 py-2 flex items-center gap-2 text-sm
                ${tab === id
                  ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-200 border-l-2 border-indigo-500'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800/60 border-l-2 border-transparent'}`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </nav>

        {/* Tab content */}
        <main className="flex-1 min-w-0 overflow-y-auto p-6">
          {loading && (
            <div className="flex items-center text-gray-500 dark:text-gray-400">
              <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading brief…
            </div>
          )}
          {error && (
            <div className="p-4 bg-red-50 dark:bg-red-900/30 border border-red-300 dark:border-red-700 rounded text-red-800 dark:text-red-200 text-sm">
              {error}
            </div>
          )}
          {brief && !loading && (
            <>
              {tab === 'exec_summary' && (
                <ExecSummaryTab
                  brief={brief}
                  isLocked={isLocked}
                  onToggleLock={toggleLock}
                  onPatch={patchField}
                  onRegenerate={() => regenerateStage('exec_summary')}
                  regenerating={regenerating?.stage === 'exec_summary'}
                  onRegenerateCommentary={() => regenerateStage('expert_commentary')}
                  regeneratingCommentary={regenerating?.stage === 'expert_commentary'}
                />
              )}
              {tab === 'cross_cutting' && (
                <ListSectionTab
                  brief={brief}
                  rootKey="cross_cutting_themes"
                  title="Cross-Cutting Themes"
                  isLocked={isLocked}
                  onToggleLock={toggleLock}
                  onPatch={patchField}
                  onRegenerate={() => regenerateStage('cross_topic')}
                  regenerating={regenerating?.stage === 'cross_topic'}
                  itemFields={['lead', 'body']}
                />
              )}
              {tab === 'decision_framework' && (
                <ListSectionTab
                  brief={brief}
                  rootKey="executive_decision_framework"
                  title="Executive Decision Framework"
                  isLocked={isLocked}
                  onToggleLock={toggleLock}
                  onPatch={patchField}
                  onRegenerate={() => regenerateStage('cross_topic')}
                  regenerating={regenerating?.stage === 'cross_topic'}
                  itemFields={['headline', 'body']}
                />
              )}
              {tab === 'whats_changed' && (
                <WhatsChangedTab
                  brief={brief}
                  isLocked={isLocked}
                  onToggleLock={toggleLock}
                  onPatch={patchField}
                />
              )}
              {tab === 'per_topic' && (
                <PerTopicTab
                  brief={brief}
                  onPatch={patchTopicField}
                  onRegenerate={(stage, topic) => regenerateStage(stage, topic)}
                  regeneratingStage={regenerating?.stage}
                />
              )}
              {tab === 'events' && (
                <EventsTab
                  cadence={cadence}
                  periodLabel={periodLabel}
                  brief={brief}
                  editorIdentity={editorIdentity}
                  showToast={showToast}
                />
              )}
              {tab === 'approval' && (
                <ApprovalTab
                  brief={brief}
                  approveAndShip={approveAndShip}
                />
              )}
            </>
          )}
        </main>
      </div>

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-4 right-4 z-[110] bg-gray-900 text-white text-sm px-4 py-2 rounded shadow-lg max-w-md">
          {toast}
        </div>
      )}

      {/* Regenerate indicator */}
      {regenerating && (
        <div className="fixed bottom-4 left-4 z-[110] bg-indigo-600 text-white text-sm px-4 py-2 rounded shadow-lg flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" />
          Regenerating {regenerating.stage}…
        </div>
      )}
    </div>
  );
}


// ─── Tab components ──────────────────────────────────────────────────

interface SectionHeaderProps {
  title: string;
  locked?: boolean;
  onToggleLock?: () => void;
  onRegenerate?: () => void;
  regenerating?: boolean;
}

function SectionHeader({ title, locked, onToggleLock, onRegenerate, regenerating }: SectionHeaderProps) {
  return (
    <div className="flex items-center justify-between mb-3">
      <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">{title}</h2>
      <div className="flex items-center gap-2">
        {onToggleLock && (
          <button
            onClick={onToggleLock}
            className={`inline-flex items-center text-xs px-2 py-1 rounded border
              ${locked
                ? 'bg-amber-50 border-amber-300 text-amber-800 dark:bg-amber-900/30 dark:border-amber-700 dark:text-amber-200'
                : 'bg-white border-gray-300 text-gray-700 dark:bg-gray-800 dark:border-gray-700 dark:text-gray-200'}`}
            title={locked ? 'Locked — regenerate will preserve this section' : 'Unlocked — regenerate may overwrite'}
          >
            {locked ? <Lock className="w-3 h-3 mr-1" /> : <Unlock className="w-3 h-3 mr-1" />}
            {locked ? 'Locked' : 'Lock'}
          </button>
        )}
        {onRegenerate && (
          <button
            onClick={onRegenerate}
            disabled={regenerating}
            className="inline-flex items-center text-xs px-2 py-1 rounded border border-indigo-300 text-indigo-700 dark:text-indigo-200 dark:border-indigo-700 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 disabled:opacity-50"
          >
            {regenerating
              ? <Loader2 className="w-3 h-3 mr-1 animate-spin" />
              : <RefreshCw className="w-3 h-3 mr-1" />}
            Regenerate
          </button>
        )}
      </div>
    </div>
  );
}


interface ExecSummaryTabProps {
  brief: BriefPayload;
  isLocked: (path: string) => boolean;
  onToggleLock: (path: string, locked: boolean) => Promise<void>;
  onPatch: (path: string, value: any, lock?: boolean) => Promise<void>;
  onRegenerate: () => void;
  regenerating: boolean;
  onRegenerateCommentary: () => void;
  regeneratingCommentary: boolean;
}

function ExecSummaryTab({ brief, isLocked, onToggleLock, onPatch, onRegenerate, regenerating,
                         onRegenerateCommentary, regeneratingCommentary }: ExecSummaryTabProps) {
  const letter = brief.payload?.exec_summary?.letter || '';
  const signoff = brief.payload?.exec_summary?.signoff || '';
  const commentary = brief.payload?.expert_commentary || '';
  const [draft, setDraft] = useState(letter);
  const [signDraft, setSignDraft] = useState(signoff);
  const [commDraft, setCommDraft] = useState(commentary);
  useEffect(() => { setDraft(letter); setSignDraft(signoff); setCommDraft(commentary); },
            [letter, signoff, commentary]);

  const letterPath = 'exec_summary.letter';
  const signoffPath = 'exec_summary.signoff';
  const commentaryPath = 'expert_commentary';
  const locked = isLocked(letterPath);
  const commLocked = isLocked(commentaryPath);

  return (
    <div className="max-w-3xl">
      <SectionHeader
        title="Executive Summary letter"
        locked={locked}
        onToggleLock={() => onToggleLock(letterPath, !locked)}
        onRegenerate={onRegenerate}
        regenerating={regenerating}
      />
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
        Multi-paragraph Markdown. Bold section headers (<code>**The bottom line.**</code>) become slide subheads.
        Edit freely — Save when done. Lock to preserve across regenerates.
      </p>
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        className="w-full h-[480px] p-3 font-mono text-sm bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded text-gray-900 dark:text-gray-100"
        placeholder="**The bottom line.** ..."
      />
      <div className="flex items-center gap-2 mt-2">
        <Button onClick={() => onPatch(letterPath, draft)} className="inline-flex items-center">
          <Save className="w-4 h-4 mr-1.5" /> Save letter
        </Button>
        <Button
          onClick={() => { setDraft(letter); }}
          variant="outline"
        >
          Revert
        </Button>
      </div>

      <div className="mt-6">
        <SectionHeader title="Signoff" />
        <input
          value={signDraft}
          onChange={(e) => setSignDraft(e.target.value)}
          className="w-full p-2 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded text-sm"
          placeholder="AunooAI Editorial Team · Q2 2026"
        />
        <Button
          onClick={() => onPatch(signoffPath, signDraft)}
          className="mt-2 inline-flex items-center"
          size="sm"
        >
          <Save className="w-4 h-4 mr-1.5" /> Save signoff
        </Button>
      </div>

      <div className="mt-8 pt-6 border-t border-gray-200 dark:border-gray-700">
        <SectionHeader
          title="Expert view — emerging themes"
          locked={commLocked}
          onToggleLock={() => onToggleLock(commentaryPath, !commLocked)}
          onRegenerate={onRegenerateCommentary}
          regenerating={regeneratingCommentary}
        />
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
          One to two paragraphs of expert interpretation of the quarter's emerging themes.
          AI drafts it grounded in the named themes — edit freely, then Save. Lock to preserve
          across regenerates. Renders in the deck, Executive Summary doc, and HTML.
        </p>
        <textarea
          value={commDraft}
          onChange={(e) => setCommDraft(e.target.value)}
          className="w-full h-[220px] p-3 font-mono text-sm bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded text-gray-900 dark:text-gray-100"
          placeholder="Several themes this quarter show…"
        />
        <div className="flex items-center gap-2 mt-2">
          <Button onClick={() => onPatch(commentaryPath, commDraft)} className="inline-flex items-center">
            <Save className="w-4 h-4 mr-1.5" /> Save commentary
          </Button>
          <Button onClick={() => { setCommDraft(commentary); }} variant="outline">
            Revert
          </Button>
        </div>
      </div>
    </div>
  );
}


interface ListSectionTabProps {
  brief: BriefPayload;
  rootKey: string;
  title: string;
  isLocked: (path: string) => boolean;
  onToggleLock: (path: string, locked: boolean) => Promise<void>;
  onPatch: (path: string, value: any, lock?: boolean) => Promise<void>;
  onRegenerate: () => void;
  regenerating: boolean;
  itemFields: string[];
}

function ListSectionTab({
  brief, rootKey, title, isLocked, onToggleLock, onPatch, onRegenerate, regenerating, itemFields,
}: ListSectionTabProps) {
  const items: any[] = brief.payload?.[rootKey] || [];

  const updateItemField = async (idx: number, field: string, value: string) => {
    const path = `${rootKey}[${idx}].${field}`;
    await onPatch(path, value);
  };

  const replaceList = async (next: any[]) => {
    await onPatch(rootKey, next);
  };

  return (
    <div className="max-w-3xl">
      <SectionHeader
        title={title}
        onRegenerate={onRegenerate}
        regenerating={regenerating}
      />
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        {items.length} {items.length === 1 ? 'item' : 'items'}.
        Edit text inline. Use Add / Remove to restructure. Lock individual items via the chip.
      </p>

      <div className="space-y-3">
        {items.map((it, idx) => {
          const itemPath = `${rootKey}[${idx}]`;
          const locked = isLocked(itemPath);
          return (
            <div
              key={idx}
              className="border border-gray-200 dark:border-gray-700 rounded p-3 bg-white dark:bg-gray-900"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-500 dark:text-gray-400">#{idx + 1}</span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => onToggleLock(itemPath, !locked)}
                    className={`inline-flex items-center text-xs px-2 py-1 rounded border
                      ${locked
                        ? 'bg-amber-50 border-amber-300 text-amber-800 dark:bg-amber-900/30 dark:border-amber-700 dark:text-amber-200'
                        : 'bg-white border-gray-300 text-gray-700 dark:bg-gray-800 dark:border-gray-700 dark:text-gray-200'}`}
                  >
                    {locked ? <Lock className="w-3 h-3 mr-1" /> : <Unlock className="w-3 h-3 mr-1" />}
                    {locked ? 'Locked' : 'Lock'}
                  </button>
                  <button
                    onClick={() => replaceList(items.filter((_, i) => i !== idx))}
                    className="text-xs text-red-600 dark:text-red-300 hover:underline inline-flex items-center"
                  >
                    <Trash2 className="w-3 h-3 mr-1" /> Remove
                  </button>
                </div>
              </div>
              {itemFields.map((field) => (
                <div key={field} className="mb-2">
                  <label className="block text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    {field}
                  </label>
                  {(field === 'name' || field === 'lead' || field === 'headline') ? (
                    <input
                      defaultValue={it[field] || ''}
                      onBlur={(e) => {
                        if (e.target.value !== (it[field] || '')) {
                          updateItemField(idx, field, e.target.value);
                        }
                      }}
                      className="w-full p-1.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded text-sm"
                    />
                  ) : (
                    <textarea
                      defaultValue={it[field] || ''}
                      rows={3}
                      onBlur={(e) => {
                        if (e.target.value !== (it[field] || '')) {
                          updateItemField(idx, field, e.target.value);
                        }
                      }}
                      className="w-full p-1.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded text-sm"
                    />
                  )}
                </div>
              ))}
            </div>
          );
        })}
        <button
          onClick={() => {
            const blank: any = {};
            itemFields.forEach((f) => { blank[f] = ''; });
            replaceList([...items, blank]);
          }}
          className="text-sm text-indigo-600 dark:text-indigo-300 hover:underline inline-flex items-center"
        >
          <Plus className="w-4 h-4 mr-1" /> Add item
        </button>
      </div>
    </div>
  );
}


interface WhatsChangedTabProps {
  brief: BriefPayload;
  isLocked: (path: string) => boolean;
  onToggleLock: (path: string, locked: boolean) => Promise<void>;
  onPatch: (path: string, value: any, lock?: boolean) => Promise<void>;
}

function WhatsChangedTab({ brief, onPatch }: WhatsChangedTabProps) {
  const wc = brief.payload?.whats_changed || {};

  const subsections: Array<{ key: string; title: string; help: string }> = [
    { key: 'events', title: 'Named events this quarter', help: 'Auto-populated from extraction. Edit factual facts; toggle include_in_deck on the Events tab.' },
    { key: 'scenario_drift', title: 'Scenarios that moved in our framing', help: 'Three Horizons scenario-set drift. One bullet per scenario name + before/after positioning.' },
    { key: 'emerging', title: 'New on the watch', help: 'New emerging themes the discovery pipeline surfaced this quarter.' },
    { key: 'coverage_shifts', title: 'Where press attention shifted', help: 'Press attention only — never framed as forecast accuracy.' },
  ];

  return (
    <div className="max-w-3xl">
      <SectionHeader title="What's Changed Since Last Quarter" />
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
        Four signals, in slide priority order: events → drift → emerging → coverage shifts.
        The slide drops items from the bottom when budget is tight.
      </p>

      {subsections.map(({ key, title, help }) => {
        const items: string[] = Array.isArray(wc[key]) ? wc[key] : [];
        const path = `whats_changed.${key}`;
        return (
          <div key={key} className="mb-6 border border-gray-200 dark:border-gray-700 rounded p-3 bg-white dark:bg-gray-900">
            <SectionHeader title={title} />
            <p className="text-[11px] text-gray-500 dark:text-gray-400 mb-2">{help}</p>
            <ul className="space-y-2">
              {items.map((it, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <textarea
                    defaultValue={it}
                    rows={2}
                    onBlur={(e) => {
                      if (e.target.value !== it) {
                        const next = [...items];
                        next[idx] = e.target.value;
                        onPatch(path, next);
                      }
                    }}
                    className="flex-1 p-1.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded text-sm"
                  />
                  <button
                    onClick={() => onPatch(path, items.filter((_, i) => i !== idx))}
                    className="text-red-600 dark:text-red-300 text-xs hover:underline mt-1"
                    title="Remove"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </li>
              ))}
            </ul>
            <button
              onClick={() => onPatch(path, [...items, ''])}
              className="text-sm text-indigo-600 dark:text-indigo-300 hover:underline inline-flex items-center mt-2"
            >
              <Plus className="w-4 h-4 mr-1" /> Add line
            </button>
          </div>
        );
      })}
    </div>
  );
}


interface PerTopicTabProps {
  brief: BriefPayload;
  onPatch: (topic: string, assessmentId: string, path: string, value: any, lock?: boolean) => Promise<void>;
  onRegenerate: (stage: string, topic?: string) => void;
  regeneratingStage?: string;
}

function PerTopicTab({ brief, onPatch, onRegenerate, regeneratingStage }: PerTopicTabProps) {
  const [activeTopic, setActiveTopic] = useState<string | null>(brief.per_topic[0]?.topic || null);
  const t = brief.per_topic.find((p) => p.topic === activeTopic);

  if (!t) return <div className="text-sm text-gray-600 dark:text-gray-300">No topics in this brief.</div>;

  const briefing = t.summary?.topic_briefing || {};
  const recs: string[] = t.summary?.strategic_recommendations || [];
  const nextSteps: string[] = t.summary?.next_steps || [];

  return (
    <div className="max-w-4xl">
      <div className="flex flex-wrap gap-2 mb-4 border-b border-gray-200 dark:border-gray-700 pb-2">
        {brief.per_topic.map((p) => (
          <button
            key={p.topic}
            onClick={() => setActiveTopic(p.topic)}
            className={`text-xs px-2 py-1 rounded ${
              activeTopic === p.topic
                ? 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-200'
                : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
          >
            {p.topic}
          </button>
        ))}
      </div>

      <div className="mb-6">
        <SectionHeader
          title={`Briefing — ${t.topic}`}
          onRegenerate={() => onRegenerate('briefing', t.topic)}
          regenerating={regeneratingStage === 'briefing'}
        />
        <label className="block text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Headline</label>
        <input
          defaultValue={briefing.headline || ''}
          onBlur={(e) => {
            if (e.target.value !== (briefing.headline || '')) {
              onPatch(t.topic, t.assessment_id, 'topic_briefing.headline', e.target.value);
            }
          }}
          className="w-full p-1.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded text-sm mb-2"
        />
        <label className="block text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Lede</label>
        <textarea
          defaultValue={briefing.lede || ''}
          rows={3}
          onBlur={(e) => {
            if (e.target.value !== (briefing.lede || '')) {
              onPatch(t.topic, t.assessment_id, 'topic_briefing.lede', e.target.value);
            }
          }}
          className="w-full p-1.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded text-sm mb-2"
        />
        {(briefing.tensions || []).map((tn: any, idx: number) => (
          <div key={idx} className="mb-2 p-2 bg-gray-50 dark:bg-gray-800/40 border border-gray-200 dark:border-gray-700 rounded">
            <label className="block text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Tension {idx + 1} — name</label>
            <input
              defaultValue={tn.name || ''}
              onBlur={(e) => {
                if (e.target.value !== (tn.name || '')) {
                  onPatch(t.topic, t.assessment_id, `topic_briefing.tensions[${idx}].name`, e.target.value);
                }
              }}
              className="w-full p-1.5 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded text-sm mb-1"
            />
            <label className="block text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Body</label>
            <textarea
              defaultValue={tn.body || ''}
              rows={2}
              onBlur={(e) => {
                if (e.target.value !== (tn.body || '')) {
                  onPatch(t.topic, t.assessment_id, `topic_briefing.tensions[${idx}].body`, e.target.value);
                }
              }}
              className="w-full p-1.5 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded text-sm"
            />
          </div>
        ))}
      </div>

      <div className="mb-6">
        <SectionHeader
          title="Strategic Recommendations"
          onRegenerate={() => onRegenerate('recommendations', t.topic)}
          regenerating={regeneratingStage === 'recommendations'}
        />
        {recs.map((r, idx) => (
          <textarea
            key={idx}
            defaultValue={r}
            rows={2}
            onBlur={(e) => {
              if (e.target.value !== r) {
                const next = [...recs];
                next[idx] = e.target.value;
                onPatch(t.topic, t.assessment_id, 'strategic_recommendations', next);
              }
            }}
            className="w-full p-1.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded text-sm mb-2"
          />
        ))}
      </div>

      <div className="mb-6">
        <SectionHeader
          title="Next Steps"
          onRegenerate={() => onRegenerate('next_steps', t.topic)}
          regenerating={regeneratingStage === 'next_steps'}
        />
        {nextSteps.map((s, idx) => (
          <textarea
            key={idx}
            defaultValue={s}
            rows={2}
            onBlur={(e) => {
              if (e.target.value !== s) {
                const next = [...nextSteps];
                next[idx] = e.target.value;
                onPatch(t.topic, t.assessment_id, 'next_steps', next);
              }
            }}
            className="w-full p-1.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded text-sm mb-2"
          />
        ))}
      </div>
    </div>
  );
}


interface EventsTabProps {
  cadence: string;
  periodLabel: string;
  brief: BriefPayload;
  editorIdentity?: string;
  showToast: (msg: string) => void;
}

function EventsTab({ cadence, periodLabel, brief, editorIdentity, showToast }: EventsTabProps) {
  const [events, setEvents] = useState<ExtractedEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [topicFilter, setTopicFilter] = useState<string>('');

  const base = `/api/forecast/brief/${encodeURIComponent(cadence)}/${encodeURIComponent(periodLabel)}/events`;

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const url = topicFilter ? `${base}?topic=${encodeURIComponent(topicFilter)}` : base;
      const r = await fetch(url);
      if (!r.ok) throw new Error(`${r.status}`);
      const data = await r.json();
      setEvents(data.events || []);
    } catch (e: any) {
      showToast(`Load events failed: ${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }, [base, topicFilter, showToast]);

  useEffect(() => { refresh(); }, [refresh]);

  const patch = async (id: number, fields: Partial<ExtractedEvent>) => {
    try {
      const r = await fetch(`/api/forecast/brief/events/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...fields, edited_by: editorIdentity || 'analyst' }),
      });
      if (!r.ok) throw new Error(`${r.status}`);
      await refresh();
    } catch (e: any) {
      showToast(`Patch failed: ${e?.message || e}`);
    }
  };

  const remove = async (id: number) => {
    if (!confirm('Delete this event?')) return;
    try {
      const r = await fetch(`/api/forecast/brief/events/${id}`, { method: 'DELETE' });
      if (!r.ok) throw new Error(`${r.status}`);
      await refresh();
      showToast('Event removed');
    } catch (e: any) {
      showToast(`Delete failed: ${e?.message || e}`);
    }
  };

  const addManual = async () => {
    const topic = brief.per_topic[0]?.topic || '';
    if (!topic) { showToast('No topic available to attach event to'); return; }
    try {
      const r = await fetch(base, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic,
          actor: 'New actor',
          action: 'announced',
          subject: 'New event subject',
          event_date: new Date().toISOString().slice(0, 10),
          source_urls: [],
          confidence: 1.0,
          requires_review: false,
          edited_by: editorIdentity || 'analyst',
        }),
      });
      if (!r.ok) throw new Error(`${r.status}`);
      await refresh();
      showToast('Manual event added');
    } catch (e: any) {
      showToast(`Add failed: ${e?.message || e}`);
    }
  };

  const review = events.filter((e) => e.requires_review);
  const ready = events.filter((e) => !e.requires_review);

  return (
    <div className="max-w-5xl">
      <SectionHeader title="Events curation" />
      <div className="flex items-center justify-between gap-2 mb-3">
        <select
          value={topicFilter}
          onChange={(e) => setTopicFilter(e.target.value)}
          className="p-1.5 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded text-sm"
        >
          <option value="">All topics</option>
          {brief.per_topic.map((p) => (
            <option key={p.topic} value={p.topic}>{p.topic}</option>
          ))}
        </select>
        <Button onClick={addManual} className="inline-flex items-center">
          <Plus className="w-4 h-4 mr-1.5" /> Add manual event
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center text-gray-500 dark:text-gray-400">
          <Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading events…
        </div>
      ) : (
        <>
          {review.length > 0 && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-amber-700 dark:text-amber-300 mb-2 flex items-center">
                <AlertTriangle className="w-4 h-4 mr-1.5" /> Needs review ({review.length})
              </h3>
              <EventTable events={review} onPatch={patch} onRemove={remove} />
            </div>
          )}
          <div>
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
              Ready for deck ({ready.length})
            </h3>
            {ready.length === 0 ? (
              <div className="text-sm text-gray-500 dark:text-gray-400 italic">
                No events extracted yet for this period. Use "Add manual event" or run the event extraction stage.
              </div>
            ) : (
              <EventTable events={ready} onPatch={patch} onRemove={remove} />
            )}
          </div>
        </>
      )}
    </div>
  );
}

const DIR_STYLE: Record<string, string> = {
  confirms: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200',
  counters: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
  neutral: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300',
};
const DIR_CYCLE: Record<string, string> = { confirms: 'counters', counters: 'neutral', neutral: 'confirms' };

function _normRel(raw: ExtractedEvent['scenario_relevance']): Array<{ scenario: string; direction: string }> {
  return (raw || []).map((r) =>
    typeof r === 'string'
      ? { scenario: r, direction: 'neutral' }
      : { scenario: r.scenario, direction: (r.direction || 'neutral') }
  ).filter((r) => r.scenario);
}

function EventTable({
  events, onPatch, onRemove,
}: {
  events: ExtractedEvent[];
  onPatch: (id: number, fields: Partial<ExtractedEvent>) => Promise<void>;
  onRemove: (id: number) => Promise<void>;
}) {
  const cycleDir = (ev: ExtractedEvent, idx: number) => {
    const rel = _normRel(ev.scenario_relevance);
    rel[idx] = { ...rel[idx], direction: DIR_CYCLE[rel[idx].direction] || 'confirms' };
    onPatch(ev.id, { scenario_relevance: rel });
  };
  return (
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr className="text-left text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
          <th className="py-1 pr-2">In deck</th>
          <th className="py-1 pr-2">Topic</th>
          <th className="py-1 pr-2">Actor</th>
          <th className="py-1 pr-2">Action</th>
          <th className="py-1 pr-2">Subject</th>
          <th className="py-1 pr-2">Magnitude</th>
          <th className="py-1 pr-2">Date</th>
          <th className="py-1 pr-2">Conf</th>
          <th className="py-1 pr-2">Signal direction</th>
          <th className="py-1 pr-2">Origin</th>
          <th className="py-1 pr-2"></th>
        </tr>
      </thead>
      <tbody>
        {events.map((ev) => (
          <tr key={ev.id} className="border-b border-gray-100 dark:border-gray-800">
            <td className="py-1 pr-2">
              <input
                type="checkbox"
                checked={!!ev.include_in_deck}
                onChange={(e) => onPatch(ev.id, { include_in_deck: e.target.checked })}
              />
            </td>
            <td className="py-1 pr-2 text-xs">{ev.topic}</td>
            <td className="py-1 pr-2">
              <input
                defaultValue={ev.actor}
                onBlur={(e) => { if (e.target.value !== ev.actor) onPatch(ev.id, { actor: e.target.value }); }}
                className="w-32 p-1 bg-transparent border border-gray-200 dark:border-gray-700 rounded text-xs"
              />
            </td>
            <td className="py-1 pr-2">
              <input
                defaultValue={ev.action}
                onBlur={(e) => { if (e.target.value !== ev.action) onPatch(ev.id, { action: e.target.value }); }}
                className="w-24 p-1 bg-transparent border border-gray-200 dark:border-gray-700 rounded text-xs"
              />
            </td>
            <td className="py-1 pr-2">
              <input
                defaultValue={ev.subject}
                onBlur={(e) => { if (e.target.value !== ev.subject) onPatch(ev.id, { subject: e.target.value }); }}
                className="w-60 p-1 bg-transparent border border-gray-200 dark:border-gray-700 rounded text-xs"
              />
            </td>
            <td className="py-1 pr-2 text-xs">
              {ev.magnitude_value != null
                ? `${ev.magnitude_value} ${ev.magnitude_unit || ''}`
                : '—'}
            </td>
            <td className="py-1 pr-2 text-xs">{ev.event_date || '—'}</td>
            <td className="py-1 pr-2 text-xs">
              {ev.confidence != null ? ev.confidence.toFixed(2) : '—'}
            </td>
            <td className="py-1 pr-2">
              <div className="flex flex-wrap gap-1 max-w-[220px]">
                {_normRel(ev.scenario_relevance).length === 0 ? (
                  <span className="text-[10px] text-gray-400">—</span>
                ) : _normRel(ev.scenario_relevance).map((rel, idx) => (
                  <button
                    key={idx}
                    onClick={() => cycleDir(ev, idx)}
                    title={`${rel.scenario} — ${rel.direction} (click to change)`}
                    className={`text-[10px] px-1.5 py-0.5 rounded ${DIR_STYLE[rel.direction] || DIR_STYLE.neutral}`}
                  >
                    {rel.direction === 'confirms' ? '▲' : rel.direction === 'counters' ? '▼' : '◦'} {rel.scenario.length > 16 ? rel.scenario.slice(0, 15) + '…' : rel.scenario}
                  </button>
                ))}
              </div>
            </td>
            <td className="py-1 pr-2 text-xs">{ev.origin || 'auto'}</td>
            <td className="py-1 pr-2">
              <button onClick={() => onRemove(ev.id)} className="text-red-600 dark:text-red-300" title="Remove">
                <Trash2 className="w-3 h-3" />
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}


function ApprovalTab({ brief, approveAndShip }: { brief: BriefPayload; approveAndShip: () => Promise<void> }) {
  const findings = brief.review?.reviewer_findings || [];
  const status = brief.review?.status || 'unknown';
  const errors = findings.filter((f) => f.severity === 'error').length;
  const warnings = findings.filter((f) => f.severity === 'warning').length;

  return (
    <div className="max-w-3xl space-y-6">
      <SectionHeader title="Approval — review findings + lock summary" />

      <div className="grid grid-cols-3 gap-3">
        <div className="p-3 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded">
          <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Review status</div>
          <div className="font-semibold mt-1">{status}</div>
        </div>
        <div className="p-3 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded">
          <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Errors</div>
          <div className="font-semibold mt-1 text-red-700 dark:text-red-300">{errors}</div>
        </div>
        <div className="p-3 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded">
          <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Warnings</div>
          <div className="font-semibold mt-1 text-amber-700 dark:text-amber-300">{warnings}</div>
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-2">Locked sections ({brief.locked_keys.length})</h3>
        {brief.locked_keys.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400 italic">
            No sections locked. Lock anything you've edited to preserve across regenerates.
          </p>
        ) : (
          <ul className="text-sm space-y-1">
            {brief.locked_keys.map((k) => (
              <li key={k} className="font-mono text-xs bg-amber-50 dark:bg-amber-900/20 px-2 py-1 rounded text-amber-800 dark:text-amber-200 inline-flex items-center mr-2 mb-1">
                <Lock className="w-3 h-3 mr-1" /> {k}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-2">Reviewer findings</h3>
        {findings.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400 italic">No findings on record.</p>
        ) : (
          <ul className="space-y-2">
            {findings.map((f, i) => (
              <li key={i} className={`p-2 rounded text-sm border
                ${f.severity === 'error'
                  ? 'bg-red-50 border-red-300 text-red-800 dark:bg-red-900/30 dark:border-red-700 dark:text-red-200'
                  : f.severity === 'warning'
                    ? 'bg-amber-50 border-amber-300 text-amber-800 dark:bg-amber-900/30 dark:border-amber-700 dark:text-amber-200'
                    : 'bg-gray-50 border-gray-300 text-gray-700 dark:bg-gray-800 dark:border-gray-700 dark:text-gray-200'}`}>
                <div className="text-[11px] uppercase tracking-wide mb-1">
                  {f.severity} · <span className="font-mono">{f.artefact_key || f.stage || '—'}</span>
                </div>
                <div>{f.finding}</div>
                {f.suggested_fix && (
                  <div className="mt-1 text-xs italic">Suggested: {f.suggested_fix}</div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button onClick={approveAndShip} className="bg-emerald-600 hover:bg-emerald-700 text-white inline-flex items-center">
          <Send className="w-4 h-4 mr-1.5" /> Approve & ship
        </Button>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
          Stamps approved_by / approved_at. The bundle PPTX download then returns 200 (not 202) for the Wiley recipient.
        </p>
      </div>
    </div>
  );
}
