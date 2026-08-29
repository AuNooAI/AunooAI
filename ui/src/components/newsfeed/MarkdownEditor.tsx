/**
 * A Markdown editor for writing pieces and editing briefings.
 *
 * A toolbar that wraps or prefixes the selection (bold, italic, headings,
 * link, lists, quote, code), Write / Split / Preview views, keyboard
 * shortcuts (Ctrl/Cmd+B, I, K), Tab indents a list item, and a word count.
 * The preview is react-markdown with GitHub tables and lists, unless the
 * caller supplies its own renderer (the briefing editor keeps citations
 * linked to their evidence).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Bold, Code, Heading2, Heading3, Italic, Link2, List, ListOrdered, Quote } from 'lucide-react';

type View = 'write' | 'split' | 'preview';

export function MarkdownEditor({ value, onChange, rows = 18, placeholder, renderPreview, autoFocus }: {
  value: string;
  onChange: (next: string) => void;
  rows?: number;
  placeholder?: string;
  /** Custom preview as an HTML string; the default is react-markdown. */
  renderPreview?: (md: string) => string;
  autoFocus?: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [view, setView] = useState<View>('split');

  // Apply an edit around the current selection and put the caret back where
  // a writer expects it: inside the wrapper when nothing was selected, after
  // the wrapped text otherwise.
  const apply = useCallback((fn: (sel: string) => { text: string; caret?: [number, number] }) => {
    const el = ref.current;
    if (!el) return;
    const start = el.selectionStart, end = el.selectionEnd;
    const sel = value.slice(start, end);
    const { text, caret } = fn(sel);
    const next = value.slice(0, start) + text + value.slice(end);
    onChange(next);
    const [a, b] = caret ?? [start + text.length, start + text.length];
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(a, b); });
  }, [value, onChange]);

  const wrap = useCallback((left: string, right = left, hint = 'text') => apply(sel => {
    const inner = sel || hint;
    const text = left + inner + right;
    const s = left.length;
    return { text, caret: sel ? undefined : [s, s + inner.length] as [number, number] };
  }), [apply]);

  // A prefix goes at the start of every selected line, on its own line.
  const prefixLines = useCallback((prefix: string | ((i: number) => string)) => {
    const el = ref.current;
    if (!el) return;
    const start = el.selectionStart, end = el.selectionEnd;
    const lineStart = value.lastIndexOf('\n', start - 1) + 1;
    const lineEndIdx = value.indexOf('\n', end);
    const lineEnd = lineEndIdx === -1 ? value.length : lineEndIdx;
    const block = value.slice(lineStart, lineEnd);
    const lines = block.split('\n');
    const done = lines.map((l, i) => (typeof prefix === 'function' ? prefix(i) : prefix) + l).join('\n');
    const lead = lineStart > 0 && value[lineStart - 1] !== '\n' ? '\n' : '';
    const next = value.slice(0, lineStart) + lead + done + value.slice(lineEnd);
    onChange(next);
    const caret = lineStart + lead.length + done.length;
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(caret, caret); });
  }, [value, onChange]);

  const heading = useCallback((level: number) => prefixLines('#'.repeat(level) + ' '), [prefixLines]);

  const link = useCallback(() => apply(sel => {
    const label = sel || 'link text';
    const text = `[${label}](https://)`;
    const s = label.length + 3;
    return { text, caret: [s, s + 8] as [number, number] };
  }), [apply]);

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key.toLowerCase() === 'b') { e.preventDefault(); wrap('**'); }
    else if (mod && e.key.toLowerCase() === 'i') { e.preventDefault(); wrap('_'); }
    else if (mod && e.key.toLowerCase() === 'k') { e.preventDefault(); link(); }
    else if (e.key === 'Tab') {
      // Indent or outdent the current line; a writer inside a list expects it.
      e.preventDefault();
      const el = e.currentTarget;
      const start = el.selectionStart;
      const lineStart = value.lastIndexOf('\n', start - 1) + 1;
      if (e.shiftKey) {
        if (value.slice(lineStart, lineStart + 2) === '  ') {
          onChange(value.slice(0, lineStart) + value.slice(lineStart + 2));
          requestAnimationFrame(() => el.setSelectionRange(start - 2, start - 2));
        }
      } else {
        onChange(value.slice(0, lineStart) + '  ' + value.slice(lineStart));
        requestAnimationFrame(() => el.setSelectionRange(start + 2, start + 2));
      }
    }
  }

  useEffect(() => { if (autoFocus) ref.current?.focus(); }, [autoFocus]);

  const words = value.trim() ? value.trim().split(/\s+/).length : 0;
  const btn = 'p-1.5 rounded hover:bg-slate-100 text-slate-600 dark:text-gray-300 dark:hover:bg-gray-700';
  const tab = (v: View, label: string) => (
    <button type="button" onClick={() => setView(v)}
            className={`text-xs px-2 py-1 rounded ${view === v
              ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-100 dark:text-gray-300 dark:hover:bg-gray-700'}`}>
      {label}
    </button>
  );

  const showWrite = view !== 'preview';
  const showPreview = view !== 'write';

  return (
    <div className="border rounded-md bg-white dark:bg-gray-900 dark:border-gray-600">
      <div className="flex flex-wrap items-center gap-0.5 px-1.5 py-1 border-b dark:border-gray-700">
        <button type="button" title="Bold (Ctrl+B)" className={btn} onClick={() => wrap('**')}><Bold className="w-4 h-4" /></button>
        <button type="button" title="Italic (Ctrl+I)" className={btn} onClick={() => wrap('_')}><Italic className="w-4 h-4" /></button>
        <span className="w-px h-4 bg-slate-200 mx-1 dark:bg-gray-700" />
        <button type="button" title="Heading" className={btn} onClick={() => heading(2)}><Heading2 className="w-4 h-4" /></button>
        <button type="button" title="Subheading" className={btn} onClick={() => heading(3)}><Heading3 className="w-4 h-4" /></button>
        <span className="w-px h-4 bg-slate-200 mx-1 dark:bg-gray-700" />
        <button type="button" title="Link (Ctrl+K)" className={btn} onClick={link}><Link2 className="w-4 h-4" /></button>
        <button type="button" title="Bulleted list" className={btn} onClick={() => prefixLines('- ')}><List className="w-4 h-4" /></button>
        <button type="button" title="Numbered list" className={btn} onClick={() => prefixLines(i => `${i + 1}. `)}><ListOrdered className="w-4 h-4" /></button>
        <button type="button" title="Quote" className={btn} onClick={() => prefixLines('> ')}><Quote className="w-4 h-4" /></button>
        <button type="button" title="Code" className={btn} onClick={() => wrap('`', '`', 'code')}><Code className="w-4 h-4" /></button>
        <div className="flex-1" />
        <span className="text-xs text-slate-400 mr-2 dark:text-gray-500">{words} words</span>
        {tab('write', 'Write')}{tab('split', 'Split')}{tab('preview', 'Preview')}
      </div>
      <div className={`grid gap-0 ${showWrite && showPreview ? 'lg:grid-cols-2' : 'grid-cols-1'}`}>
        {showWrite && (
          <textarea ref={ref} value={value} onChange={e => onChange(e.target.value)}
                    onKeyDown={onKeyDown} rows={rows} spellCheck placeholder={placeholder}
                    className="w-full font-mono text-[13px] leading-6 px-3 py-2 bg-transparent
                               text-slate-800 dark:text-gray-100 outline-none resize-y" />
        )}
        {showPreview && (
          <div className={`mm-prose text-sm text-slate-700 dark:text-gray-300 px-4 py-3 overflow-y-auto
                           ${showWrite ? 'border-t lg:border-t-0 lg:border-l dark:border-gray-700' : ''}`}
               style={{ maxHeight: `${Math.max(rows * 1.5 + 1, 12)}rem` }}>
            {renderPreview
              ? <div dangerouslySetInnerHTML={{ __html: renderPreview(value) }} />
              : value.trim()
                ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{value}</ReactMarkdown>
                : <p className="text-slate-400 dark:text-gray-500">Nothing to preview yet.</p>}
          </div>
        )}
      </div>
    </div>
  );
}
