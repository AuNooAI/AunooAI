/**
 * The analyst's controls for one vendor on the Market Horizon.
 *
 * A multiplier per input (0 to 2, default 1) scales this vendor's weight on
 * that input — to discount posts that are noise, or emphasise a signal that
 * is real — a status (active, acquired, closed) with acquirer and date, and
 * a free-text note. Saved per vendor per market, applied on the next
 * compute, and printed beside the vendor on the horizon, so an adjustment is
 * never silent.
 */

import { useEffect, useState } from 'react';
import { Loader2, Save } from 'lucide-react';
import {
  getHorizonControls, saveHorizonControls, type HorizonControls,
} from '../../services/marketMonitorApi';

export function MarketVendorHorizonControls({ marketId, brandId }: {
  marketId: number; brandId: number;
}) {
  const [inputs, setInputs] = useState<Record<string, { label: string; axis: string; weight: number }>>({});
  const [form, setForm] = useState<HorizonControls | null>(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setForm(null); setMsg(null); setError(null);
    getHorizonControls(marketId, brandId)
      .then(d => { if (live) { setInputs(d.inputs); setForm(d.controls); } })
      .catch(e => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [marketId, brandId]);

  const save = async () => {
    if (!form) return;
    setSaving(true); setMsg(null); setError(null);
    try {
      const saved = await saveHorizonControls(marketId, brandId, {
        ...form,
        acquired_by: form.status === 'active' ? null : form.acquired_by,
        status_date: form.status === 'active' ? null : (form.status_date || null),
      });
      setForm(saved);
      setMsg('Saved. Applied on the next Market Horizon compute.');
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setSaving(false);
    }
  };

  const ordered = Object.entries(inputs).sort(([, a], [, b]) =>
    a.axis === b.axis ? b.weight - a.weight : a.axis === 'scale' ? -1 : 1);

  return (
    <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
      <div className="text-sm font-medium text-slate-800 dark:text-gray-100">Market Horizon controls</div>
      <p className="text-xs text-slate-500 mt-0.5 dark:text-gray-400">
        Per-input multipliers for this vendor (1 = the market weight; 0 ignores the input; 2
        doubles it), status, and an analyst note. Applied on the next compute and shown beside
        the vendor on the horizon.
      </p>
      {error && <div className="text-xs text-red-600 dark:text-red-400 mt-2">{error}</div>}
      {!form ? (
        <div className="py-6 text-center text-slate-400"><Loader2 className="w-4 h-4 animate-spin mx-auto" /></div>
      ) : (
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-slate-600 dark:text-gray-300">
              Status
              <select value={form.status}
                      onChange={e => setForm({ ...form, status: e.target.value as HorizonControls['status'] })}
                      className="block mt-0.5 text-sm px-2 py-1 rounded border bg-white dark:bg-gray-900 dark:border-gray-600 dark:text-gray-100">
                <option value="active">active</option>
                <option value="acquired">acquired</option>
                <option value="closed">closed</option>
              </select>
            </label>
            {form.status !== 'active' && (
              <>
                <label className="text-xs text-slate-600 dark:text-gray-300">
                  {form.status === 'acquired' ? 'Acquired by' : 'Detail'}
                  <input value={form.acquired_by ?? ''} maxLength={200}
                         onChange={e => setForm({ ...form, acquired_by: e.target.value })}
                         placeholder={form.status === 'acquired' ? 'Cribl (AI technology assets)' : ''}
                         className="block mt-0.5 text-sm px-2 py-1 rounded border w-64 bg-white dark:bg-gray-900 dark:border-gray-600 dark:text-gray-100" />
                </label>
                <label className="text-xs text-slate-600 dark:text-gray-300">
                  Date
                  <input type="date" value={form.status_date ?? ''}
                         onChange={e => setForm({ ...form, status_date: e.target.value || null })}
                         className="block mt-0.5 text-sm px-2 py-1 rounded border bg-white dark:bg-gray-900 dark:border-gray-600 dark:text-gray-100" />
                </label>
              </>
            )}
          </div>

          <div>
            <div className="text-xs text-slate-600 dark:text-gray-300 mb-1">Input weights for this vendor</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1">
              {ordered.map(([key, i]) => {
                const m = form.multipliers[key] ?? 1;
                return (
                  <label key={key} className="flex items-center gap-2 text-xs text-slate-700 dark:text-gray-200">
                    <input type="number" min={0} max={2} step={0.25} value={m}
                           onChange={e => {
                             const v = Math.max(0, Math.min(2, Number(e.target.value)));
                             const next = { ...form.multipliers };
                             if (v === 1) delete next[key]; else next[key] = v;
                             setForm({ ...form, multipliers: next });
                           }}
                           className={`w-16 text-sm px-1.5 py-0.5 rounded border bg-white dark:bg-gray-900 dark:border-gray-600 dark:text-gray-100 ${m !== 1 ? 'border-amber-400' : ''}`} />
                    <span className="truncate" title={i.label}>{i.label}</span>
                    <span className="text-slate-400 shrink-0">{i.axis} · {i.weight.toFixed(2)}</span>
                  </label>
                );
              })}
            </div>
          </div>

          <label className="block text-xs text-slate-600 dark:text-gray-300">
            Analyst note
            <textarea value={form.note ?? ''} rows={3} maxLength={4000}
                      onChange={e => setForm({ ...form, note: e.target.value })}
                      placeholder="Why this vendor is weighted or marked as it is. Shown in the full report, not the shared one."
                      className="block mt-0.5 w-full text-sm px-2 py-1 rounded border bg-white dark:bg-gray-900 dark:border-gray-600 dark:text-gray-100" />
          </label>

          <div className="flex items-center gap-3">
            <button onClick={save} disabled={saving}
                    className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border bg-white hover:bg-slate-50 disabled:opacity-50 dark:bg-gray-800 dark:hover:bg-gray-700 dark:border-gray-600 dark:text-gray-200">
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              Save
            </button>
            {msg && <span className="text-xs text-emerald-700 dark:text-emerald-400">{msg}</span>}
            {form.updated_at && (
              <span className="text-xs text-slate-400">
                last saved {form.updated_at.slice(0, 16).replace('T', ' ')}{form.updated_by ? ` by ${form.updated_by}` : ''}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
