/**
 * AddTopicWizard — 4-step modal that walks a non-developer through adding
 * a new tracked topic.
 *
 *   1. Framing   — name + display name + description + owner + tags
 *   2. Build     — fires horizons + paired assessment + draft overlay in
 *                  the background. Wizard polls progress; auto-advances.
 *                  Replaces the old "open another tab and come back"
 *                  redirects that broke the flow.
 *   3. Overlay   — structured editor for the auto-generated deck overlay.
 *                  Approve writes the production overlay JSON.
 *   4. Delivery  — cadence + recipient. Finishing flips the topic to
 *                  'active' status.
 *
 * Wizard state lives in localStorage keyed by topic name so users can
 * close the modal and resume.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, X, Check, ChevronRight, AlertTriangle, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface Props {
  open: boolean;
  onClose: () => void;
  onCompleted?: (topic: string) => void;
  /** Kept for backwards compatibility with App.tsx wiring — no longer
   *  triggered by the wizard itself. */
  onNavigateToHorizons?: (topic: string) => void;
  onNavigateToTracker?: (topic: string) => void;
  initialTopic?: string;
  initialStep?: number;
}

type StepIdx = 1 | 2 | 3 | 4;

interface TopicMeta {
  topic: string;
  display_name: string | null;
  description: string | null;
  owner: string | null;
  status: 'draft' | 'active' | 'archived';
  tags: string[] | null;
  overlay_status: 'missing' | 'auto_generated' | 'human_reviewed';
}

interface LifecycleRow extends TopicMeta {
  assessment_id: string | null;
  assessed_at: string | null;
  cadence: 'monthly' | 'quarterly' | 'none' | null;
  recipient_email: string | null;
}

interface DeckScenario {
  deck_scenario_name: string;
  horizon: string;
  consensus_pct: number;
  primary_signal: string;
  minority_view?: string;
  decision_fork?: { favorable?: string; adverse?: string };
  action_windows?: { '0_6_months'?: string; '6_18_months'?: string; '18_plus_months'?: string };
}

interface Overlay {
  topic: string;
  display_name?: string;
  description?: string;
  source_run_id?: string;
  deck_scenarios: Record<string, DeckScenario>;
  scenario_title_to_deck_key: Record<string, string>;
}

const STORAGE_PREFIX = 'addTopicWizard:';
const STEP_LABELS = ['Framing', 'Build', 'Overlay', 'Delivery'];

function loadState(topic: string): { step: StepIdx; overlay?: Overlay } {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + topic);
    return raw ? JSON.parse(raw) : { step: 1 };
  } catch {
    return { step: 1 };
  }
}

function saveState(topic: string, state: { step: StepIdx; overlay?: Overlay }) {
  try { localStorage.setItem(STORAGE_PREFIX + topic, JSON.stringify(state)); } catch {}
}

function clearState(topic: string) {
  try { localStorage.removeItem(STORAGE_PREFIX + topic); } catch {}
}

export function AddTopicWizard({
  open, onClose, onCompleted,
  initialTopic, initialStep,
}: Props) {
  const [step, setStep] = useState<StepIdx>((initialStep as StepIdx) || 1);
  const [name, setName] = useState(initialTopic || '');
  const [displayName, setDisplayName] = useState('');
  const [description, setDescription] = useState('');
  const [owner, setOwner] = useState('');
  const [tagsInput, setTagsInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [, setMeta] = useState<TopicMeta | null>(null);
  const [lifecycle, setLifecycle] = useState<LifecycleRow | null>(null);
  const [overlay, setOverlay] = useState<Overlay | null>(null);

  // Step 2 — build pipeline progress
  const [buildTaskId, setBuildTaskId] = useState<string | null>(null);
  const [buildPct, setBuildPct] = useState(0);
  const [buildStatus, setBuildStatus] = useState('');

  // Step 3 — overlay generation (only needed if .proposed was lost or never written)
  const [generateTaskId, setGenerateTaskId] = useState<string | null>(null);
  const [generateStatus, setGenerateStatus] = useState<string>('');
  const [generatePct, setGeneratePct] = useState(0);

  // Step 4 — delivery
  const [cadence, setCadence] = useState<'monthly' | 'quarterly' | 'none'>('none');
  const [recipient, setRecipient] = useState('');

  // Restore wizard state when the modal opens with an initialTopic
  useEffect(() => {
    if (!open) return;
    if (initialTopic) {
      const s = loadState(initialTopic);
      if (s.step) setStep(s.step);
      if (s.overlay) setOverlay(s.overlay);
      setName(initialTopic);
    } else {
      // Fresh wizard — reset state so the modal isn't poisoned by the
      // previous run.
      setStep((initialStep as StepIdx) || 1);
      setName('');
      setDisplayName('');
      setDescription('');
      setOwner('');
      setTagsInput('');
      setOverlay(null);
      setBuildTaskId(null);
      setBuildPct(0);
      setBuildStatus('');
      setError(null);
    }
  }, [open, initialTopic, initialStep]);

  const persist = useCallback((nextStep: StepIdx, nextOverlay?: Overlay | null) => {
    if (!name) return;
    saveState(name, { step: nextStep, overlay: nextOverlay ?? overlay ?? undefined });
  }, [name, overlay]);

  const refreshLifecycle = useCallback(async () => {
    if (!name) return null;
    try {
      const r = await fetch('/api/forecast/topics');
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const data = await r.json();
      const row = (data.topics || []).find((t: LifecycleRow) => t.topic === name) || null;
      setLifecycle(row);
      if (row) {
        setCadence((row.cadence || 'none') as any);
        setRecipient(row.recipient_email || '');
      }
      return row as LifecycleRow | null;
    } catch (e: any) {
      setError(e?.message || 'Failed to load lifecycle');
      return null;
    }
  }, [name]);

  useEffect(() => {
    if (open && step >= 2 && name) refreshLifecycle();
  }, [open, step, name, refreshLifecycle]);

  // If the wizard opens directly at step 3 (overlay review — e.g. after
  // candidate promotion) and we don't yet have an overlay loaded, fetch
  // the .proposed file the pipeline wrote.
  useEffect(() => {
    if (!open || step !== 3 || !name || overlay) return;
    let cancelled = false;
    (async () => {
      try {
        const pr = await fetch(
          `/api/forecast/topics/${encodeURIComponent(name)}/overlay/proposed`,
        );
        if (cancelled || !pr.ok) return;
        const pj = await pr.json();
        if (pj?.overlay) {
          setOverlay(pj.overlay);
          persist(3, pj.overlay);
        }
      } catch {
        // Step 3 panel offers a "Generate overlay" button when no
        // proposal exists yet.
      }
    })();
    return () => { cancelled = true; };
  }, [open, step, name, overlay, persist]);

  // ── Step 1 — name & framing
  const createMetadata = async () => {
    setBusy(true); setError(null);
    try {
      const parsedTags = tagsInput.split(',').map(s => s.trim()).filter(Boolean);
      const r = await fetch('/api/forecast/topics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: name.trim(),
          display_name: displayName.trim() || null,
          description: description.trim() || null,
          owner: owner.trim() || null,
          tags: parsedTags.length ? parsedTags : null,
        }),
      });
      if (!r.ok) {
        const t = await r.text();
        throw new Error(`${r.status} ${t || r.statusText}`);
      }
      const data = await r.json();
      setMeta(data.topic);
      setStep(2); persist(2);
    } catch (e: any) {
      setError(e?.message || 'Failed to create topic');
    } finally {
      setBusy(false);
    }
  };

  // ── Step 2 — build pipeline (horizons + assessment + overlay draft)
  const startBuild = async () => {
    setBusy(true); setError(null); setBuildPct(0); setBuildStatus('starting…');
    try {
      const r = await fetch(
        `/api/forecast/topics/${encodeURIComponent(name)}/wizard/build`,
        { method: 'POST' },
      );
      if (!r.ok) {
        const t = await r.text();
        throw new Error(`${r.status} ${t || r.statusText}`);
      }
      const data = await r.json();
      setBuildTaskId(data.task_id);
    } catch (e: any) {
      setError(e?.message || 'Failed to start build pipeline');
      setBusy(false);
    }
  };

  // Poll the build task — auto-advance to step 3 (overlay review) on completion.
  useEffect(() => {
    if (!buildTaskId) return;
    const handle = window.setInterval(async () => {
      try {
        const r = await fetch(`/api/forecast/assessment/job/${buildTaskId}`);
        if (!r.ok) return;
        const s = await r.json();
        setBuildPct(Math.round(s.progress || 0));
        setBuildStatus(s.current_item || s.status || '');
        if (s.status === 'completed') {
          window.clearInterval(handle);
          setBuildTaskId(null);
          setBusy(false);
          // Try to auto-load the .proposed overlay so step 3 has data
          try {
            const pr = await fetch(`/api/forecast/topics/${encodeURIComponent(name)}/overlay/proposed`);
            if (pr.ok) {
              const pj = await pr.json();
              if (pj?.overlay) {
                setOverlay(pj.overlay);
                persist(3, pj.overlay);
              }
            }
          } catch {}
          setStep(3); persist(3);
        } else if (s.status === 'failed' || s.status === 'error') {
          window.clearInterval(handle);
          setBuildTaskId(null);
          setError(s.error || 'Build pipeline failed');
          setBusy(false);
        }
      } catch {}
    }, 2000);
    return () => window.clearInterval(handle);
  }, [buildTaskId, name, persist]);

  // ── Step 3 — overlay regenerate (only used if no .proposed found)
  const startOverlayGen = async () => {
    setBusy(true); setError(null); setGenerateStatus('starting…'); setGeneratePct(0);
    try {
      const r = await fetch(`/api/forecast/topics/${encodeURIComponent(name)}/overlay/generate`, {
        method: 'POST',
      });
      if (!r.ok) {
        const t = await r.text();
        throw new Error(`${r.status} ${t || r.statusText}`);
      }
      const data = await r.json();
      setGenerateTaskId(data.task_id);
    } catch (e: any) {
      setError(e?.message || 'Failed to start overlay generation');
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!generateTaskId) return;
    const handle = window.setInterval(async () => {
      try {
        const r = await fetch(`/api/forecast/assessment/job/${generateTaskId}`);
        if (!r.ok) return;
        const s = await r.json();
        setGeneratePct(Math.round(s.progress || 0));
        setGenerateStatus(s.current_item || s.status || '');
        if (s.status === 'completed') {
          window.clearInterval(handle);
          setGenerateTaskId(null);
          const pr = await fetch(`/api/forecast/topics/${encodeURIComponent(name)}/overlay/proposed`);
          if (pr.ok) {
            const pj = await pr.json();
            setOverlay(pj.overlay);
            persist(3, pj.overlay);
          } else {
            setError('Generation completed but proposed overlay could not be loaded');
          }
          setBusy(false);
        } else if (s.status === 'failed') {
          window.clearInterval(handle);
          setGenerateTaskId(null);
          setError(s.error || 'Overlay generation failed');
          setBusy(false);
        }
      } catch {}
    }, 1500);
    return () => window.clearInterval(handle);
  }, [generateTaskId, name, persist]);

  const approveOverlay = async () => {
    if (!overlay) return;
    setBusy(true); setError(null);
    try {
      const r = await fetch(`/api/forecast/topics/${encodeURIComponent(name)}/overlay/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ overlay }),
      });
      if (!r.ok) {
        const t = await r.text();
        throw new Error(`${r.status} ${t || r.statusText}`);
      }
      setStep(4); persist(4);
    } catch (e: any) {
      setError(e?.message || 'Failed to approve overlay');
    } finally {
      setBusy(false);
    }
  };

  // ── Step 4 — delivery + finish
  const finish = async () => {
    setBusy(true); setError(null);
    try {
      if (cadence !== 'none') {
        const r = await fetch(`/api/forecast/topics/${encodeURIComponent(name)}/delivery`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cadence, recipient_email: recipient || null }),
        });
        if (!r.ok) {
          const t = await r.text();
          throw new Error(`${r.status} ${t || r.statusText}`);
        }
      }
      await fetch(`/api/forecast/topics/${encodeURIComponent(name)}/metadata`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'active' }),
      });
      clearState(name);
      onCompleted && onCompleted(name);
      onClose();
    } catch (e: any) {
      setError(e?.message || 'Failed to finalise');
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white dark:bg-gray-900 rounded-lg shadow-xl max-w-4xl w-full max-h-[92vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Add a new tracked topic</h3>
            <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">
              4 steps. Build runs the full horizons + assessment + overlay pipeline in the background (~10 min); you can close and resume.
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Stepper */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="flex items-center gap-2">
              <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-medium ${
                step === i ? 'bg-pink-600 text-white'
                  : step > i ? 'bg-emerald-600 text-white'
                  : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
              }`}>
                {step > i ? <Check className="w-3 h-3" /> : i}
              </span>
              <span className={`text-[11px] ${step === i ? 'font-semibold text-gray-900 dark:text-gray-100' : 'text-gray-500'}`}>
                {STEP_LABELS[i - 1]}
              </span>
              {i < 4 && <ChevronRight className="w-3 h-3 text-gray-400" />}
            </div>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {error && (
            <div className="text-xs bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 rounded p-2 flex items-start gap-2">
              <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" /> <span>{error}</span>
            </div>
          )}

          {step === 1 && (
            <Step1
              name={name} setName={setName}
              displayName={displayName} setDisplayName={setDisplayName}
              description={description} setDescription={setDescription}
              owner={owner} setOwner={setOwner}
              tagsInput={tagsInput} setTagsInput={setTagsInput}
            />
          )}

          {step === 2 && (
            <Step2Build
              topic={name}
              lifecycle={lifecycle}
              busy={!!buildTaskId || busy}
              pct={buildPct}
              status={buildStatus}
              onBuild={startBuild}
              onSkipToOverlay={() => { setStep(3); persist(3); }}
            />
          )}

          {step === 3 && (
            <Step3Overlay
              topic={name}
              overlay={overlay}
              setOverlay={(o) => { setOverlay(o); persist(3, o); }}
              busy={busy}
              genPct={generatePct}
              genStatus={generateStatus}
              onGenerate={startOverlayGen}
            />
          )}

          {step === 4 && (
            <Step4Delivery
              cadence={cadence} setCadence={setCadence}
              recipient={recipient} setRecipient={setRecipient}
            />
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-gray-200 dark:border-gray-700">
          <button
            type="button"
            onClick={() => { setStep((Math.max(1, step - 1)) as StepIdx); persist((Math.max(1, step - 1)) as StepIdx); }}
            disabled={step === 1 || busy || !!buildTaskId}
            className="text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-700 rounded text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
          >
            Back
          </button>
          {step === 1 && (
            <Button onClick={createMetadata} disabled={busy || !name.trim()} className="text-xs bg-pink-600 hover:bg-pink-700 text-white h-7 px-3 py-0">
              {busy ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : null} Save & continue
            </Button>
          )}
          {step === 2 && lifecycle?.assessment_id && !buildTaskId && (
            <Button onClick={() => { setStep(3); persist(3); }} className="text-xs bg-pink-600 hover:bg-pink-700 text-white h-7 px-3 py-0">
              Continue to overlay
            </Button>
          )}
          {step === 3 && (
            <Button onClick={approveOverlay} disabled={busy || !overlay} className="text-xs bg-pink-600 hover:bg-pink-700 text-white h-7 px-3 py-0">
              {busy ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : null} Approve overlay & continue
            </Button>
          )}
          {step === 4 && (
            <Button onClick={finish} disabled={busy} className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white h-7 px-3 py-0">
              {busy ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : null} Finish — activate topic
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}


// ── Step 1
function Step1({ name, setName, displayName, setDisplayName, description, setDescription, owner, setOwner, tagsInput, setTagsInput }: any) {
  return (
    <div className="space-y-3">
      <h4 className="font-medium text-gray-900 dark:text-gray-100">Name & framing</h4>
      <p className="text-xs text-gray-600 dark:text-gray-300">
        The topic name is the universal join key — it must match the name stored on articles in the corpus (or the name you'll tag new articles with going forward). Pick the deck-friendly form (e.g. "Patent Cliffs").
      </p>
      <Field label="Topic name *">
        <input value={name} onChange={e => setName(e.target.value)} placeholder="Patent Cliffs"
               className="w-full text-sm px-2 py-1.5 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100" />
      </Field>
      <Field label="Display name (optional)">
        <input value={displayName} onChange={e => setDisplayName(e.target.value)} placeholder="Shown in the deck if different from the canonical name"
               className="w-full text-sm px-2 py-1.5 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100" />
      </Field>
      <Field label="Description">
        <textarea value={description} onChange={e => setDescription(e.target.value)} rows={2}
                  placeholder="1-2 sentence framing — appears in the Topics dashboard and onboarding docs"
                  className="w-full text-sm px-2 py-1.5 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Owner (username)">
          <input value={owner} onChange={e => setOwner(e.target.value)} placeholder="e.g. admin"
                 className="w-full text-sm px-2 py-1.5 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100" />
        </Field>
        <Field label="Tags (comma-separated)">
          <input value={tagsInput} onChange={e => setTagsInput(e.target.value)} placeholder="pharma, regulation"
                 className="w-full text-sm px-2 py-1.5 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100" />
        </Field>
      </div>
    </div>
  );
}

// ── Step 2 — build pipeline inline
function Step2Build({ topic, lifecycle, busy, pct, status, onBuild, onSkipToOverlay }: {
  topic: string; lifecycle: LifecycleRow | null;
  busy: boolean; pct: number; status: string;
  onBuild: () => void; onSkipToOverlay: () => void;
}) {
  const alreadyAssessed = !!lifecycle?.assessment_id;
  return (
    <div className="space-y-3">
      <h4 className="font-medium text-gray-900 dark:text-gray-100">Build the pipeline</h4>
      <p className="text-xs text-gray-600 dark:text-gray-300">
        We'll run three things for you in the background:
      </p>
      <ol className="list-decimal ml-5 text-xs text-gray-700 dark:text-gray-200 space-y-1">
        <li>A Three Horizons projection seeded with recent articles tagged <code className="px-1 py-0.5 bg-gray-100 dark:bg-gray-800 rounded font-mono text-[11px]">{topic}</code> in the corpus.</li>
        <li>A paired (live + placebo) assessment of the new forecast against the post-forecast window.</li>
        <li>A draft deck overlay mapping the 10-14 raw scenarios into 4-5 deck-level scenarios.</li>
      </ol>
      <p className="text-xs text-gray-600 dark:text-gray-300">
        Total runtime ≈ 8-12 minutes. The wizard polls progress — you can close this and resume.
      </p>

      {alreadyAssessed && !busy && (
        <div className="rounded p-3 border bg-emerald-50 dark:bg-emerald-900/30 border-emerald-200 dark:border-emerald-800">
          <div className="text-xs text-gray-900 dark:text-gray-100 font-medium">
            This topic already has a stored assessment ({lifecycle?.assessed_at?.slice(0, 10) || '—'}).
          </div>
          <div className="text-[11px] text-gray-700 dark:text-gray-200 mt-1">
            You can skip the build and go straight to the overlay review, or re-run the pipeline to refresh the forecast and assessment.
          </div>
          <div className="mt-2 flex gap-2">
            <Button onClick={onSkipToOverlay} className="text-[11px] bg-emerald-600 hover:bg-emerald-700 text-white h-6 px-3 py-0">
              Skip to overlay
            </Button>
            <Button onClick={onBuild} disabled={busy} className="text-[11px] bg-pink-600 hover:bg-pink-700 text-white h-6 px-3 py-0">
              Re-run build
            </Button>
          </div>
        </div>
      )}

      {!alreadyAssessed && !busy && (
        <Button onClick={onBuild} disabled={busy} className="text-xs bg-pink-600 hover:bg-pink-700 text-white h-7 px-3 py-0 inline-flex items-center">
          <Sparkles className="w-3 h-3 mr-1" /> Run build pipeline
        </Button>
      )}

      {busy && (
        <div className="rounded border border-pink-200 dark:border-pink-800 bg-pink-50/60 dark:bg-pink-900/20 p-3 space-y-2">
          <div className="text-xs font-medium text-pink-900 dark:text-pink-100 inline-flex items-center gap-2">
            <Loader2 className="w-3 h-3 animate-spin" /> Building pipeline · {pct}%
          </div>
          <div className="w-full bg-pink-100 dark:bg-pink-900/40 h-1.5 rounded overflow-hidden">
            <div className="bg-pink-600 h-full transition-all" style={{ width: `${pct}%` }} />
          </div>
          <div className="text-[11px] text-pink-900 dark:text-pink-100 truncate">{status}</div>
          <p className="text-[10px] text-gray-600 dark:text-gray-300">
            You can close this modal — the job runs server-side and will be picked up when you reopen the wizard for this topic.
          </p>
        </div>
      )}
    </div>
  );
}

// ── Step 3 — overlay review (structured editor)
function Step3Overlay({ topic, overlay, setOverlay, busy, genPct, genStatus, onGenerate }: {
  topic: string; overlay: Overlay | null; setOverlay: (o: Overlay) => void;
  busy: boolean; genPct: number; genStatus: string; onGenerate: () => void;
}) {
  const scenarioKeys = useMemo(() => Object.keys(overlay?.deck_scenarios || {}), [overlay]);
  if (!overlay) {
    return (
      <div className="space-y-3">
        <h4 className="font-medium text-gray-900 dark:text-gray-100">Deck overlay — auto-generated proposal</h4>
        <p className="text-xs text-gray-600 dark:text-gray-300">
          The overlay groups raw Three Horizons scenarios into 4-5 deck-level scenarios with consensus / signal / decision-fork framing. The build pipeline should have drafted one already — if it didn't, generate a fresh proposal you can edit before saving.
        </p>
        <Button onClick={onGenerate} disabled={busy} className="text-xs bg-pink-600 hover:bg-pink-700 text-white h-7 px-3 py-0">
          {busy ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : null}
          {busy ? `Generating… ${genPct}%` : 'Generate overlay proposal'}
        </Button>
        {busy && (
          <div className="text-[11px] text-gray-600 dark:text-gray-300">
            <div className="w-full bg-gray-200 dark:bg-gray-800 h-1.5 rounded overflow-hidden">
              <div className="bg-pink-500 h-full transition-all" style={{ width: `${genPct}%` }} />
            </div>
            <div className="mt-1">{genStatus}</div>
          </div>
        )}
      </div>
    );
  }

  const updateScenario = (key: string, patch: Partial<DeckScenario>) => {
    setOverlay({
      ...overlay,
      deck_scenarios: { ...overlay.deck_scenarios, [key]: { ...overlay.deck_scenarios[key], ...patch } },
    });
  };

  const updateFork = (key: string, branch: 'favorable' | 'adverse', value: string) => {
    const s = overlay.deck_scenarios[key];
    setOverlay({
      ...overlay,
      deck_scenarios: { ...overlay.deck_scenarios, [key]: {
        ...s,
        decision_fork: { ...(s.decision_fork || {}), [branch]: value },
      }},
    });
  };

  const updateWindow = (key: string, slot: '0_6_months' | '6_18_months' | '18_plus_months', value: string) => {
    const s = overlay.deck_scenarios[key];
    setOverlay({
      ...overlay,
      deck_scenarios: { ...overlay.deck_scenarios, [key]: {
        ...s,
        action_windows: { ...(s.action_windows || {}), [slot]: value },
      }},
    });
  };

  return (
    <div className="space-y-3">
      <h4 className="font-medium text-gray-900 dark:text-gray-100">Review the {scenarioKeys.length} deck scenarios</h4>
      <p className="text-xs text-gray-600 dark:text-gray-300">
        Edit the fields below. Auto-generated content is a starting point — sharpen the primary signals (name concrete actors) and write the decision-fork branches if blank. The mini-preview shows how each card will appear in the Strategic Domains slide.
      </p>
      <div className="space-y-3">
        {scenarioKeys.map(key => {
          const s = overlay.deck_scenarios[key];
          return (
            <div key={key} className="border border-gray-200 dark:border-gray-700 rounded p-3 bg-gray-50 dark:bg-gray-800/40">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Field label="Deck name">
                    <input value={s.deck_scenario_name} onChange={e => updateScenario(key, { deck_scenario_name: e.target.value })}
                           className="w-full text-sm px-2 py-1 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100" />
                  </Field>
                  <div className="grid grid-cols-2 gap-2">
                    <Field label="Horizon">
                      <select value={s.horizon} onChange={e => updateScenario(key, { horizon: e.target.value })}
                              className="w-full text-sm px-2 py-1 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
                        {['h1','h2','h3','h1_h2','h2_h3'].map(h => <option key={h} value={h}>{h}</option>)}
                      </select>
                    </Field>
                    <Field label="Consensus %">
                      <input type="number" min={0} max={100} value={s.consensus_pct}
                             onChange={e => updateScenario(key, { consensus_pct: Number(e.target.value) })}
                             className="w-full text-sm px-2 py-1 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100" />
                    </Field>
                  </div>
                  <Field label="Primary signal">
                    <textarea value={s.primary_signal || ''} rows={3} onChange={e => updateScenario(key, { primary_signal: e.target.value })}
                              className="w-full text-sm px-2 py-1 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100" />
                  </Field>
                  <Field label="Minority view">
                    <textarea value={s.minority_view || ''} rows={2} onChange={e => updateScenario(key, { minority_view: e.target.value })}
                              className="w-full text-sm px-2 py-1 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100" />
                  </Field>
                </div>
                <div className="space-y-2">
                  <Field label="Decision fork — favorable">
                    <textarea value={s.decision_fork?.favorable || ''} rows={2}
                              onChange={e => updateFork(key, 'favorable', e.target.value)}
                              className="w-full text-sm px-2 py-1 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100" />
                  </Field>
                  <Field label="Decision fork — adverse">
                    <textarea value={s.decision_fork?.adverse || ''} rows={2}
                              onChange={e => updateFork(key, 'adverse', e.target.value)}
                              className="w-full text-sm px-2 py-1 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100" />
                  </Field>
                  <Field label="Action window — 0-6 months">
                    <input value={s.action_windows?.['0_6_months'] || ''}
                           onChange={e => updateWindow(key, '0_6_months', e.target.value)}
                           className="w-full text-sm px-2 py-1 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100" />
                  </Field>
                  <Field label="Action window — 6-18 months">
                    <input value={s.action_windows?.['6_18_months'] || ''}
                           onChange={e => updateWindow(key, '6_18_months', e.target.value)}
                           className="w-full text-sm px-2 py-1 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100" />
                  </Field>
                </div>
              </div>
              {/* Mini-preview matching the Strategic Domains card layout */}
              <div className="mt-3 border-l-4 border-pink-500 pl-2">
                <div className="text-[10px] uppercase tracking-wide text-pink-600 font-semibold">Preview — Strategic Domains card</div>
                <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded mt-1 p-2 text-[11px]">
                  <div className="bg-pink-600 text-white px-2 py-1 rounded-t font-semibold">{s.deck_scenario_name || '(deck name)'}</div>
                  <div className="text-pink-600 italic mt-1">Original consensus {s.consensus_pct}%  ·  {s.horizon.toUpperCase()}</div>
                  <div className="font-semibold text-gray-700 dark:text-gray-200 mt-1 text-[10px] tracking-wide">PRIMARY SIGNAL</div>
                  <div className="text-gray-700 dark:text-gray-200 line-clamp-3">{s.primary_signal || <span className="italic text-gray-400">(primary signal will appear here)</span>}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Step 4 — delivery
function Step4Delivery({ cadence, setCadence, recipient, setRecipient }: any) {
  return (
    <div className="space-y-3">
      <h4 className="font-medium text-gray-900 dark:text-gray-100">Delivery cadence</h4>
      <p className="text-xs text-gray-600 dark:text-gray-300">
        Set how often this topic should be included in the recurring Wiley bundle, and where it should ship. You can leave this as "none" and configure later from the Wiley Deliverables panel.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Cadence">
          <select value={cadence} onChange={e => setCadence(e.target.value)}
                  className="w-full text-sm px-2 py-1.5 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
            <option value="none">None</option>
            <option value="monthly">Monthly</option>
            <option value="quarterly">Quarterly</option>
          </select>
        </Field>
        <Field label="Recipient email">
          <input type="email" value={recipient} onChange={e => setRecipient(e.target.value)} placeholder="director@example.com"
                 className="w-full text-sm px-2 py-1.5 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100" />
        </Field>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: any }) {
  return (
    <label className="block">
      <div className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-0.5 font-medium">{label}</div>
      {children}
    </label>
  );
}
