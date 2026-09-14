/**
 * Reports tab: generated, versioned market reports.
 *
 * A report is assembled facts with model prose on top, so the reader needs
 * both: the text, and the evidence it was written from. "Show the evidence"
 * is not a debugging aid here — it is how someone checks that a figure in the
 * prose is real, and the whole design rests on that being checkable. The
 * component and API names underneath still say "briefing" (matching the
 * backend route and DB table) — only the on-screen copy says "report", so a
 * generated document is never called a "brief," which is Pulse's word now.
 */

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Download, FileText, History, Loader2, Pencil, PenLine, Play, Save, X } from 'lucide-react';
import { MarkdownEditor } from './MarkdownEditor';
import { getBriefingRevision, type BriefingRevision, restoreBriefingRevision, getBriefingRevisions, editBriefing,
  generateBriefing, getBriefing, getBriefings, setBriefingStatus, writePiece,
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
.mm-prose a.mm-cite { font-size: .78em; font-weight: 600; color: #0369a1;
                      text-decoration: none; padding: 0 .1em; }
.mm-prose a.mm-cite:hover { text-decoration: underline; }
.dark .mm-prose h2 { color: #f3f4f6; }
.dark .mm-prose h3 { color: #e5e7eb; }
.dark .mm-prose h4, .dark .mm-prose h5 { color: #d1d5db; }
.dark .mm-prose hr { border-top-color: #374151; }
.dark .mm-prose strong { color: #f3f4f6; }
.dark .mm-prose a.mm-cite { color: #38bdf8; }
`;

const STATUS_TONE: Record<string, string> = {
  draft: 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-gray-700 dark:text-gray-400 dark:border-gray-700',
  approved: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800',
  rejected: 'bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800',
};

/** A citation's real URI/title, keyed by its [A3]/[C7] ID — the same shape
 *  the backend attaches to a report's stored facts. */
type CitationIndex = Record<string, { uri: string; title: string;
                                      vendor?: string; source?: string }>;

/** Very small markdown: headings, bold, bullets, paragraphs, citation links.
 *  The report is the only markdown this app renders, and a library for five
 *  rules would be more code than the five rules. */
function renderMarkdown(md: string, citations?: CitationIndex): string {
  const esc = (s: string) => s
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const inline = (s: string) => esc(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*(?!\*)(.+?)\*(?!\*)/g, '$1<em>$2</em>')
    // Underscore emphasis only at word edges: an X handle like jp_young_26
    // or a snake_case name is not italics (the operator saw one mangled).
    .replace(/(^|[\s(])_(\S(?:.*?\S)?)_(?=[\s).,;:!?]|$)/g, '$1<em>$2</em>')
    // A markdown link, [text](url), as a person writes in an analysis
    // piece; the public page renders these, so the preview must too.
    // Runs before the bare-URL rule, which would otherwise wrap the href.
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
             '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
    // A citation's reference entry ends in a bare URL. Must run BEFORE the
    // citation-marker replace below: that one injects a real <a href="...">
    // tag, and if this regex ran after, it would re-match the URL sitting
    // inside that href and wrap it again, producing nested/malformed tags
    // that browsers render as literal text. The lookbehind keeps it off the
    // href the markdown-link rule just wrote.
    .replace(/(?<!href=")(https?:\/\/[^\s<]+)/g,
             '<a href="$1" target="_blank" rel="noreferrer">$1</a>')
    // An inline citation marker becomes a link to the article it names,
    // right where the reader is, not only in the References list below.
    .replace(/\[([AC]\d+)\]/g, (whole, id) => {
      const ref = citations?.[id];
      return ref
        ? `<a href="${ref.uri}" target="_blank" rel="noreferrer" ` +
          `class="mm-cite" title="${esc(ref.title)}">[${id}]</a>`
        : whole;
    });

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

type PeriodKind = 'day' | 'week' | 'month' | 'year';

const PERIOD_LABEL: Record<PeriodKind, string> = {
  day: 'Day', week: 'Week', month: 'Month', year: 'Year',
};

function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-` +
    `${String(d.getDate()).padStart(2, '0')}`;
}

/** Options for one period kind, newest first, each an ISO date the backend
 *  can resolve back to that whole period. The period in progress is left out
 *  of every list on purpose — a briefing about it would be wrong by the time
 *  it ends, and the backend rejects it outright if one slips through. */
function periodOptions(kind: PeriodKind): { refDate: string; label: string }[] {
  const now = new Date();
  const out: { refDate: string; label: string }[] = [];
  if (kind === 'day') {
    for (let i = 1; i <= 30; i++) {
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
      out.push({
        refDate: isoDate(d),
        label: d.toLocaleDateString(undefined,
          { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }),
      });
    }
  } else if (kind === 'week') {
    // Monday of this week, then step back a week at a time.
    const thisMonday = new Date(now);
    thisMonday.setDate(now.getDate() - ((now.getDay() + 6) % 7));
    for (let i = 1; i <= 12; i++) {
      const monday = new Date(thisMonday);
      monday.setDate(thisMonday.getDate() - 7 * i);
      const sunday = new Date(monday);
      sunday.setDate(monday.getDate() + 6);
      out.push({
        refDate: isoDate(monday),
        label: `Week of ${monday.toLocaleDateString(undefined,
          { month: 'short', day: 'numeric' })}–${sunday.toLocaleDateString(undefined,
          { month: 'short', day: 'numeric', year: 'numeric' })}`,
      });
    }
  } else if (kind === 'year') {
    for (let i = 1; i <= 5; i++) {
      out.push({ refDate: `${now.getFullYear() - i}-06-15`,
                 label: String(now.getFullYear() - i) });
    }
  } else {
    for (let i = 1; i <= 12; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      out.push({
        refDate: isoDate(d),
        label: d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' }),
      });
    }
  }
  return out;
}

export function MarketBriefingsView({ marketId, onFeedChanged }: {
  marketId: number;
  /** An approved briefing is an item in the news feed, and rejecting or
   *  regenerating one takes it out again. The page owns the feed's article
   *  list, so it is told when that list has changed underneath it. */
  onFeedChanged?: () => void;
}) {
  const [list, setList] = useState<BriefingSummary[] | null>(null);
  const [open, setOpen] = useState<BriefingDetail | null>(null);
  const [showFacts, setShowFacts] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Editing by hand: the draft text and title, the history drawer, and the
  // revision being previewed. The previous text is always kept server-side.
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [draftTitle, setDraftTitle] = useState('');
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState<BriefingRevision[] | null>(null);
  const [preview, setPreview] = useState<{ id: number; content: string } | null>(null);
  const [periodKind, setPeriodKind] = useState<PeriodKind>('month');
  // Our own pieces: a person writes an analysis or a note here; it is a draft
  // until approved, like a briefing.
  const [writing, setWriting] = useState(false);
  const [pieceKind, setPieceKind] = useState<'analysis' | 'note'>('analysis');
  const [pieceTitle, setPieceTitle] = useState('');
  const [pieceAuthor, setPieceAuthor] = useState('');
  const [pieceBody, setPieceBody] = useState('');
  const options = periodOptions(periodKind);
  // The most recent complete period of the chosen kind, matching what
  // "Write last month's" wrote before there was a picker at all.
  const [refDate, setRefDate] = useState(options[0].refDate);

  const reload = useCallback(() => {
    getBriefings(marketId)
      .then(r => setList(r.briefings))
      .catch(e => setError(String(e.message ?? e)));
  }, [marketId]);

  useEffect(() => { setOpen(null); reload(); }, [reload]);

  // Switching kind invalidates the old refDate — a month's first-of-month
  // is not a valid week-of-Monday.
  useEffect(() => { setRefDate(periodOptions(periodKind)[0].refDate); },
           [periodKind]);

  async function openBriefing(id: number) {
    setEditing(false); setHistory(null); setPreview(null);
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
      const r = await generateBriefing(marketId, { periodKind, refDate });
      setNote(
        r.generation === 'fallback'
          ? `${r.period_label}: ${r.item_count} items — too few to write from, or the model returned nothing. The stored briefing is the evidence itself.`
          : `${r.period_label} written from ${r.item_count} items.`);
      reload();
      onFeedChanged?.();
      if (r.id) openBriefing(r.id);
    } catch (e: any) {
      setNote(`Could not write it: ${e.message ?? e}`);
    } finally {
      setBusy(false);
    }
  }

  async function savePiece() {
    setBusy(true); setNote(null);
    try {
      const row = await writePiece(marketId, {
        kind: pieceKind, title: pieceTitle.trim(), report_content: pieceBody,
        author: pieceAuthor.trim() || null,
      });
      setNote(`Saved as a draft. Approve it to publish it on the front page and in the feed.`);
      setWriting(false); setPieceTitle(''); setPieceBody('');
      reload();
      openBriefing(row.id);
    } catch (e: any) {
      setNote(`Could not save it: ${e.message ?? e}`);
    } finally {
      setBusy(false);
    }
  }

  function startEdit() {
    if (!open) return;
    setDraft(open.report_content || '');
    setDraftTitle(open.title || '');
    setEditing(true); setShowFacts(false); setNote(null); setError(null);
  }

  async function saveEdit() {
    if (!open) return;
    setSaving(true); setError(null);
    try {
      const updated = await editBriefing(marketId, open.id, {
        report_content: draft, title: draftTitle.trim() || null,
      });
      setOpen(updated);
      setEditing(false);
      setHistory(null);
      setNote(updated.status === 'approved'
        ? 'Saved. The feed item follows the new text.'
        : 'Saved. The previous text is kept in the history.');
      setList(prev => prev?.map(b => b.id === updated.id
        ? { ...b, title: updated.title, generation: updated.generation, updated_at: updated.updated_at }
        : b) ?? prev);
      onFeedChanged?.();
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setSaving(false);
    }
  }

  async function loadHistory() {
    if (!open) return;
    if (history) { setHistory(null); setPreview(null); return; }
    try {
      setHistory((await getBriefingRevisions(marketId, open.id)).revisions);
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  async function previewRevision(id: number) {
    if (!open) return;
    if (preview?.id === id) { setPreview(null); return; }
    try {
      const r = await getBriefingRevision(marketId, open.id, id);
      setPreview({ id, content: r.report_content });
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  async function restoreRevision(id: number) {
    if (!open) return;
    if (!window.confirm('Put this earlier text back? The current text is kept in the history.')) return;
    setBusy(true); setError(null);
    try {
      const updated = await restoreBriefingRevision(marketId, open.id, id);
      setOpen(updated); setHistory(null); setPreview(null);
      setNote('Restored. The text that was there is kept in the history.');
      onFeedChanged?.();
    } catch (e: any) {
      setError(String(e.message ?? e));
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
      onFeedChanged?.();
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  function downloadReport() {
    if (!open) return;
    const blob = new Blob([open.report_content || ''],
      { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${(open.title ?? open.period_label).replace(/[^\w-]+/g, '-')}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (error) {
    return <div className="text-sm text-red-700 p-3 border rounded-md bg-red-50 dark:text-red-400 dark:bg-red-900/20">
      {error}</div>;
  }

  return (
    <div className="space-y-4">
      <style>{PROSE_CSS}</style>
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm text-slate-600 max-w-2xl dark:text-gray-400">
          One report per period — day, week, month or year — written from
          that period's announcements, coverage, hiring and headcount
          readings. The figures are assembled from stored records first and
          the narrative is written around them, so nothing in a report is a
          number the model invented. Claims drawn from one specific fact
          carry a citation, resolved into a References list at the end.
        </p>
        <div className="flex-1" />
        <div className="flex border rounded-md overflow-hidden">
          {(['day', 'week', 'month', 'year'] as const).map(k => (
            <button key={k} onClick={() => setPeriodKind(k)}
                    className={`text-sm px-2.5 py-1.5 ${
                      periodKind === k
                        ? 'bg-slate-800 text-white'
                        : 'bg-white text-slate-600 hover:bg-slate-50 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'}`}>
              {PERIOD_LABEL[k]}
            </button>
          ))}
        </div>
        <select value={refDate} onChange={e => setRefDate(e.target.value)}
                className="text-sm px-2 py-1.5 border rounded-md bg-white
                           text-slate-700 dark:bg-gray-800 dark:text-gray-300">
          {options.map(o => (
            <option key={o.refDate} value={o.refDate}>{o.label}</option>
          ))}
        </select>
        <button onClick={writeBriefing} disabled={busy}
                className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50
                           disabled:opacity-50 inline-flex items-center gap-1.5 dark:hover:bg-gray-700">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" />
                : <Play className="w-4 h-4" />}
          Generate report
        </button>
        <button onClick={() => { setWriting(w => !w); setNote(null); }} disabled={busy}
                className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50
                           disabled:opacity-50 inline-flex items-center gap-1.5 dark:hover:bg-gray-700">
          <PenLine className="w-4 h-4" />
          Write a piece
        </button>
      </div>

      {writing && (
        <div className="border rounded-lg bg-white p-4 space-y-3 dark:bg-gray-800">
          <p className="text-sm text-slate-600 dark:text-gray-400">
            Your own analysis or note, in Markdown. It is saved as a draft; approving it
            puts it on the market's front page, under Analysis, and into the feed. The
            page says who wrote it.
          </p>
          <div className="flex flex-wrap gap-2">
            <select value={pieceKind} onChange={e => setPieceKind(e.target.value as 'analysis' | 'note')}
                    className="text-sm px-2 py-1.5 border rounded-md bg-white text-slate-700 dark:bg-gray-800 dark:text-gray-300">
              <option value="analysis">Analysis</option>
              <option value="note">Note</option>
            </select>
            <input value={pieceTitle} onChange={e => setPieceTitle(e.target.value)}
                   placeholder="Title" maxLength={300}
                   className="flex-1 min-w-[240px] text-sm px-2 py-1.5 border rounded-md bg-white text-slate-800 dark:bg-gray-800 dark:text-gray-100" />
            <input value={pieceAuthor} onChange={e => setPieceAuthor(e.target.value)}
                   placeholder="Author (your name)" maxLength={120}
                   className="min-w-[200px] text-sm px-2 py-1.5 border rounded-md bg-white text-slate-800 dark:bg-gray-800 dark:text-gray-100" />
          </div>
          <MarkdownEditor value={pieceBody} onChange={setPieceBody} rows={18} autoFocus
                          placeholder="The piece. Markdown: # heading, **bold**, - list, [link](url)." />
          <div className="flex gap-2">
            <button onClick={savePiece} disabled={busy || !pieceTitle.trim() || !pieceBody.trim()}
                    className="text-sm px-3 py-1.5 border rounded-md bg-slate-800 text-white hover:bg-slate-700 disabled:opacity-50 inline-flex items-center gap-1.5">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save as draft
            </button>
            <button onClick={() => setWriting(false)} disabled={busy}
                    className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50 dark:hover:bg-gray-700">
              Cancel
            </button>
          </div>
        </div>
      )}

      {note && (
        <div className="text-sm px-3 py-2 rounded-md bg-slate-100 text-slate-700 dark:bg-gray-700 dark:text-gray-300">
          {note}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <div className="border rounded-lg bg-white divide-y self-start dark:bg-gray-800">
          {list === null ? (
            <div className="py-8 text-center text-slate-400 dark:text-gray-500">
              <Loader2 className="w-4 h-4 animate-spin mx-auto" />
            </div>
          ) : list.length === 0 ? (
            <p className="text-sm text-slate-500 p-4 text-center dark:text-gray-400">
              None yet.
            </p>
          ) : list.map(b => (
            <button key={b.id} onClick={() => openBriefing(b.id)}
                    className={`w-full text-left p-3 hover:bg-slate-50 dark:hover:bg-gray-700 ${
                      open?.id === b.id ? 'bg-slate-50 dark:bg-gray-700' : ''}`}>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-slate-800 dark:text-gray-100">
                  {b.kind === 'briefing' ? b.period_label : (b.title ?? b.period_label)}
                </span>
                <span className={`text-xs px-1.5 py-0.5 rounded border ${
                  STATUS_TONE[b.status]}`}>
                  {b.status}
                </span>
              </div>
              <div className="text-xs text-slate-500 mt-0.5 dark:text-gray-400">
                {b.kind === 'briefing'
                  ? <>{b.sources ?? 0} sources{b.generation === 'fallback' && ' · evidence only'}</>
                  : <>{b.kind === 'analysis' ? 'Analysis' : 'Note'}{b.author ? ` · ${b.author}` : ''}</>}
              </div>
            </button>
          ))}
        </div>

        <div className="border rounded-lg bg-white p-4 min-h-[300px] dark:bg-gray-800">
          {!open ? (
            <div className="py-16 text-center text-slate-400 dark:text-gray-500">
              <FileText className="w-8 h-8 mx-auto mb-2" />
              <p className="text-sm">Pick a report.</p>
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2 pb-3 border-b mb-3">
                <span className="text-sm font-medium text-slate-800 dark:text-gray-100">
                  {open.title ?? open.period_label}
                </span>
                <span className={`text-xs px-1.5 py-0.5 rounded border ${
                  STATUS_TONE[open.status]}`}>{open.status}</span>
                <span className="text-xs text-slate-500 dark:text-gray-400">
                  {open.model_used} · {open.article_uris.length} sources
                  {open.generation === 'edited' && ' · edited by hand'}
                </span>
                <div className="flex-1" />
                {!editing && (
                  <button onClick={startEdit}
                          className="text-xs px-2 py-1 border rounded hover:bg-slate-50
                                     inline-flex items-center gap-1 dark:hover:bg-gray-700">
                    <Pencil className="w-3 h-3" /> Edit
                  </button>
                )}
                {!editing && (
                  <button onClick={loadHistory}
                          className="text-xs px-2 py-1 border rounded hover:bg-slate-50
                                     inline-flex items-center gap-1 dark:hover:bg-gray-700">
                    <History className="w-3 h-3" /> History
                  </button>
                )}
                <button onClick={downloadReport}
                        className="text-xs px-2 py-1 border rounded hover:bg-slate-50
                                   inline-flex items-center gap-1 dark:hover:bg-gray-700">
                  <Download className="w-3 h-3" /> Download
                </button>
                <button onClick={() => setShowFacts(v => !v)}
                        className="text-xs px-2 py-1 border rounded hover:bg-slate-50 dark:hover:bg-gray-700">
                  {showFacts ? 'Show the report' : 'Show the evidence'}
                </button>
                {open.status !== 'approved' && (
                  <button onClick={() => mark('approved')}
                          className="text-xs px-2 py-1 border rounded
                                     hover:bg-emerald-50 text-emerald-700
                                     border-emerald-200 inline-flex items-center gap-1 dark:text-emerald-400 dark:border-emerald-800">
                    <CheckCircle2 className="w-3 h-3" /> Approve
                  </button>
                )}
                {open.status !== 'rejected' && (
                  <button onClick={() => mark('rejected')}
                          className="text-xs px-2 py-1 border rounded
                                     hover:bg-red-50 text-red-700 border-red-200 dark:text-red-400 dark:border-red-800">
                    Reject
                  </button>
                )}
              </div>

              {open.generation === 'fallback' && (
                <div className="flex items-start gap-2 text-sm px-3 py-2 mb-3
                                rounded-md bg-amber-50 text-amber-800
                                border border-amber-200 dark:bg-amber-900/20 dark:border-amber-800">
                  <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                  <span>
                    This is the assembled evidence, not a written report —
                    either the period was too quiet to write about or the
                    model returned nothing usable.
                  </span>
                </div>
              )}

              {open.lint?.length > 0 && (
                <div className="text-xs px-3 py-2 mb-3 rounded-md bg-amber-50
                                text-amber-800 border border-amber-200 dark:bg-amber-900/20 dark:border-amber-800">
                  {open.lint.map((l, i) => (
                    <div key={i}>{l.check}: {l.detail}</div>
                  ))}
                </div>
              )}

              {editing && (
                <div className="mb-3">
                  <input value={draftTitle} onChange={e => setDraftTitle(e.target.value)}
                         placeholder="Title" maxLength={300}
                         className="w-full text-sm font-medium px-2 py-1 mb-2 rounded border
                                    bg-white dark:bg-gray-900 dark:border-gray-600 dark:text-gray-100" />
                  <div className="text-xs text-slate-500 mb-1 dark:text-gray-400">
                    Markdown. Citations like [A3] stay linked to the evidence.
                  </div>
                  <MarkdownEditor value={draft} onChange={setDraft} rows={26}
                                  renderPreview={md => renderMarkdown(md, open.facts?.citation_index)} />
                  <div className="flex items-center gap-2 mt-2">
                    <button onClick={saveEdit} disabled={saving || !draft.trim()}
                            className="text-xs px-2.5 py-1.5 border rounded bg-white hover:bg-emerald-50
                                       text-emerald-700 border-emerald-200 disabled:opacity-50
                                       inline-flex items-center gap-1 dark:bg-gray-800 dark:text-emerald-400 dark:border-emerald-800">
                      {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />} Save
                    </button>
                    <button onClick={() => setEditing(false)} disabled={saving}
                            className="text-xs px-2.5 py-1.5 border rounded hover:bg-slate-50
                                       inline-flex items-center gap-1 dark:hover:bg-gray-700">
                      <X className="w-3 h-3" /> Cancel
                    </button>
                    <span className="text-xs text-slate-500 dark:text-gray-400">
                      The previous text is kept and can be restored from History.
                      {open.status === 'approved' && ' This briefing is approved: saving updates its feed item.'}
                    </span>
                  </div>
                </div>
              )}

              {history && !editing && (
                <div className="mb-3 border rounded p-3 dark:border-gray-700">
                  <div className="text-xs font-medium text-slate-700 mb-1 dark:text-gray-200">
                    History — every earlier text, newest first
                  </div>
                  {history.length === 0 ? (
                    <div className="text-xs text-slate-500 dark:text-gray-400">No earlier text: this is the model's draft as written.</div>
                  ) : (
                    <ul className="text-xs space-y-1">
                      {history.map(r => (
                        <li key={r.id} className="flex flex-wrap items-center gap-2">
                          <span className="text-slate-600 dark:text-gray-300">
                            {r.saved_at.slice(0, 16).replace('T', ' ')}
                          </span>
                          <span className="text-slate-500 dark:text-gray-400">
                            {r.reason}{r.saved_by ? ` by ${r.saved_by}` : ''} · {r.generation ?? '—'} · {r.length.toLocaleString()} chars
                          </span>
                          <button onClick={() => previewRevision(r.id)}
                                  className="underline text-sky-700 dark:text-sky-400">
                            {preview?.id === r.id ? 'hide' : 'view'}
                          </button>
                          <button onClick={() => restoreRevision(r.id)} disabled={busy}
                                  className="underline text-amber-700 dark:text-amber-400">restore</button>
                        </li>
                      ))}
                    </ul>
                  )}
                  {preview && (
                    <div className="mm-prose text-sm text-slate-700 dark:text-gray-300 border-t mt-2 pt-2
                                    max-h-[24rem] overflow-y-auto dark:border-gray-700"
                         dangerouslySetInnerHTML={{
                           __html: renderMarkdown(preview.content, open.facts?.citation_index),
                         }} />
                  )}
                </div>
              )}

              {editing ? null : showFacts ? (
                <pre className="text-xs bg-slate-50 border rounded p-3
                                overflow-x-auto whitespace-pre-wrap dark:bg-gray-700">
                  {JSON.stringify(open.facts, null, 1)}
                </pre>
              ) : (
                <div className="mm-prose text-sm text-slate-700 dark:text-gray-300"
                     dangerouslySetInnerHTML={{
                       __html: renderMarkdown(open.report_content || '',
                                              open.facts?.citation_index),
                     }} />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
