/**
 * The case view, organized around the brand-protection questions:
 *
 *   WHAT is happening        — situation summary + AI assessment
 *   HOW BIG is it            — spread, platforms, reach, credibility check
 *   WHAT'S OUT THERE         — all coverage (in the case + AI-found), one
 *                              Accept button folds the AI findings in
 *   WHO is involved          — accounts posting about it
 *   HOW it unfolded          — chronology of the content + case milestones
 *   CASE RECORD (collapsed)  — audit trail, hashes, chain verification, notes
 *
 * All datapoints are synthesized client-side from the incident payload by
 * caseSynthesis.ts. AI-found items carry a violet dot; accepting them into
 * the case is one click (noise was already filtered by the triage agent).
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  ArrowLeft, Check, ChevronDown, ChevronRight, FileDown, FileUp, Link2,
  Loader2, Search, ShieldCheck, Sparkles, UserCircle, X,
} from 'lucide-react';
import { BWIncident, incidentFileUrl, translateForReport, updateIncident } from '../../../services/brandWatcherApi';
import { downloadIncidentReport } from '../../../services/incidentReportService';
import { IncidentCase } from './useIncidentCase';
import {
  CoverageItem, RISKY_VERDICTS, VERDICT_LABEL, cleanText, hostOf, needsTranslation, synthesizeCase,
} from './caseSynthesis';

const SEV_SELECT_CLS: Record<string, string> = {
  low: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
  medium: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  high: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  critical: 'bg-red-600 text-white',
};
const STATUS_SELECT_CLS: Record<string, string> = {
  open: 'bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400',
  investigating: 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300',
  contained: 'bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400',
  resolved: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300',
  closed: 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400',
};

function suggDismissKey(incidentId: number, at?: string | null) {
  return `bw_inc_sugg_dismissed:${incidentId}:${at || ''}`;
}

const SEV_ORDER = ['low', 'medium', 'high', 'critical'];
const lowerSeverity = (sev: string) => SEV_ORDER[Math.max(0, SEV_ORDER.indexOf(sev) - 1)] || 'low';

/** Structured read of an agent_suggestion note (prefixes are stable backend contract). */
function parseSuggestion(note: string): { type: 'severity' } | { type: 'duplicate'; otherId: number; otherTitle: string } | { type: 'other' } {
  if (note.startsWith('severity review:')) return { type: 'severity' };
  const m = /^possible duplicate of incident #(\d+) \('([^']*)'\)/.exec(note);
  if (m) return { type: 'duplicate', otherId: Number(m[1]), otherTitle: m[2] };
  return { type: 'other' };
}

const nf = (n: number) => n >= 10000 ? `${Math.round(n / 1000)}k` : n.toLocaleString();

// Display label (caseSynthesis) → collector platform key, for profile builds.
const PLATFORM_KEY: Record<string, string> = {
  Bluesky: 'bluesky', X: 'x', Reddit: 'reddit', TikTok: 'tiktok', Instagram: 'instagram',
};

export function IncidentCaseFile(props: {
  c: IncidentCase;
  renderSignalsChips: (article: any) => React.ReactNode;
  showBack: boolean;
  incidents: BWIncident[];
}) {
  const { c, renderSignalsChips, showBack, incidents } = props;
  const inc = c.detail!;
  const [platFilter, setPlatFilter] = useState('');
  const [briefFull, setBriefFull] = useState(false);
  const [recordOpen, setRecordOpen] = useState(false);
  const [openItems, setOpenItems] = useState<Set<string>>(new Set());
  const [suggHidden, setSuggHidden] = useState(0);

  const syn = useMemo(() => synthesizeCase(inc, c.enrich), [inc, c.enrich]);
  const running = c.enrich?.run?.status === 'running';

  const setField = (updates: Record<string, string>) =>
    updateIncident(inc.id, updates).then(c.refreshIncident).catch(console.error);

  const suggestions = (inc.timeline || [])
    .filter(ev => ev.kind === 'agent_suggestion' && ev.note)
    .filter(ev => { void suggHidden; try { return !localStorage.getItem(suggDismissKey(inc.id, ev.at)); } catch { return true; } })
    // Retire cards that have been overtaken by events: a duplicate pointing at
    // a merged/closed/deleted case, or a severity nudge after severity dropped.
    .filter(ev => {
      const s = parseSuggestion(ev.note || '');
      if (s.type === 'duplicate') {
        const other = incidents.find(i => i.id === s.otherId);
        if (!other || ['closed', 'resolved'].includes(other.status)) return false;
      }
      if (s.type === 'severity' && !['high', 'critical'].includes(inc.severity)) return false;
      return true;
    });

  // English display titles/bodies for foreign-language coverage — same
  // translation pass the report uses, fetched once per item and cached.
  const [translations, setTranslations] = useState<Record<string, string>>({});
  const translationRequested = useRef<Set<string>>(new Set());
  useEffect(() => {
    const items: { id: string; text: string }[] = [];
    for (const it of syn.coverage) {
      if (translationRequested.current.has(it.key)) continue;
      if (needsTranslation(it.title)) items.push({ id: `${it.key}|t`, text: it.title });
      if (it.body && needsTranslation(it.body)) items.push({ id: `${it.key}|b`, text: it.body.slice(0, 800) });
      translationRequested.current.add(it.key);
    }
    if (!items.length) return;
    translateForReport(items)
      .then(map => setTranslations(prev => {
        const next = { ...prev };
        for (const it of items) { if (map[it.id]?.text) next[it.id] = map[it.id].text; }
        return next;
      }))
      .catch(() => { /* originals stay */ });
  }, [syn.coverage]);

  const brief = cleanText(c.enrich?.run?.brief || '');
  const coverageShown = platFilter ? syn.coverage.filter(it => it.platform === platFilter) : syn.coverage;

  const coverageRow = (it: CoverageItem) => {
    const open = openItems.has(it.key);
    const tTitle = translations[`${it.key}|t`];
    const tBody = translations[`${it.key}|b`];
    const shownTitle = tTitle || it.title;
    return (
      <div key={it.key} className={`rounded-md border ${it.inCase
        ? 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800'
        : 'border-violet-200 dark:border-violet-800 bg-violet-50/30 dark:bg-violet-900/10'}`}>
        <div className="flex items-center gap-2 px-2.5 py-2">
          {!it.inCase && <span className="w-1.5 h-1.5 rounded-full bg-violet-400 flex-shrink-0" title="Found by AI — not yet part of the case" />}
          <span className="text-sm truncate flex-1 min-w-0">
            {it.url && String(it.url).startsWith('http') ? (
              <a href={it.url} target="_blank" rel="noopener noreferrer" title={tTitle ? `${it.title}\n${it.url}` : it.url}
                className="text-gray-800 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400 hover:underline">
                {shownTitle}
                {tTitle && <span className="text-[10px] font-semibold text-blue-400 ml-1" title={`Translated — original: ${it.title}`}>EN</span>}
                {it.type === 'article' && <span className="text-xs font-normal text-gray-400 ml-1.5">{hostOf(it.url)}</span>}
              </a>
            ) : <span className="text-gray-800 dark:text-gray-100" title={tTitle ? `Original: ${it.title}` : undefined}>
                {shownTitle}{tTitle && <span className="text-[10px] font-semibold text-blue-400 ml-1">EN</span>}
              </span>}
          </span>
          {it.signals && (
            <span className="flex-shrink-0" onClick={e => e.stopPropagation()}>
              {renderSignalsChips({ uri: it.url, brand_id: inc.brand_id, title: it.title, signals_summary: it.signals })}
            </span>
          )}
          {it.engagementLine && <span className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0">{it.engagementLine}</span>}
          {it.date && <span className="text-xs text-gray-400 flex-shrink-0">{it.date}</span>}
          {!it.inCase && it.candidateId != null && (
            <span className="flex items-center gap-1 flex-shrink-0">
              <button disabled={c.enrichBusy} onClick={() => c.decideOne(it.candidateId!, 'attach')}
                title="Add to the case" className="p-1 rounded text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 disabled:opacity-40">
                <Check className="w-4 h-4" /></button>
              <button disabled={c.enrichBusy} onClick={() => c.decideOne(it.candidateId!, 'dismiss')}
                title="Not relevant — never propose again" className="p-1 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-40">
                <X className="w-4 h-4" /></button>
            </span>
          )}
          {(it.body || it.aiReason) && (
            <button onClick={() => setOpenItems(prev => { const n = new Set(prev); if (open) n.delete(it.key); else n.add(it.key); return n; })}
              className="text-gray-400 hover:text-gray-600 flex-shrink-0">
              {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </button>
          )}
        </div>
        {open && (
          <div className="px-2.5 pb-2 space-y-1 border-t border-gray-100 dark:border-gray-700 pt-1.5">
            {tBody && <p className="text-xs text-gray-600 dark:text-gray-300 whitespace-pre-line max-h-32 overflow-y-auto"><span className="text-[10px] font-semibold text-blue-400 mr-1">EN</span>{tBody}</p>}
            {it.body && <p className={`text-xs whitespace-pre-line max-h-32 overflow-y-auto ${tBody ? 'text-gray-400 dark:text-gray-500' : 'text-gray-500 dark:text-gray-400'}`}>{it.body}</p>}
            {it.aiReason && <p className="text-xs text-violet-500 dark:text-violet-400">AI: {it.aiReason}</p>}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4 min-w-0">
      {c.chain && !c.chain.intact && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-300 dark:border-red-800 text-sm text-red-700 dark:text-red-300 font-medium">
          ✗ EVIDENCE CHAIN BROKEN at item(s) {c.chain.broken_ids.join(', ')} — the case record has been altered. Treat its evidence as compromised until investigated.
        </div>
      )}

      {/* ── Header: identity + the actions that matter ─────────────── */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-3">
        <div className="flex items-start gap-3">
          {showBack && (
            <button onClick={c.closeIncident} className="mt-1 text-gray-400 hover:text-gray-600 lg:hidden" title="Back to all incidents">
              <ArrowLeft className="w-5 h-5" />
            </button>
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{inc.title}</h3>
              <select value={inc.severity} onChange={e => setField({ severity: e.target.value })} title="Severity"
                className={`text-xs font-semibold px-2 py-0.5 rounded-full border-0 cursor-pointer ${SEV_SELECT_CLS[inc.severity] || SEV_SELECT_CLS.medium}`}>
                {['low', 'medium', 'high', 'critical'].map(sv => <option key={sv} value={sv}>{sv}</option>)}
              </select>
              <select value={inc.status} onChange={e => setField({ status: e.target.value })} title="Status"
                className={`text-xs font-semibold px-2 py-0.5 rounded-full border-0 cursor-pointer ${STATUS_SELECT_CLS[inc.status] || STATUS_SELECT_CLS.closed}`}>
                {['open', 'investigating', 'contained', 'resolved', 'closed'].map(st => <option key={st} value={st}>{st}</option>)}
              </select>
            </div>
            <p className="text-xs text-gray-400 mt-1">
              {inc.brand_name} · case #{inc.id} · opened {(inc.created_at || '').slice(0, 10)}
              {inc.resolved_at ? ` · resolved ${inc.resolved_at.slice(0, 10)}` : ''}
              {' · owner '}
              <input type="text" defaultValue={inc.owner || ''} placeholder="unassigned" key={`owner-${inc.id}`}
                onBlur={e => { if (e.target.value !== (inc.owner || '')) setField({ owner: e.target.value }); }}
                className="inline-block w-24 text-xs px-1 py-0 rounded border-0 border-b border-dashed border-gray-300 dark:border-gray-600 bg-transparent text-gray-600 dark:text-gray-300" />
            </p>
            {inc.description && <p className="text-sm text-gray-600 dark:text-gray-300 mt-1.5">{cleanText(inc.description)}</p>}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {(() => {
            // must mirror acceptAll's filter — the button count is a promise
            const acceptable = (c.enrich?.candidates || []).filter((x: any) =>
              x.candidate_type !== 'account_profile'
              && (x.recommendation === 'attach' || x.triage_score == null)).length;
            return acceptable > 0 && (
              <button disabled={c.enrichBusy} onClick={c.acceptAll}
                title="Fold the AI findings the triage agent stands behind into the case in one go. Uncertain or low-scored items stay below for a per-item decision."
                className="text-sm px-3 py-1.5 rounded-md bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40 inline-flex items-center gap-1.5 font-medium">
                {c.enrichBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                Accept {acceptable} recommended finding{acceptable > 1 ? 's' : ''}
              </button>
            );
          })()}
          <button onClick={c.startEnrich} disabled={running}
            title="AI sweeps for related coverage, checks who is spreading it, screens articles for credibility and drafts an assessment"
            className="text-sm px-3 py-1.5 rounded-md border border-violet-300 dark:border-violet-700 text-violet-600 dark:text-violet-400 hover:bg-violet-50 dark:hover:bg-violet-900/20 disabled:opacity-50 inline-flex items-center gap-1.5">
            {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            {running ? (c.enrich?.run?.stage || 'Investigating…') : 'Investigate'}
          </button>
          <span className="flex-1" />
          <span className="inline-flex items-center rounded-md border border-gray-300 dark:border-gray-600 overflow-hidden"
            title="Download this case as a report">
            <span className="px-1.5 text-gray-400 inline-flex items-center"><FileDown className="w-3.5 h-3.5" /></span>
            {(['html', 'pdf', 'md'] as const).map(fmt => (
              <button key={fmt}
                onClick={async () => { try { await downloadIncidentReport({ incident: inc, enrichment: c.enrich }, fmt); } catch (e) { console.error(e); alert('Report export failed: ' + e); } }}
                className="text-xs px-2 py-1 uppercase text-gray-500 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 border-l border-gray-200 dark:border-gray-700">
                {fmt}
              </button>
            ))}
          </span>
        </div>
        {suggestions.map((ev, i) => {
          const dismiss = () => { try { localStorage.setItem(suggDismissKey(inc.id, ev.at), '1'); } catch { /* ignore */ } setSuggHidden(n => n + 1); };
          const s = parseSuggestion(ev.note || '');
          return (
            <div key={`sugg-${i}`} className="p-3 rounded-md bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
              {s.type === 'severity' ? (
                <>
                  <p className="text-sm font-medium text-amber-900 dark:text-amber-100">Severity may be overstated</p>
                  <p className="text-xs text-amber-800 dark:text-amber-200 mt-0.5">
                    Every screened item in this case came back low-risk — nothing is independently confirmed or coordinated. Severity is currently ‘{inc.severity}’.
                  </p>
                  <div className="flex items-center gap-2 mt-2">
                    <button onClick={() => { setField({ severity: lowerSeverity(inc.severity) }); dismiss(); }}
                      className="text-xs px-2.5 py-1 rounded-md bg-amber-600 text-white hover:bg-amber-700 font-medium">
                      Lower to {lowerSeverity(inc.severity)}</button>
                    <button onClick={dismiss}
                      className="text-xs px-2.5 py-1 rounded-md border border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-300">
                      Keep {inc.severity}</button>
                  </div>
                </>
              ) : s.type === 'duplicate' ? (
                <>
                  <p className="text-sm font-medium text-amber-900 dark:text-amber-100">Possibly the same incident as case #{s.otherId}</p>
                  <p className="text-xs text-amber-800 dark:text-amber-200 mt-0.5">
                    This case and #{s.otherId} (‘{s.otherTitle}’) contain the same evidence. If they cover one event, work it in a single case and close the other.
                  </p>
                  <div className="flex items-center gap-2 mt-2">
                    <button onClick={() => { dismiss(); c.mergeInto(s.otherId); }}
                      title={`Copy this case's evidence into #${s.otherId} and close this one with a cross-reference`}
                      className="text-xs px-2.5 py-1 rounded-md bg-amber-600 text-white hover:bg-amber-700 font-medium">
                      Merge into #{s.otherId}</button>
                    <button onClick={() => c.openIncident(s.otherId)}
                      className="text-xs px-2.5 py-1 rounded-md border border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-300">
                      View #{s.otherId}</button>
                    <button onClick={dismiss}
                      className="text-xs px-2.5 py-1 rounded-md border border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-300">
                      Not a duplicate</button>
                  </div>
                </>
              ) : (
                <div className="flex items-start gap-2">
                  <span className="text-xs text-amber-800 dark:text-amber-200 flex-1">{ev.note}</span>
                  <button onClick={dismiss} className="text-amber-500 hover:text-amber-700 flex-shrink-0"><X className="w-3.5 h-3.5" /></button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Situation: how big is this ──────────────────────────────── */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-3">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div>
            <p className="text-[10px] uppercase tracking-wide text-gray-400 font-semibold">Coverage</p>
            <p className="text-xl font-bold text-gray-900 dark:text-gray-100">{syn.coverage.length}</p>
            <p className="text-xs text-gray-400">{syn.coverage.filter(i => i.type === 'social_post').length} posts · {syn.coverage.filter(i => i.type === 'article').length} articles</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wide text-gray-400 font-semibold">Platforms</p>
            <p className="text-xl font-bold text-gray-900 dark:text-gray-100">{syn.platforms.length}</p>
            <p className="text-xs text-gray-400 truncate">{syn.platforms.map(p => p.name).join(', ') || '—'}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wide text-gray-400 font-semibold">Engagement</p>
            <p className="text-xl font-bold text-gray-900 dark:text-gray-100">{nf(syn.totalEngagement)}</p>
            <p className="text-xs text-gray-400">likes + reposts + comments</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wide text-gray-400 font-semibold">Credibility check</p>
            {syn.worstVerdict ? (
              <>
                <p className={`text-sm font-bold mt-1 ${RISKY_VERDICTS.has(syn.worstVerdict) ? 'text-red-600 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                  {VERDICT_LABEL[syn.worstVerdict] || syn.worstVerdict}
                </p>
                <p className="text-xs text-gray-400">{syn.verdicts.length} item{syn.verdicts.length > 1 ? 's' : ''} screened</p>
              </>
            ) : (
              <p className="text-xs text-gray-400 mt-1.5">nothing screened yet — Investigate runs it</p>
            )}
          </div>
        </div>
        {brief && (
          <div className="border-t border-gray-100 dark:border-gray-700 pt-3">
            <p className="text-[10px] uppercase tracking-wide text-violet-500 font-semibold mb-1 inline-flex items-center gap-1">
              <Sparkles className="w-3 h-3" /> AI assessment
              <span className="text-gray-400 normal-case font-normal">{c.enrich?.run?.finished_at ? ` · ${c.enrich.run.finished_at.slice(0, 16).replace('T', ' ')}` : ''}</span>
            </p>
            <div className={`text-sm text-gray-700 dark:text-gray-200 ${briefFull ? '' : 'max-h-44 overflow-hidden relative'}`}>
              <ReactMarkdown components={{
                h1: p => <h5 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mt-3 mb-1" {...p} />,
                h2: p => <h5 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mt-3 mb-1" {...p} />,
                h3: p => <h6 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mt-2.5 mb-1" {...p} />,
                h4: p => <h6 className="text-xs font-semibold text-gray-800 dark:text-gray-200 mt-2 mb-0.5" {...p} />,
                p: p => <p className="my-1.5" {...p} />,
                ul: p => <ul className="list-disc pl-5 my-1.5 space-y-0.5" {...p} />,
                ol: p => <ol className="list-decimal pl-5 my-1.5 space-y-0.5" {...p} />,
                strong: p => <strong className="font-semibold text-gray-900 dark:text-gray-100" {...p} />,
                a: p => <a className="text-blue-600 dark:text-blue-400 hover:underline" target="_blank" rel="noopener noreferrer" {...p} />,
              }}>{brief}</ReactMarkdown>
              {!briefFull && <div className="absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-white dark:from-gray-800 to-transparent" />}
            </div>
            <div className="flex items-center gap-3 mt-1.5">
              <button onClick={() => setBriefFull(f => !f)} className="text-xs text-blue-600 dark:text-blue-400 hover:underline">
                {briefFull ? 'Collapse' : 'Read full assessment'}
              </button>
              <button onClick={c.attachBrief} className="text-xs text-gray-400 hover:text-gray-600 hover:underline"
                title="Preserve this assessment in the audit log">Save to record</button>
            </div>
          </div>
        )}
        {!brief && !running && (
          <p className="text-xs text-gray-400 border-t border-gray-100 dark:border-gray-700 pt-3">
            No AI assessment yet — <button onClick={c.startEnrich} className="text-violet-600 dark:text-violet-400 hover:underline">Investigate</button> sweeps for coverage, checks credibility and writes one.
          </p>
        )}
        {c.enrich?.run?.status === 'failed' && (
          <p className="text-xs text-red-500">AI investigation failed: {c.enrich.run.error}
            <button onClick={c.startEnrich} className="ml-2 underline">Retry</button></p>
        )}
      </div>

      {/* ── What's out there ────────────────────────────────────────── */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-2.5">
        <div className="flex items-center gap-2 flex-wrap">
          <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Coverage</h4>
          <span className="text-xs text-gray-400">
            {syn.coverage.filter(i => i.inCase).length} in case
            {syn.agentFound.length ? ` · ${syn.agentFound.length} AI-found awaiting your ✓ / ✕` : ''}
            {syn.reassignedCount ? ` · ${syn.reassignedCount} reassigned to other cases (audit record retained)` : ''}
          </span>
          <span className="flex-1" />
          <div className="relative">
            <AddEvidenceMenu c={c} />
          </div>
        </div>
        {syn.platforms.length > 1 && (
          <div className="flex items-center gap-1 flex-wrap">
            <button onClick={() => setPlatFilter('')}
              className={`text-xs px-2 py-0.5 rounded-full border ${!platFilter ? 'bg-blue-600 text-white border-blue-600' : 'bg-white dark:bg-gray-800 text-gray-500 border-gray-300 dark:border-gray-600'}`}>
              all {syn.coverage.length}</button>
            {syn.platforms.map(p => (
              <button key={p.name} onClick={() => setPlatFilter(f => f === p.name ? '' : p.name)}
                className={`text-xs px-2 py-0.5 rounded-full border ${platFilter === p.name ? 'bg-blue-600 text-white border-blue-600' : 'bg-white dark:bg-gray-800 text-gray-500 border-gray-300 dark:border-gray-600'}`}>
                {p.name} {p.count}</button>
            ))}
          </div>
        )}
        <div className="space-y-1.5 max-h-[28rem] overflow-y-auto">
          {coverageShown.map(coverageRow)}
          {!coverageShown.length && <p className="text-xs text-gray-400 py-3 text-center">Nothing here yet — Investigate finds coverage automatically, or add items manually.</p>}
        </div>
      </div>

      {/* ── Who's involved ──────────────────────────────────────────── */}
      {syn.accounts.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-2.5">Accounts</h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2">
            {syn.accounts.map(a => (
              <div key={a.key} className="flex items-center gap-2.5 p-2 rounded-md border border-gray-100 dark:border-gray-700">
                {a.avatarUrl ? <img src={a.avatarUrl} alt="" className="w-8 h-8 rounded-full object-cover flex-shrink-0" />
                  : <UserCircle className="w-8 h-8 text-gray-300 flex-shrink-0" />}
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-gray-800 dark:text-gray-100 truncate">
                    {a.displayName || `@${a.handle}`} <span className="text-xs text-gray-400">@{a.handle} · {a.platform}</span>
                  </p>
                  <p className="text-xs text-gray-400">
                    {a.followers != null ? `${nf(Number(a.followers))} followers` : ''}
                    {a.posts ? `${a.followers != null ? ' · ' : ''}${a.posts} post${a.posts > 1 ? 's' : ''} here` : ''}
                    {a.engagement ? ` · ${nf(a.engagement)} engagement` : ''}
                    {a.profiled ? ' · profiled' : ''}
                  </p>
                </div>
                {!a.profiled && PLATFORM_KEY[a.platform] && (
                  <button disabled={c.profileBusy != null}
                    onClick={() => c.profileAndAttach(PLATFORM_KEY[a.platform], a.handle)}
                    title="Build a full profile of this account (posting history, reach, behavior) and attach the snapshot to the case"
                    className="text-xs px-2 py-1 rounded-md border border-emerald-300 dark:border-emerald-700 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 disabled:opacity-40 flex-shrink-0 inline-flex items-center gap-1">
                    {c.profileBusy === `${PLATFORM_KEY[a.platform]}:${a.handle}` ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                    Profile
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── How it unfolded ─────────────────────────────────────────── */}
      {syn.chronology.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-2.5">Timeline</h4>
          <div className="space-y-1.5 max-h-72 overflow-y-auto">
            {syn.chronology.map((row, i) => (
              <div key={i} className="flex items-baseline gap-3 text-sm">
                <span className="text-xs text-gray-400 font-mono w-20 flex-shrink-0">{row.date.slice(5)}</span>
                {row.kind === 'milestone'
                  ? <span className="text-xs font-semibold text-blue-600 dark:text-blue-400">{row.label}</span>
                  : row.item?.url
                    ? <a href={row.item.url} target="_blank" rel="noopener noreferrer" className="text-gray-700 dark:text-gray-200 hover:text-blue-600 hover:underline truncate">{row.label}</a>
                    : <span className="text-gray-700 dark:text-gray-200 truncate">{row.label}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Case record (audit) — collapsed by default ──────────────── */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <button onClick={() => setRecordOpen(o => !o)} className="w-full flex items-center gap-2 text-left">
          {recordOpen ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
          <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Audit log</h4>
          <span className="text-xs text-gray-400">{(inc.timeline || []).length} entries · tamper-evident</span>
          <span className="flex-1" />
          <button onClick={e => { e.stopPropagation(); c.runVerifyChain(); }}
            title="Recompute every entry's hash chain to prove nothing was altered or removed"
            className="text-xs px-2.5 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-500 hover:text-gray-700 inline-flex items-center gap-1">
            <ShieldCheck className="w-3.5 h-3.5" /> Verify integrity
          </button>
        </button>
        {c.chain?.intact && (
          <p className="text-xs px-2 py-1 mt-2 rounded bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400">
            ✓ Record intact — {c.chain.items} item(s) verified.
          </p>
        )}
        {recordOpen && (
          <div className="mt-3 space-y-3">
            {syn.otherEvidence.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 mb-1">Files, notes & alerts on record</p>
                <div className="space-y-1">
                  {syn.otherEvidence.map(ev => {
                    const m = ev.meta || {};
                    return (
                      <div key={ev.id} className="flex items-center gap-2 text-xs px-2 py-1.5 rounded border border-gray-100 dark:border-gray-700">
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400 font-semibold flex-shrink-0">{ev.evidence_type.replace('_', ' ')}</span>
                        {ev.evidence_type === 'file' && m.file_id ? (
                          <a href={incidentFileUrl(inc.id, m.file_id)} download className="text-amber-700 dark:text-amber-400 hover:underline truncate flex-1">{m.filename}</a>
                        ) : (
                          <span className="text-gray-700 dark:text-gray-200 truncate flex-1">{cleanText(ev.title || ev.content || ev.source_ref || '')?.slice(0, 120)}</span>
                        )}
                        <span className="text-gray-400 flex-shrink-0">{(ev.captured_at || '').slice(0, 10)}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            <div>
              <p className="text-xs font-semibold text-gray-500 mb-1">Audit trail</p>
              <div className="space-y-1 max-h-64 overflow-y-auto">
                {(inc.timeline || []).map((ev, i) => {
                  const agent = ['agent_brief', 'enrichment', 'agent_suggestion'].includes(ev.kind) || String(ev.actor || '').startsWith('agent');
                  return (
                    <div key={i} className={`flex items-start gap-2 text-xs py-0.5 ${agent ? 'text-violet-600 dark:text-violet-300' : 'text-gray-700 dark:text-gray-200'}`}>
                      <span className="text-gray-400 flex-shrink-0 w-24 font-mono">{(ev.at || '').slice(5, 16).replace('T', ' ')}</span>
                      <span className="text-gray-400 flex-shrink-0 max-w-[90px] truncate">{agent ? 'AI' : ev.actor}</span>
                      <span>
                        {ev.kind === 'note' ? ev.note
                          : ev.kind === 'evidence_added' ? `captured ${ev.new_value} evidence: ${cleanText(ev.note || '')}`
                          : ev.kind === 'created' ? `opened the case (${ev.new_value})`
                          : ev.kind === 'agent_brief' ? `wrote an assessment: ${cleanText(ev.note || '')}`
                          : ev.kind === 'enrichment' ? cleanText(ev.note || 'investigation finished')
                          : ev.kind === 'agent_suggestion' ? `💡 ${ev.note || ''}`
                          : `${ev.kind.replace('_', ' ')}: ${ev.old_value ?? '—'} → ${ev.new_value}${ev.note ? ` (${ev.note})` : ''}`}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <input type="text" value={c.noteText} onChange={e => c.setNoteText(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') c.saveNote(); }}
                placeholder="Add a note to the record…"
                className="flex-1 text-xs px-2.5 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200" />
              <button onClick={c.saveNote} disabled={!c.noteText.trim()}
                className="text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 disabled:opacity-40">Add note</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** "Add manually ▾" menu: search / profile / file / URL capture. */
function AddEvidenceMenu({ c }: { c: IncidentCase }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(o => !o)}
        className="text-xs px-2.5 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-blue-300 inline-flex items-center gap-1">
        Add manually <ChevronDown className="w-3.5 h-3.5" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-1 z-20 w-60 rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg py-1">
            <button onClick={() => { setOpen(false); c.setSearch(s => ({ ...s, open: true })); }}
              className="w-full text-left px-3 py-1.5 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 inline-flex items-center gap-2">
              <Search className="w-3.5 h-3.5 text-gray-400" /> Search collected articles / posts…
            </button>
            <button onClick={() => { setOpen(false); c.openProfilePicker(); }}
              className="w-full text-left px-3 py-1.5 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 inline-flex items-center gap-2">
              <UserCircle className="w-3.5 h-3.5 text-gray-400" /> Account profile…
            </button>
            <button onClick={() => { setOpen(false); c.fileInputRef.current?.click(); }} disabled={c.fileBusy}
              className="w-full text-left px-3 py-1.5 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 inline-flex items-center gap-2 disabled:opacity-50">
              <FileUp className="w-3.5 h-3.5 text-gray-400" /> Upload file… <span className="text-[10px] text-gray-400">max 25 MB</span>
            </button>
            <div className="px-3 py-1.5 border-t border-gray-100 dark:border-gray-700 mt-1">
              <div className="flex items-center gap-1.5">
                <Link2 className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                <input type="text" value={c.evidenceUrl} onChange={e => c.setEvidenceUrl(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && c.evidenceUrl.trim()) { c.captureUrl(); setOpen(false); } }}
                  placeholder="Paste a URL, Enter to capture"
                  className="flex-1 text-xs px-1.5 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200" />
              </div>
            </div>
          </div>
        </>
      )}
      <input ref={c.fileInputRef} type="file" className="hidden" onChange={e => c.onFilePicked(e.target.files?.[0])} />
    </>
  );
}
