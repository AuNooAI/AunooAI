/**
 * The case file: everything about one incident, organized top-to-bottom as
 * the analyst's workflow —
 *
 *   header (identity + lifecycle + actions)
 *   → needs your review (agent recommendations, candidates, 💡 suggestions)
 *   → evidence locker (the tamper-evident record; human-only writes)
 *   → agent work (brief, run state, disposition history — output, not record)
 *   → activity (timeline + notes)
 *
 * Agent material is framed violet throughout; the locker is framed neutral
 * with a lock. That contrast is the point: agent output informs, humans commit.
 */
import { useState } from 'react';
import {
  ArrowLeft, Check, ChevronDown, ChevronRight, FileDown, FileUp, Link2,
  Loader2, Lock, Search, ShieldCheck, Sparkles, UserCircle, X,
} from 'lucide-react';
import { incidentFileUrl, updateIncident } from '../../../services/brandWatcherApi';
import { downloadIncidentReport } from '../../../services/incidentReportService';
import { IncidentCase } from './useIncidentCase';
import { StatusStepper } from './StatusStepper';

const SEV_SELECT_CLS: Record<string, string> = {
  low: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
  medium: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  high: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  critical: 'bg-red-600 text-white',
};

const hostOf = (url?: string | null) => {
  try { return url ? new URL(url).hostname.replace(/^www\./, '') : ''; } catch { return ''; }
};

const AGENT_KINDS = new Set(['agent_brief', 'enrichment', 'agent_suggestion']);

function suggDismissKey(incidentId: number, at?: string | null) {
  return `bw_inc_sugg_dismissed:${incidentId}:${at || ''}`;
}

export function IncidentCaseFile(props: {
  c: IncidentCase;
  renderSignalsChips: (article: any) => React.ReactNode;
  showBack: boolean;
}) {
  const { c, renderSignalsChips, showBack } = props;
  const inc = c.detail!;
  const [evOpen, setEvOpen] = useState<Set<number>>(new Set());
  const [othersOpen, setOthersOpen] = useState(false);
  const [histOpen, setHistOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [suggHidden, setSuggHidden] = useState(0); // bump to re-render after local dismiss

  const setField = (updates: Record<string, string>) =>
    updateIncident(inc.id, updates).then(c.refreshIncident).catch(console.error);

  const recommended = (c.enrich?.candidates || []).filter(x => x.recommendation === 'attach');
  const others = (c.enrich?.candidates || []).filter(x => x.recommendation !== 'attach');
  const suggestions = (inc.timeline || [])
    .filter(ev => ev.kind === 'agent_suggestion' && ev.note)
    .filter(ev => { void suggHidden; try { return !localStorage.getItem(suggDismissKey(inc.id, ev.at)); } catch { return true; } });
  const hasReview = recommended.length > 0 || others.length > 0 || suggestions.length > 0;
  const running = c.enrich?.run?.status === 'running';

  const candidateRow = (cand: any, withCheckbox: boolean) => {
    const tcls: Record<string, string> = {
      article: 'bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400',
      social_post: 'bg-purple-50 text-purple-600 dark:bg-purple-900/20 dark:text-purple-400',
      account_profile: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400',
    };
    return (
      <label key={cand.id} className="flex items-start gap-2 p-2 rounded-md border border-gray-100 dark:border-gray-700 hover:border-blue-200 cursor-pointer bg-white dark:bg-gray-800">
        {withCheckbox && (
          <input type="checkbox" checked={c.enrichSel.has(cand.id)}
            onChange={e => c.setEnrichSel(prev => {
              const next = new Set(prev);
              if (e.target.checked) next.add(cand.id); else next.delete(cand.id);
              return next;
            })} className="mt-0.5 flex-shrink-0" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold flex-shrink-0 ${tcls[cand.candidate_type]}`}>{cand.candidate_type.replace('_', ' ')}</span>
            <span className="text-xs text-gray-800 dark:text-gray-100 truncate">{cand.title || cand.source_ref}</span>
            {cand.score != null && <span className="text-[10px] text-gray-400 flex-shrink-0">{cand.score}</span>}
          </div>
          <p className="text-xs text-gray-400 truncate mt-0.5">
            {cand.triage_rationale || cand.reason}{cand.snippet ? ` — ${cand.snippet}` : ''}
          </p>
        </div>
      </label>
    );
  };

  return (
    <div className="space-y-4 min-w-0">
      {c.chain && !c.chain.intact && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-300 dark:border-red-800 text-sm text-red-700 dark:text-red-300 font-medium">
          ✗ EVIDENCE CHAIN BROKEN at item(s) {c.chain.broken_ids.join(', ')} — the locker has been altered. Treat this case's evidence as compromised until investigated.
        </div>
      )}

      {/* ── Case header ─────────────────────────────────────────────── */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-3">
        <div className="flex items-start gap-3">
          {showBack && (
            <button onClick={c.closeIncident} className="mt-1 text-gray-400 hover:text-gray-600 lg:hidden" title="Back to all incidents">
              <ArrowLeft className="w-5 h-5" />
            </button>
          )}
          <div className="flex-1 min-w-0">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">#{inc.id} {inc.title}</h3>
            <p className="text-xs text-gray-400 mt-0.5">
              {inc.brand_name} · opened {(inc.created_at || '').slice(0, 10)} by {inc.created_by}
              {inc.resolved_at ? ` · resolved ${inc.resolved_at.slice(0, 10)}` : ''}
            </p>
            {inc.description && <p className="text-sm text-gray-600 dark:text-gray-300 mt-1.5">{inc.description}</p>}
          </div>
        </div>
        <StatusStepper status={inc.status} onChange={st => setField({ status: st })} />
        <div className="flex items-center gap-2 flex-wrap pt-1">
          <select value={inc.severity} onChange={e => setField({ severity: e.target.value })}
            title="Severity"
            className={`text-xs font-semibold px-2 py-1 rounded-md border-0 cursor-pointer ${SEV_SELECT_CLS[inc.severity] || SEV_SELECT_CLS.medium}`}>
            {['low', 'medium', 'high', 'critical'].map(sv => <option key={sv} value={sv}>{sv}</option>)}
          </select>
          <input type="text" defaultValue={inc.owner || ''} placeholder="owner…" key={`owner-${inc.id}`}
            onBlur={e => { if (e.target.value !== (inc.owner || '')) setField({ owner: e.target.value }); }}
            className="w-28 text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200" />
          <span className="flex-1" />
          <button onClick={c.startEnrich} disabled={running}
            title="The agent searches for related articles, social posts and author profiles, screens attached articles, and stages everything below for your review — nothing enters the locker without your confirmation"
            className="text-xs px-3 py-1.5 rounded-md border border-violet-300 dark:border-violet-700 text-violet-600 dark:text-violet-400 hover:bg-violet-50 dark:hover:bg-violet-900/20 disabled:opacity-50 inline-flex items-center gap-1.5 font-medium">
            {running ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            {running ? 'Enriching…' : 'Enrich'}
          </button>
          <span className="inline-flex items-center rounded-md border border-gray-300 dark:border-gray-600 overflow-hidden"
            title="Download this case as a report — evidence, Five Signals screens, agent brief, timeline and disposition history included">
            <span className="px-1.5 text-gray-400 inline-flex items-center"><FileDown className="w-3.5 h-3.5" /></span>
            {(['html', 'pdf', 'md'] as const).map(fmt => (
              <button key={fmt}
                onClick={() => { try { downloadIncidentReport({ incident: inc, enrichment: c.enrich }, fmt); } catch (e) { console.error(e); alert('Report export failed: ' + e); } }}
                className="text-xs px-2 py-1 uppercase text-gray-500 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 border-l border-gray-200 dark:border-gray-700">
                {fmt}
              </button>
            ))}
          </span>
        </div>
        {running && <p className="text-xs text-violet-600 dark:text-violet-400">✨ {c.enrich?.run?.stage || 'working…'}</p>}
      </div>

      {/* ── Needs your review ───────────────────────────────────────── */}
      {hasReview && (
        <div className="rounded-lg border border-emerald-300 dark:border-emerald-800 bg-emerald-50/40 dark:bg-emerald-900/10 p-4 space-y-3">
          <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-100 inline-flex items-center gap-1.5">
            ★ Needs your review
            <span className="text-xs font-normal text-gray-500">— the agent proposes, you decide; only your decisions touch the locker</span>
          </h4>

          {suggestions.map((ev, i) => (
            <div key={`sugg-${i}`} className="flex items-start gap-2 p-2.5 rounded-md bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
              <span className="flex-shrink-0">💡</span>
              <span className="text-xs text-amber-800 dark:text-amber-200 flex-1">{ev.note}</span>
              <button onClick={() => { try { localStorage.setItem(suggDismissKey(inc.id, ev.at), '1'); } catch { /* ignore */ } setSuggHidden(n => n + 1); }}
                title="Hide this suggestion (it stays in the timeline)"
                className="text-amber-500 hover:text-amber-700 flex-shrink-0"><X className="w-3.5 h-3.5" /></button>
            </div>
          ))}

          {recommended.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-emerald-700 dark:text-emerald-300">
                  Agent recommends attaching {recommended.length} item{recommended.length > 1 ? 's' : ''} (triage score ≥ 0.7)
                </span>
                <span className="flex-1" />
                <button disabled={c.enrichBusy} onClick={c.attachRecommended}
                  title="Attach every recommended item to the evidence locker — this is your commit, recorded under your name"
                  className="text-xs px-2.5 py-1 rounded-md bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40 inline-flex items-center gap-1 font-medium">
                  <Check className="w-3.5 h-3.5" /> Attach all {recommended.length}
                </button>
              </div>
              <div className="space-y-1 max-h-56 overflow-y-auto">
                {recommended.map(cand => candidateRow(cand, true))}
              </div>
            </div>
          )}

          {others.length > 0 && (
            <div>
              <button onClick={() => setOthersOpen(o => !o)}
                className="text-xs font-medium text-gray-600 dark:text-gray-300 inline-flex items-center gap-1">
                {othersOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                {others.length} more candidate{others.length > 1 ? 's' : ''} for review
              </button>
              {othersOpen && (
                <div className="space-y-1 max-h-72 overflow-y-auto mt-1.5">
                  {others.map(cand => candidateRow(cand, true))}
                </div>
              )}
            </div>
          )}

          {(recommended.length > 0 || others.length > 0) && (
            <div className="flex items-center gap-2 pt-1">
              <span className="text-xs text-gray-400">{c.enrichSel.size ? `${c.enrichSel.size} selected:` : 'Select items above, then:'}</span>
              <button disabled={!c.enrichSel.size || c.enrichBusy} onClick={() => c.decideEnrichSel('attach')}
                className="text-xs px-2.5 py-1 rounded-md border border-emerald-300 dark:border-emerald-700 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 disabled:opacity-40">Attach</button>
              <button disabled={!c.enrichSel.size || c.enrichBusy} onClick={() => c.decideEnrichSel('dismiss')}
                title="Dismissed items are never re-proposed by the agent"
                className="text-xs px-2.5 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-500 hover:text-gray-700 disabled:opacity-40">Dismiss</button>
            </div>
          )}
        </div>
      )}

      {/* ── Evidence locker ─────────────────────────────────────────── */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-100 inline-flex items-center gap-1.5">
            <Lock className="w-4 h-4" /> Evidence locker
            <span className="text-xs font-normal text-gray-400">({(inc.evidence || []).length}) · append-only, hash-chained</span>
          </h4>
          <span className="flex-1" />
          <button onClick={c.runVerifyChain}
            title="Recompute every entry's hash chain to prove nothing was altered or removed"
            className="text-xs px-2.5 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-500 hover:text-gray-700 inline-flex items-center gap-1">
            <ShieldCheck className="w-3.5 h-3.5" /> Verify chain
          </button>
          <div className="relative">
            <button onClick={() => setAddOpen(o => !o)}
              className="text-xs px-2.5 py-1 rounded-md bg-blue-600 text-white hover:bg-blue-700 inline-flex items-center gap-1 font-medium">
              Add evidence <ChevronDown className="w-3.5 h-3.5" />
            </button>
            {addOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setAddOpen(false)} />
                <div className="absolute right-0 top-full mt-1 z-20 w-56 rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg py-1">
                  <button onClick={() => { setAddOpen(false); c.setSearch(s => ({ ...s, open: true })); }}
                    className="w-full text-left px-3 py-1.5 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 inline-flex items-center gap-2">
                    <Search className="w-3.5 h-3.5 text-gray-400" /> Search articles / posts…
                  </button>
                  <button onClick={() => { setAddOpen(false); c.openProfilePicker(); }}
                    className="w-full text-left px-3 py-1.5 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 inline-flex items-center gap-2">
                    <UserCircle className="w-3.5 h-3.5 text-gray-400" /> Account profile…
                  </button>
                  <button onClick={() => { setAddOpen(false); c.fileInputRef.current?.click(); }} disabled={c.fileBusy}
                    className="w-full text-left px-3 py-1.5 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 inline-flex items-center gap-2 disabled:opacity-50">
                    <FileUp className="w-3.5 h-3.5 text-gray-400" /> Upload file… <span className="text-[10px] text-gray-400">max 25 MB</span>
                  </button>
                  <div className="px-3 py-1.5 border-t border-gray-100 dark:border-gray-700 mt-1">
                    <div className="flex items-center gap-1.5">
                      <Link2 className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                      <input type="text" value={c.evidenceUrl} onChange={e => c.setEvidenceUrl(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter' && c.evidenceUrl.trim()) { c.captureUrl(); setAddOpen(false); } }}
                        placeholder="Paste a URL, Enter to capture"
                        className="flex-1 text-xs px-1.5 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200" />
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
          <input ref={c.fileInputRef} type="file" className="hidden" onChange={e => c.onFilePicked(e.target.files?.[0])} />
        </div>

        {c.chain?.intact && (
          <p className="text-xs px-2 py-1 rounded bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400">
            ✓ Chain intact — {c.chain.items} item(s) verified.
          </p>
        )}

        {(inc.evidence || []).length === 0 && (
          <p className="text-xs text-gray-400">No evidence yet. Use “Add evidence” above, or attach from any article / post / profile row elsewhere via act… → Add to incident.</p>
        )}
        <div className="space-y-1.5">
          {(inc.evidence || []).map(ev => {
            const m = ev.meta || {};
            const typeCls: Record<string, string> = {
              article: 'bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400',
              social_post: 'bg-purple-50 text-purple-600 dark:bg-purple-900/20 dark:text-purple-400',
              account_profile: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400',
              file: 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400',
              alert_event: 'bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400',
            };
            const open = evOpen.has(ev.id);
            return (
              <div key={ev.id} className="rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-750">
                <div className="flex items-center gap-2 p-2.5">
                  {ev.evidence_type === 'account_profile' && m.profile?.avatar_url
                    ? <img src={m.profile.avatar_url} alt="" className="w-6 h-6 rounded-full flex-shrink-0 object-cover" /> : null}
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold flex-shrink-0 ${typeCls[ev.evidence_type] || typeCls.article}`}>{ev.evidence_type.replace('_', ' ')}</span>
                  <span className="text-sm font-medium truncate flex-1">
                    {ev.source_ref && String(ev.source_ref).startsWith('http') ? (
                      <a href={ev.source_ref} target="_blank" rel="noopener noreferrer" title={ev.source_ref}
                        onClick={e => e.stopPropagation()}
                        className="text-gray-800 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400 hover:underline">
                        {ev.title || ev.source_ref}
                        <span className="text-xs font-normal text-gray-400 ml-1.5">{hostOf(ev.source_ref)}</span>
                      </a>
                    ) : (
                      <span className="text-gray-800 dark:text-gray-100">{ev.title || ev.source_ref || '(untitled)'}</span>
                    )}
                  </span>
                  {ev.evidence_type === 'article' && ev.source_ref && String(ev.source_ref).startsWith('http') && (
                    <span className="flex-shrink-0" onClick={e => e.stopPropagation()}>
                      {renderSignalsChips({ uri: ev.source_ref, brand_id: inc.brand_id, title: ev.title, signals_summary: ev.signals_summary })}
                    </span>
                  )}
                  <button onClick={() => setEvOpen(prev => { const n = new Set(prev); if (open) n.delete(ev.id); else n.add(ev.id); return n; })}
                    className="text-gray-400 hover:text-gray-600 flex-shrink-0" title={open ? 'Collapse' : 'Details'}>
                    {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  </button>
                </div>
                {open && (
                  <div className="px-2.5 pb-2.5 space-y-1.5 border-t border-gray-100 dark:border-gray-700 pt-2">
                    {ev.evidence_type === 'social_post' && (m.platform || m.author) && (
                      <p className="text-xs text-purple-600 dark:text-purple-400">
                        {m.platform}{m.author ? ` · @${m.author}` : ''}
                        {m.engagement && Object.keys(m.engagement).length > 0 && (
                          <span className="text-gray-400"> · {Object.entries(m.engagement).map(([k, v]) => `${v} ${k}`).join(' · ')}</span>
                        )}
                      </p>
                    )}
                    {ev.evidence_type === 'account_profile' && (
                      <p className="text-xs text-emerald-600 dark:text-emerald-400">
                        {m.profile?.display_name || `@${m.handle}`} · {m.platform}
                        {m.profile?.followers_count != null && <span className="text-gray-400"> · {Number(m.profile.followers_count).toLocaleString()} followers</span>}
                      </p>
                    )}
                    {ev.evidence_type === 'file' && m.file_id && (
                      <p className="text-xs">
                        <a href={incidentFileUrl(inc.id, m.file_id)} download
                          className="text-amber-700 dark:text-amber-400 hover:underline inline-flex items-center gap-1">
                          <FileDown className="w-3.5 h-3.5" /> {m.filename}
                        </a>
                        <span className="text-gray-400"> · {m.size_bytes != null ? `${(m.size_bytes / 1024).toFixed(0)} KB` : ''} · {m.mime}</span>
                      </p>
                    )}
                    {ev.content && <p className="text-xs text-gray-500 dark:text-gray-400 whitespace-pre-line max-h-40 overflow-y-auto">{ev.content}</p>}
                    <p className="text-[10px] font-mono text-gray-400 truncate"
                      title={`content sha256: ${ev.content_sha256} · chain: ${ev.chain_sha256}`}>
                      captured {(ev.captured_at || '').slice(0, 16).replace('T', ' ')} by {ev.captured_by} · sha256 {ev.content_sha256.slice(0, 20)}… · chain {ev.chain_sha256.slice(0, 20)}…
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Agent work ──────────────────────────────────────────────── */}
      <div className="rounded-lg border border-violet-200 dark:border-violet-900 bg-violet-50/30 dark:bg-violet-900/10 p-4 space-y-2.5">
        <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-100 inline-flex items-center gap-1.5">
          <Sparkles className="w-4 h-4 text-violet-500" /> Agent work
          <span className="text-xs font-normal text-gray-400">— research output; informs the case, never writes the locker</span>
        </h4>
        {c.enrich?.run?.status === 'failed' && (
          <p className="text-xs text-red-600 dark:text-red-400">Last run failed: {c.enrich.run.error}
            <button onClick={c.startEnrich} className="ml-2 underline hover:text-red-700">Retry</button></p>
        )}
        {c.enrich?.run?.brief ? (
          <div className="rounded-md border border-violet-200 dark:border-violet-800 bg-white dark:bg-gray-800">
            <div className="flex items-center justify-between px-3 py-2">
              <button onClick={() => c.setBriefOpen(o => !o)} className="text-xs font-medium text-gray-700 dark:text-gray-200 inline-flex items-center gap-1">
                {c.briefOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                Agent brief <span className="text-gray-400 font-normal">{c.enrich.run.finished_at ? c.enrich.run.finished_at.slice(0, 16).replace('T', ' ') : ''}</span>
              </button>
              <button onClick={c.attachBrief}
                title="Snapshot this brief into the evidence locker as a note — a human commit, recorded under your name"
                className="text-xs px-2 py-0.5 rounded border border-gray-300 dark:border-gray-600 text-gray-500 hover:text-gray-700">Attach to locker</button>
            </div>
            {c.briefOpen && (
              <div className="px-3 pb-2.5 text-xs text-gray-600 dark:text-gray-300 whitespace-pre-line max-h-72 overflow-y-auto">{c.enrich.run.brief}</div>
            )}
          </div>
        ) : (!c.enrich?.run && <p className="text-xs text-gray-400">No agent runs yet — hit Enrich above.</p>)}
        {((c.enrich?.counts?.attached || 0) + (c.enrich?.counts?.dismissed || 0) > 0 || (c.enrich?.history?.length || 0) > 0) && (
          <div>
            <button onClick={() => setHistOpen(o => !o)}
              className="text-xs font-medium text-gray-600 dark:text-gray-300 inline-flex items-center gap-1">
              {histOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              Disposition history — {c.enrich?.counts?.attached || 0} attached · {c.enrich?.counts?.dismissed || 0} dismissed
            </button>
            {histOpen && (
              <div className="space-y-1 mt-1.5 max-h-56 overflow-y-auto">
                {(c.enrich?.history || []).map(h => (
                  <div key={h.id} className="flex items-center gap-2 text-xs px-2 py-1 rounded bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold flex-shrink-0 ${h.state === 'attached' ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400' : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'}`}>{h.state}</span>
                    <span className="text-gray-700 dark:text-gray-200 truncate flex-1">{h.title || h.source_ref}</span>
                    <span className="text-gray-400 flex-shrink-0">{h.decided_by} · {(h.decided_at || '').slice(5, 16).replace('T', ' ')}</span>
                  </div>
                ))}
                {!(c.enrich?.history || []).length && <p className="text-xs text-gray-400">Decisions will appear here.</p>}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Activity ────────────────────────────────────────────────── */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-2">Activity</h4>
        <div className="space-y-1 max-h-72 overflow-y-auto">
          {(inc.timeline || []).map((ev, i) => {
            const agent = AGENT_KINDS.has(ev.kind) || String(ev.actor || '').startsWith('agent');
            return (
              <div key={i} className={`flex items-start gap-2 text-xs py-0.5 ${agent ? 'text-violet-700 dark:text-violet-300' : ''}`}>
                <span className="text-gray-400 flex-shrink-0 w-24 font-mono">{(ev.at || '').slice(5, 16).replace('T', ' ')}</span>
                {agent ? <Sparkles className="w-3.5 h-3.5 mt-0.5 text-violet-400 flex-shrink-0" />
                       : <span className="text-gray-500 dark:text-gray-400 flex-shrink-0 max-w-[90px] truncate">{ev.actor}</span>}
                <span className={agent ? '' : 'text-gray-700 dark:text-gray-200'}>
                  {ev.kind === 'note' ? ev.note
                    : ev.kind === 'evidence_added' ? `captured ${ev.new_value} evidence: ${ev.note}`
                    : ev.kind === 'created' ? `opened the incident (${ev.new_value})`
                    : ev.kind === 'agent_brief' ? `wrote an incident brief: ${ev.note || ''}`
                    : ev.kind === 'enrichment' ? (ev.note || 'enrichment run finished')
                    : ev.kind === 'agent_suggestion' ? `💡 ${ev.note || 'agent suggestion'}`
                    : `${ev.kind.replace('_', ' ')}: ${ev.old_value ?? '—'} → ${ev.new_value}${ev.note ? ` (${ev.note})` : ''}`}
                </span>
              </div>
            );
          })}
        </div>
        <div className="flex items-center gap-2 mt-2.5">
          <input type="text" value={c.noteText} onChange={e => c.setNoteText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') c.saveNote(); }}
            placeholder="Add a note…"
            className="flex-1 text-xs px-2.5 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200" />
          <button onClick={c.saveNote} disabled={!c.noteText.trim()}
            className="text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 disabled:opacity-40">Add note</button>
        </div>
      </div>
    </div>
  );
}
