/**
 * Monthly market briefings.
 *
 * A briefing is assembled facts with model prose on top, so the reader needs
 * both: the text, and the evidence it was written from. "Show the evidence"
 * is not a debugging aid here — it is how someone checks that a figure in the
 * prose is real, and the whole design rests on that being checkable.
 */

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, FileText, Loader2, Play } from 'lucide-react';
import {
  generateBriefing, getBriefing, getBriefings, setBriefingStatus,
  type BriefingDetail, type BriefingSummary,
} from '../../services/marketMonitorApi';

/** The app has no typography plugin, so the rendered markdown is styled here
 *  rather than relying on a `prose` class that does not exist. */
const PROSE_CSS = `
.mm-prose h2 { font-size: 1.05rem; font-weight: 600; color: #0f172a; margin: 1.2rem 0 .4rem; }
.mm-prose h3 { font-size: .95rem; font-weight: 600; color: #1e293b; margin: 1rem 0 .3rem; }
.mm-prose h4, .mm-prose h5 { font-size: .88rem; font-weight: 600; color: #334155; margin: .8rem 0 .25rem; }
.mm-prose p { margin: .55rem 0; line-height: 1.6; }
.mm-prose ul { margin: .5rem 0 .5rem 1.1rem; list-style: disc; }
.mm-prose li { margin: .25rem 0; line-height: 1.55; }
.mm-prose hr { border: 0; border-top: 1px solid #e2e8f0; margin: 1rem 0; }
.mm-prose strong { font-weight: 600; color: #0f172a; }
`;

const STATUS_TONE: Record<string, string> = {
  draft: 'bg-slate-100 text-slate-600 border-slate-200',
  approved: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  rejected: 'bg-red-50 text-red-700 border-red-200',
};

/** Very small markdown: headings, bold, bullets, paragraphs. The briefing is
 *  the only markdown this app renders, and a library for four rules would be
 *  more code than the four rules. */
function renderMarkdown(md: string): string {
  const esc = (s: string) => s
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const inline = (s: string) => esc(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*(?!\*)(.+?)\*(?!\*)/g, '$1<em>$2</em>')
    .replace(/_(.+?)_/g, '<em>$1</em>');

  const out: string[] = [];
  let inList = false;
  for (const raw of md.split('\n')) {
    const line = raw.trimEnd();
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    if (bullet) {
      if (!inList) { out.push('<ul>'); inList = true; }
      out.push(`<li>${inline(bullet[1])}</li>`);
      continue;
    }
    if (inList) { out.push('</ul>'); inList = false; }
    const head = /^(#{1,4})\s+(.*)$/.exec(line);
    if (head) {
      const level = Math.min(head[1].length + 1, 5);
      out.push(`<h${level}>${inline(head[2])}</h${level}>`);
    } else if (line === '---') {
      out.push('<hr/>');
    } else if (line) {
      out.push(`<p>${inline(line)}</p>`);
    }
  }
  if (inList) out.push('</ul>');
  return out.join('');
}

export function MarketBriefingsView({ marketId }: { marketId: number }) {
  const [list, setList] = useState<BriefingSummary[] | null>(null);
  const [open, setOpen] = useState<BriefingDetail | null>(null);
  const [showFacts, setShowFacts] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    getBriefings(marketId)
      .then(r => setList(r.briefings))
      .catch(e => setError(String(e.message ?? e)));
  }, [marketId]);

  useEffect(() => { setOpen(null); reload(); }, [reload]);

  async function openBriefing(id: number) {
    setShowFacts(false);
    try {
      setOpen(await getBriefing(marketId, id));
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  async function writeBriefing() {
    setBusy(true); setNote(null);
    try {
      const r = await generateBriefing(marketId, {});
      setNote(
        r.generation === 'fallback'
          ? `${r.period_label}: ${r.item_count} items — too few to write from, or the model returned nothing. The stored briefing is the evidence itself.`
          : `${r.period_label} written from ${r.item_count} items.`);
      reload();
      if (r.id) openBriefing(r.id);
    } catch (e: any) {
      setNote(`Could not write it: ${e.message ?? e}`);
    } finally {
      setBusy(false);
    }
  }

  async function mark(status: string) {
    if (!open) return;
    try {
      await setBriefingStatus(marketId, open.id, status);
      setOpen({ ...open, status: status as BriefingDetail['status'] });
      reload();
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  if (error) {
    return <div className="text-sm text-red-700 p-3 border rounded-md bg-red-50">
      {error}</div>;
  }

  return (
    <div className="space-y-4">
      <style>{PROSE_CSS}</style>
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm text-slate-600 max-w-2xl">
          One briefing per calendar month, written from the month's
          announcements, coverage, hiring and headcount readings. The figures
          are assembled from stored records first and the narrative is written
          around them, so nothing in a briefing is a number the model invented.
        </p>
        <div className="flex-1" />
        <button onClick={writeBriefing} disabled={busy}
                className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50
                           disabled:opacity-50 inline-flex items-center gap-1.5">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" />
                : <Play className="w-4 h-4" />}
          Write last month's
        </button>
      </div>

      {note && (
        <div className="text-sm px-3 py-2 rounded-md bg-slate-100 text-slate-700">
          {note}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <div className="border rounded-lg bg-white divide-y self-start">
          {list === null ? (
            <div className="py-8 text-center text-slate-400">
              <Loader2 className="w-4 h-4 animate-spin mx-auto" />
            </div>
          ) : list.length === 0 ? (
            <p className="text-sm text-slate-500 p-4 text-center">
              None yet.
            </p>
          ) : list.map(b => (
            <button key={b.id} onClick={() => openBriefing(b.id)}
                    className={`w-full text-left p-3 hover:bg-slate-50 ${
                      open?.id === b.id ? 'bg-slate-50' : ''}`}>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-slate-800">
                  {b.period_label}
                </span>
                <span className={`text-xs px-1.5 py-0.5 rounded border ${
                  STATUS_TONE[b.status]}`}>
                  {b.status}
                </span>
              </div>
              <div className="text-xs text-slate-500 mt-0.5">
                {b.sources ?? 0} sources
                {b.generation === 'fallback' && ' · evidence only'}
              </div>
            </button>
          ))}
        </div>

        <div className="border rounded-lg bg-white p-4 min-h-[300px]">
          {!open ? (
            <div className="py-16 text-center text-slate-400">
              <FileText className="w-8 h-8 mx-auto mb-2" />
              <p className="text-sm">Pick a month.</p>
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2 pb-3 border-b mb-3">
                <span className="text-sm font-medium text-slate-800">
                  {open.title ?? open.period_label}
                </span>
                <span className={`text-xs px-1.5 py-0.5 rounded border ${
                  STATUS_TONE[open.status]}`}>{open.status}</span>
                <span className="text-xs text-slate-500">
                  {open.model_used} · {open.article_uris.length} sources
                </span>
                <div className="flex-1" />
                <button onClick={() => setShowFacts(v => !v)}
                        className="text-xs px-2 py-1 border rounded hover:bg-slate-50">
                  {showFacts ? 'Show the briefing' : 'Show the evidence'}
                </button>
                {open.status !== 'approved' && (
                  <button onClick={() => mark('approved')}
                          className="text-xs px-2 py-1 border rounded
                                     hover:bg-emerald-50 text-emerald-700
                                     border-emerald-200 inline-flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" /> Approve
                  </button>
                )}
                {open.status !== 'rejected' && (
                  <button onClick={() => mark('rejected')}
                          className="text-xs px-2 py-1 border rounded
                                     hover:bg-red-50 text-red-700 border-red-200">
                    Reject
                  </button>
                )}
              </div>

              {open.generation === 'fallback' && (
                <div className="flex items-start gap-2 text-sm px-3 py-2 mb-3
                                rounded-md bg-amber-50 text-amber-800
                                border border-amber-200">
                  <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                  <span>
                    This is the assembled evidence, not a written briefing —
                    either the month was too quiet to write about or the model
                    returned nothing usable.
                  </span>
                </div>
              )}

              {open.lint?.length > 0 && (
                <div className="text-xs px-3 py-2 mb-3 rounded-md bg-amber-50
                                text-amber-800 border border-amber-200">
                  {open.lint.map((l, i) => (
                    <div key={i}>{l.check}: {l.detail}</div>
                  ))}
                </div>
              )}

              {showFacts ? (
                <pre className="text-xs bg-slate-50 border rounded p-3
                                overflow-x-auto whitespace-pre-wrap">
                  {JSON.stringify(open.facts, null, 1)}
                </pre>
              ) : (
                <div className="mm-prose text-sm text-slate-700"
                     dangerouslySetInnerHTML={{
                       __html: renderMarkdown(open.report_content || ''),
                     }} />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
