/**
 * Brand Watcher first-run onboarding wizard.
 *
 * Shown when the Brand Watcher tab loads with zero configured brands
 * (the state every freshly provisioned dedicated tenant starts in).
 * Sets up the primary brand plus at least one competitor, then creates
 * everything through the existing API: POST /brands per brand,
 * /setup-monitoring per brand (topic + keyword group), and /set-primary.
 */

import { useState } from 'react';
import { Target, Sparkles, Plus, X, Loader2, Check, ArrowRight, ArrowLeft, AlertCircle } from 'lucide-react';
import {
  createBrand, setPrimaryBrand, setupBrandMonitoring, suggestKeywords,
} from '../../services/brandWatcherApi';

interface WizardBrand {
  display_name: string;
  description: string;
  keywords: string[];
}

const COMPETITOR_COLORS = ['#9333ea', '#059669', '#d97706', '#dc2626', '#0891b2'];
const PRIMARY_COLOR = '#2563eb';

function emptyBrand(): WizardBrand {
  return { display_name: '', description: '', keywords: [] };
}

function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'brand';
}

function ChipsInput({ label, hint, keywords, onChange }: {
  label: string;
  hint?: string;
  keywords: string[];
  onChange: (next: string[]) => void;
}) {
  const [input, setInput] = useState('');
  const add = (raw: string) => {
    const v = raw.trim();
    if (v && !keywords.includes(v)) onChange([...keywords, v]);
  };
  return (
    <div>
      <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{label}</label>
      <div className="flex flex-wrap gap-1 mb-1">
        {keywords.map(kw => (
          <span key={kw} className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-xs">
            {kw}
            <button onClick={() => onChange(keywords.filter(k => k !== kw))} className="hover:text-red-500">
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
      </div>
      <input
        type="text"
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            add(input);
            setInput('');
          }
        }}
        onBlur={() => { add(input); setInput(''); }}
        placeholder="Type and press Enter"
        className="w-full px-2 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800 dark:text-gray-100"
      />
      {hint && <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-1">{hint}</p>}
    </div>
  );
}

export function BrandWatcherOnboarding({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0); // 0 primary, 1 competitors, 2 review
  const [primary, setPrimary] = useState<WizardBrand>(emptyBrand());
  const [competitors, setCompetitors] = useState<WizardBrand[]>([emptyBrand()]);
  const [suggestedCompetitors, setSuggestedCompetitors] = useState<string[]>([]);
  const [suggesting, setSuggesting] = useState<string | null>(null); // 'primary' | 'comp-N'
  const [creating, setCreating] = useState(false);
  const [progress, setProgress] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const suggest = async (which: 'primary' | number) => {
    const brand = which === 'primary' ? primary : competitors[which];
    if (!brand.display_name.trim()) return;
    setSuggesting(which === 'primary' ? 'primary' : `comp-${which}`);
    setError(null);
    try {
      const s = await suggestKeywords(brand.display_name.trim(), brand.description.trim() || undefined);
      const merged = Array.from(new Set([...brand.keywords, ...(s.brand_keywords || [])]));
      if (which === 'primary') {
        setPrimary(p => ({ ...p, keywords: merged }));
        setSuggestedCompetitors((s.competitor_keywords || []).slice(0, 6));
      } else {
        setCompetitors(cs => cs.map((c, i) => i === which ? { ...c, keywords: merged } : c));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Keyword suggestion failed');
    } finally {
      setSuggesting(null);
    }
  };

  const updateCompetitor = (i: number, patch: Partial<WizardBrand>) => {
    setCompetitors(cs => cs.map((c, idx) => idx === i ? { ...c, ...patch } : c));
  };

  const validCompetitors = competitors.filter(c => c.display_name.trim());
  const primaryReady = primary.display_name.trim().length > 0;
  const competitorsReady = validCompetitors.length >= 1;

  const launch = async () => {
    setCreating(true);
    setError(null);
    setProgress([]);
    const note = (m: string) => setProgress(p => [...p, m]);
    try {
      const mk = (b: WizardBrand, color: string) => ({
        name: slugify(b.display_name),
        display_name: b.display_name.trim(),
        description: b.description.trim() || undefined,
        brand_keywords: b.keywords.length ? b.keywords : [b.display_name.trim()],
        color,
      });
      const created = await createBrand(mk(primary, PRIMARY_COLOR));
      note(`Created brand ${created.display_name}`);
      await setPrimaryBrand(created.id);
      note(`${created.display_name} set as primary brand`);
      await setupBrandMonitoring(created.id);
      note(`Monitoring topic + keyword group created for ${created.display_name}`);
      for (let i = 0; i < validCompetitors.length; i++) {
        const comp = await createBrand(mk(validCompetitors[i], COMPETITOR_COLORS[i % COMPETITOR_COLORS.length]));
        note(`Created competitor ${comp.display_name}`);
        await setupBrandMonitoring(comp.id);
        note(`Monitoring set up for ${comp.display_name}`);
      }
      note('Done — collection starts on the next ingest cycle');
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Setup failed');
      setCreating(false);
    }
  };

  const stepDot = (i: number, label: string) => (
    <div className="flex items-center gap-1.5">
      <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-semibold ${
        step > i ? 'bg-green-500 text-white' : step === i ? 'bg-blue-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400'}`}>
        {step > i ? <Check className="w-3 h-3" /> : i + 1}
      </div>
      <span className={`text-xs ${step === i ? 'text-gray-900 dark:text-gray-100 font-medium' : 'text-gray-400 dark:text-gray-500'}`}>{label}</span>
    </div>
  );

  return (
    <div className="flex items-start justify-center py-10 px-4">
      <div className="w-full max-w-2xl bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-gray-100 dark:border-gray-700">
          <div className="flex items-center gap-2 mb-1">
            <Target className="w-5 h-5 text-blue-600" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Set up Brand Watcher</h2>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Tell us which brand to protect and who to benchmark it against. This creates the
            monitoring topics and keyword groups — article collection starts automatically.
          </p>
          <div className="flex items-center gap-4 mt-4">
            {stepDot(0, 'Your brand')}
            <div className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
            {stepDot(1, 'Competitors')}
            <div className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
            {stepDot(2, 'Review & launch')}
          </div>
        </div>

        <div className="px-6 py-5 space-y-4">
          {/* Step 0: primary brand */}
          {step === 0 && (
            <>
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Brand name *</label>
                <input
                  type="text" value={primary.display_name} autoFocus
                  onChange={e => setPrimary(p => ({ ...p, display_name: e.target.value }))}
                  placeholder="e.g. Acme Publishing"
                  className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 dark:text-gray-100"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">What does this company do? (optional, improves suggestions)</label>
                <textarea
                  value={primary.description} rows={2}
                  onChange={e => setPrimary(p => ({ ...p, description: e.target.value }))}
                  placeholder="e.g. Academic publisher focused on scientific journals and research platforms"
                  className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 dark:text-gray-100"
                />
              </div>
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <ChipsInput
                    label="Monitoring keywords"
                    hint="Name variants the news would use: legal name, abbreviations, ticker. The brand name itself is always included."
                    keywords={primary.keywords}
                    onChange={kws => setPrimary(p => ({ ...p, keywords: kws }))}
                  />
                </div>
                <button
                  onClick={() => suggest('primary')}
                  disabled={!primaryReady || suggesting === 'primary'}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/30 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/50 disabled:opacity-50 whitespace-nowrap"
                  title="Ask the AI for name variants, tickers and likely competitors"
                >
                  {suggesting === 'primary' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                  Suggest
                </button>
              </div>
            </>
          )}

          {/* Step 1: competitors */}
          {step === 1 && (
            <>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                At least one competitor is required — benchmarks, share of voice and the
                comparison views need a peer to compare against.
              </p>
              {suggestedCompetitors.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] text-gray-400 dark:text-gray-500">Suggested:</span>
                  {suggestedCompetitors.map(name => (
                    <button key={name}
                      onClick={() => {
                        if (competitors.some(c => c.display_name === name)) return;
                        const blank = competitors.findIndex(c => !c.display_name.trim());
                        if (blank >= 0) updateCompetitor(blank, { display_name: name });
                        else setCompetitors(cs => [...cs, { ...emptyBrand(), display_name: name }]);
                      }}
                      className="px-2 py-0.5 text-xs bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 rounded hover:bg-purple-100 dark:hover:bg-purple-900/50">
                      + {name}
                    </button>
                  ))}
                </div>
              )}
              {competitors.map((c, i) => (
                <div key={i} className="p-3 border border-gray-200 dark:border-gray-700 rounded-lg space-y-2">
                  <div className="flex items-center gap-2">
                    <input
                      type="text" value={c.display_name}
                      onChange={e => updateCompetitor(i, { display_name: e.target.value })}
                      placeholder={`Competitor ${i + 1} name`}
                      className="flex-1 px-3 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 dark:text-gray-100"
                    />
                    <button
                      onClick={() => suggest(i)}
                      disabled={!c.display_name.trim() || suggesting === `comp-${i}`}
                      className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/30 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/50 disabled:opacity-50"
                      title="Suggest keyword variants for this competitor">
                      {suggesting === `comp-${i}` ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                    </button>
                    {competitors.length > 1 && (
                      <button onClick={() => setCompetitors(cs => cs.filter((_, idx) => idx !== i))}
                        className="text-gray-400 hover:text-red-500" title="Remove competitor">
                        <X className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                  {c.display_name.trim() && (
                    <ChipsInput label="Keywords" keywords={c.keywords}
                      onChange={kws => updateCompetitor(i, { keywords: kws })} />
                  )}
                </div>
              ))}
              <button onClick={() => setCompetitors(cs => [...cs, emptyBrand()])}
                className="flex items-center gap-1.5 text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline">
                <Plus className="w-3.5 h-3.5" /> Add another competitor
              </button>
            </>
          )}

          {/* Step 2: review + launch */}
          {step === 2 && (
            <>
              <div className="space-y-2">
                <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800 rounded-lg">
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {primary.display_name} <span className="text-[11px] font-normal text-blue-600 dark:text-blue-400">primary brand</span>
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    {(primary.keywords.length ? primary.keywords : [primary.display_name]).join(', ')}
                  </p>
                </div>
                {validCompetitors.map((c, i) => (
                  <div key={i} className="p-3 bg-gray-50 dark:bg-gray-750 border border-gray-200 dark:border-gray-700 rounded-lg">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {c.display_name} <span className="text-[11px] font-normal text-gray-400">competitor</span>
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                      {(c.keywords.length ? c.keywords : [c.display_name]).join(', ')}
                    </p>
                  </div>
                ))}
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                For each brand this creates a "Brand Monitoring" topic and a news keyword group.
                Collection begins on the next ingest cycle; the dashboard fills as articles arrive.
                Everything can be tuned later under Brand Watcher → gear icon.
              </p>
              {progress.length > 0 && (
                <div className="p-3 bg-gray-50 dark:bg-gray-750 rounded-lg space-y-1">
                  {progress.map((m, i) => (
                    <p key={i} className="text-xs text-gray-600 dark:text-gray-300 flex items-center gap-1.5">
                      <Check className="w-3 h-3 text-green-500 flex-shrink-0" /> {m}
                    </p>
                  ))}
                </div>
              )}
            </>
          )}

          {error && (
            <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-red-700 dark:text-red-300">{error}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-100 dark:border-gray-700 flex items-center justify-between">
          <button
            onClick={() => setStep(s => Math.max(0, s - 1))}
            disabled={step === 0 || creating}
            className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 disabled:opacity-40">
            <ArrowLeft className="w-4 h-4" /> Back
          </button>
          {step < 2 ? (
            <button
              onClick={() => setStep(s => s + 1)}
              disabled={step === 0 ? !primaryReady : !competitorsReady}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50">
              Next <ArrowRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={launch}
              disabled={creating}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50">
              {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Target className="w-4 h-4" />}
              {creating ? 'Setting up…' : 'Launch monitoring'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
