/**
 * AddTopicWizard — 5-step modal that walks a non-developer through adding
 * a new tracked topic.
 *
 * v1 strategy: don't reinvent existing tab flows. Steps 2 (Three Horizons)
 * and 3 (paired assessment) DETECT existing work and link out to the
 * already-built UI for those flows. The wizard's own UI focuses on:
 *   - step 1: name + framing → metadata row in 'draft'
 *   - step 4: overlay review (generate → edit structured form → approve)
 *   - step 5: delivery cadence + recipient
 *
 * Wizard state lives in localStorage keyed by topic name so users can
 * close the modal and resume.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, X, Check, ChevronRight, ExternalLink, AlertTriangle, RefreshCw, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface Props {
  open: boolean;
  onClose: () => void;
  onCompleted?: (topic: string) => void;
  onNavigateToHorizons?: (topic: string) => void;
  onNavigateToTracker?: (topic: string) => void;
  initialTopic?: string;
  initialStep?: number;
}

type StepIdx = 1 | 2 | 3 | 4 | 5;

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
  open, onClose, onCompleted, onNavigateToHorizons, onNavigateToTracker,
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
  const [meta, setMeta] = useState<TopicMeta | null>(null);
  const [lifecycle, setLifecycle] = useState<LifecycleRow | null>(null);
  const [overlay, setOverlay] = useState<Overlay | null>(null);
  const [generateTaskId, setGenerateTaskId] = useState<string | null>(null);
  const [generateStatus, setGenerateStatus] = useState<string>('');
  const [generatePct, setGeneratePct] = useState(0);
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
    }
  }, [open, initialTopic]);

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

  // ── Step 4 — overlay generate + review + approve
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

  // Poll the overlay generation task; on completion, fetch the proposed JSON
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
            persist(4, pj.overlay);
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
      setStep(5); persist(5);
    } catch (e: any) {
      setError(e?.message || 'Failed to approve overlay');
    } finally {
      setBusy(false);
    }
  };

  // ── Step 5 — delivery + finish
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
      // Flip metadata.status to active (overlay approve already does this,
      // but covers the "skipped step 4" case)
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
            <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">5 steps. You can close this and resume any time.</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Stepper */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="flex items-center gap-2">
              <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-medium ${
                step === i ? 'bg-pink-600 text-white' : step > i ? 'bg-emerald-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
              }`}>
                {step > i ? <Check className="w-3 h-3" /> : i}
              </span>
              <span className={`text-[11px] ${step === i ? 'font-semibold text-gray-900 dark:text-gray-100' : 'text-gray-500'}`}>
                {['Framing', 'Horizons', 'Assessment', 'Overlay', 'Delivery'][i - 1]}
              </span>
              {i < 5 && <ChevronRight className="w-3 h-3 text-gray-400" />}
            </div>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {error && (
            <div className="text-xs bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 rounded p-2 flex items-start gap-2">
              <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" /> <span>{error}</span>
            </div>
          )}

          {/* ── Step 1: Name & framing ── */}
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
            <Step2Check
              kind="horizons"
              ready={!!lifecycle && lifecycle.status !== 'draft' /* heuristic: backend uses runs not in API yet */}
              topic={name}
              lifecycle={lifecycle}
              onRefresh={refreshLifecycle}
              onNavigate={() => onNavigateToHorizons && onNavigateToHorizons(name)}
            />
          )}

          {step === 3 && (
            <Step2Check
              kind="assessment"
              ready={!!lifecycle?.assessment_id}
              topic={name}
              lifecycle={lifecycle}
              onRefresh={refreshLifecycle}
              onNavigate={() => onNavigateToTracker && onNavigateToTracker(name)}
            />
          )}

          {step === 4 && (
            <Step4Overlay
              topic={name}
              overlay={overlay}
              setOverlay={(o) => { setOverlay(o); persist(4, o); }}
              busy={busy}
              genPct={generatePct}
              genStatus={generateStatus}
              onGenerate={startOverlayGen}
            />
          )}

          {step === 5 && (
            <Step5Delivery
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
            disabled={step === 1 || busy}
            className="text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-700 rounded text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
          >
            Back
          </button>
          {step === 1 && (
            <Button onClick={createMetadata} disabled={busy || !name.trim()} className="text-xs bg-pink-600 hover:bg-pink-700 text-white h-7 px-3 py-0">
              {busy ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : null} Save & continue
            </Button>
          )}
          {(step === 2 || step === 3) && (
            <Button onClick={() => { setStep((step + 1) as StepIdx); persist((step + 1) as StepIdx); }} className="text-xs bg-pink-600 hover:bg-pink-700 text-white h-7 px-3 py-0">
              Continue
            </Button>
          )}
          {step === 4 && (
            <Button onClick={approveOverlay} disabled={busy || !overlay} className="text-xs bg-pink-600 hover:bg-pink-700 text-white h-7 px-3 py-0">
              {busy ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : null} Approve overlay & continue
            </Button>
          )}
          {step === 5 && (
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
        The topic name is the universal join key — it must match the name you'll use in the Future Horizons tab and the eventual Wiley deck. Pick the deck-friendly form (e.g. "Patent Cliffs").
      </p>
      <Field label="Topic name *">
        <input value={name} onChange={e => setName(e.target.value)} placeholder="Patent Cliffs"
               className="w-full text-sm px-2 py-1.5 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100" />
      </Field>
      <Field label="Display name (optional)">
        <input value={displayName} onChange={e => setDisplayName(e.target.value)} placeholder="shown in the deck if different from the canonical name"
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

// ── Step 2 / 3 — "is the prerequisite work done?"
function Step2Check({ kind, ready, topic, lifecycle, onRefresh, onNavigate }: {
  kind: 'horizons' | 'assessment'; ready: boolean; topic: string; lifecycle: LifecycleRow | null;
  onRefresh: () => Promise<any>; onNavigate: () => void;
}) {
  const isHorizons = kind === 'horizons';
  return (
    <div className="space-y-3">
      <h4 className="font-medium text-gray-900 dark:text-gray-100">
        {isHorizons ? 'Three Horizons forecast' : 'First paired assessment'}
      </h4>
      <p className="text-xs text-gray-600 dark:text-gray-300">
        {isHorizons
          ? `The deck overlay is built from the Three Horizons scenarios for this topic. Run a Three Horizons analysis on the Future Horizons tab using the exact topic name '${topic}', then come back.`
          : `The overlay generator needs at least one live paired assessment so it has supports/contradicts data to anchor consensus_pct on. Go to the Forecast Tracker tab and run a paired assessment for '${topic}'.`
        }
      </p>
      <div className={`rounded p-3 border ${ready
        ? 'bg-emerald-50 dark:bg-emerald-900/30 border-emerald-200 dark:border-emerald-800'
        : 'bg-amber-50 dark:bg-amber-900/30 border-amber-200 dark:border-amber-800'
      }`}>
        <div className="text-xs font-medium text-gray-900 dark:text-gray-100">
          {ready ? (isHorizons ? 'Topic is registered in the lifecycle index.' : 'Latest assessment detected.')
                 : (isHorizons ? 'Topic not yet in the lifecycle index.' : 'No live assessment recorded yet.')}
        </div>
        {ready && lifecycle && !isHorizons && (
          <div className="text-[11px] text-gray-700 dark:text-gray-200 mt-1">
            assessed {lifecycle.assessed_at?.slice(0, 10) || '—'}
          </div>
        )}
        <div className="mt-2 flex gap-2">
          <button onClick={onNavigate} className="text-[11px] inline-flex items-center px-2 py-1 border border-gray-300 dark:border-gray-700 rounded hover:bg-white dark:hover:bg-gray-800">
            <ExternalLink className="w-3 h-3 mr-1" /> Open {isHorizons ? 'Future Horizons' : 'Forecast Tracker'}
          </button>
          <button onClick={onRefresh} className="text-[11px] inline-flex items-center px-2 py-1 border border-gray-300 dark:border-gray-700 rounded hover:bg-white dark:hover:bg-gray-800">
            <RefreshCw className="w-3 h-3 mr-1" /> Refresh
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Step 4 — overlay review (structured editor)
function Step4Overlay({ topic, overlay, setOverlay, busy, genPct, genStatus, onGenerate }: {
  topic: string; overlay: Overlay | null; setOverlay: (o: Overlay) => void;
  busy: boolean; genPct: number; genStatus: string; onGenerate: () => void;
}) {
  const scenarioKeys = useMemo(() => Object.keys(overlay?.deck_scenarios || {}), [overlay]);
  if (!overlay) {
    return (
      <div className="space-y-3">
        <h4 className="font-medium text-gray-900 dark:text-gray-100">Deck overlay — auto-generated proposal</h4>
        <p className="text-xs text-gray-600 dark:text-gray-300">
          The overlay groups raw Three Horizons scenarios into 4-5 deck-level scenarios with consensus / signal / decision-fork framing. We'll generate a proposal you can edit before saving as the production overlay.
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

// ── Step 5 — delivery
function Step5Delivery({ cadence, setCadence, recipient, setRecipient }: any) {
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
