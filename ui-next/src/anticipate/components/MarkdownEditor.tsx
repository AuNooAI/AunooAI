import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Dialog, DialogClose, EmptyState, Icon, SegmentedControl, SettingRow, Skeleton, Stack, Text, TextArea, TextField } from '@aunoo/ui';
import { api, errorText } from '../../shell';
import { Markdown } from '../../shell/Markdown';

interface Snapshot { value: string; start: number; end: number }
interface Hit { id: string; metadata: { title?: string; uri?: string; news_source?: string; publication_date?: string } }

/** Wraps the selection in `before`/`after`, or unwraps it when it already is. */
function wrap(s: Snapshot, before: string, after = before, placeholder = 'text'): Snapshot {
  const sel = s.value.slice(s.start, s.end) || placeholder;
  const pre = s.value.slice(0, s.start);
  const post = s.value.slice(s.end);
  if (pre.endsWith(before) && post.startsWith(after)) {
    return { value: pre.slice(0, -before.length) + sel + post.slice(after.length), start: s.start - before.length, end: s.start - before.length + sel.length };
  }
  return { value: pre + before + sel + after + post, start: s.start + before.length, end: s.start + before.length + sel.length };
}

/** Adds (or removes, when every line has it) a prefix on each selected line. */
function prefixLines(s: Snapshot, prefix: (i: number) => string, strip: RegExp): Snapshot {
  const lineStart = s.value.lastIndexOf('\n', s.start - 1) + 1;
  const nl = s.value.indexOf('\n', s.end);
  const lineEnd = nl < 0 ? s.value.length : nl;
  const lines = s.value.slice(lineStart, lineEnd).split('\n');
  const all = lines.every((l) => strip.test(l));
  const next = lines.map((l, i) => (all ? l.replace(strip, '') : prefix(i) + l.replace(strip, ''))).join('\n');
  return { value: s.value.slice(0, lineStart) + next + s.value.slice(lineEnd), start: lineStart, end: lineStart + next.length };
}

function insert(s: Snapshot, text: string): Snapshot {
  const value = s.value.slice(0, s.start) + text + s.value.slice(s.end);
  return { value, start: s.start + text.length, end: s.start + text.length };
}

const fmtDate = (d?: string) => (d ? new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '');

interface Props {
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Topic the article search looks in */
  topic: string;
}

/**
 * Markdown editor: a formatting toolbar with keyboard shortcuts (Ctrl+B, I, K, Z, Shift+Z), its own
 * undo history (the browser's is lost when the toolbar changes the text), a preview, and an
 * article search that inserts a cited link at the cursor.
 */
export function MarkdownEditor({ label, value, onChange, topic }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<'write' | 'preview'>('write');
  const past = useRef<Snapshot[]>([]);
  const future = useRef<Snapshot[]>([]);
  const lastPush = useRef(0);
  const [, force] = useState(0);
  const [pickOpen, setPickOpen] = useState(false);
  const pendingSel = useRef<{ start: number; end: number } | null>(null);

  const area = () => wrapRef.current?.querySelector('textarea') ?? null;
  const snap = (): Snapshot => {
    const el = area();
    return { value, start: el?.selectionStart ?? value.length, end: el?.selectionEnd ?? value.length };
  };
  const remember = (s: Snapshot) => {
    past.current.push(s);
    if (past.current.length > 200) past.current.shift();
    future.current = [];
    force((n) => n + 1);
  };
  const apply = useCallback(
    (next: Snapshot) => {
      pendingSel.current = { start: next.start, end: next.end };
      onChange(next.value);
    },
    [onChange],
  );
  // Restore the selection after React writes the new value
  useEffect(() => {
    const el = area();
    if (el && pendingSel.current) {
      el.focus();
      el.setSelectionRange(pendingSel.current.start, pendingSel.current.end);
      pendingSel.current = null;
    }
  });

  const edit = (fn: (s: Snapshot) => Snapshot) => {
    const s = snap();
    remember(s);
    lastPush.current = 0;
    apply(fn(s));
  };
  const undo = () => {
    const prev = past.current.pop();
    if (!prev) return;
    future.current.push(snap());
    apply(prev);
    force((n) => n + 1);
  };
  const redo = () => {
    const next = future.current.pop();
    if (!next) return;
    past.current.push(snap());
    apply(next);
    force((n) => n + 1);
  };
  // Typing: one undo step per pause of a second or more
  const type = (v: string) => {
    const now = Date.now();
    if (now - lastPush.current > 1000) remember(snap());
    lastPush.current = now;
    onChange(v);
  };

  const actions = {
    bold: () => edit((s) => wrap(s, '**')),
    italic: () => edit((s) => wrap(s, '_')),
    h2: () => edit((s) => prefixLines(s, () => '## ', /^#{1,6}\s+/)),
    h3: () => edit((s) => prefixLines(s, () => '### ', /^#{1,6}\s+/)),
    bullets: () => edit((s) => prefixLines(s, () => '- ', /^\s*[-*]\s+/)),
    numbers: () => edit((s) => prefixLines(s, (i) => `${i + 1}. `, /^\s*\d+\.\s+/)),
    quote: () => edit((s) => prefixLines(s, () => '> ', /^>\s?/)),
    link: () => edit((s) => wrap(s, '[', '](https://)', 'link text')),
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
    const k = e.key.toLowerCase();
    const run = k === 'b' ? actions.bold : k === 'i' ? actions.italic : k === 'k' ? actions.link : k === 'z' ? (e.shiftKey ? redo : undo) : k === 'y' ? redo : null;
    if (run) {
      e.preventDefault();
      run();
    }
  };

  const openPicker = () => {
    const s = snap();
    pendingSel.current = null;
    pickSel.current = { start: s.start, end: s.end };
    setPickOpen(true);
  };
  const pickSel = useRef<{ start: number; end: number }>({ start: value.length, end: value.length });
  const insertArticle = (h: Hit) => {
    const m = h.metadata;
    const meta = [m.news_source, fmtDate(m.publication_date)].filter(Boolean).join(', ');
    const line = `[${(m.title ?? m.uri ?? h.id).replace(/[[\]]/g, '')}](${m.uri ?? h.id})${meta ? ` (${meta})` : ''}`;
    const s = { value, ...pickSel.current };
    // On its own line, so it doesn't run into the text before it
    const lead = s.start > 0 && value[s.start - 1] !== '\n' ? '\n' : '';
    remember(s);
    apply(insert(s, lead + line));
    setPickOpen(false);
  };

  const tools: { id: keyof typeof actions; label: string; hint: string }[] = [
    { id: 'bold', label: 'Bold', hint: 'Ctrl+B' },
    { id: 'italic', label: 'Italic', hint: 'Ctrl+I' },
    { id: 'h2', label: 'Heading', hint: '' },
    { id: 'h3', label: 'Subheading', hint: '' },
    { id: 'bullets', label: 'List', hint: '' },
    { id: 'numbers', label: 'Numbered', hint: '' },
    { id: 'quote', label: 'Quote', hint: '' },
    { id: 'link', label: 'Link', hint: 'Ctrl+K' },
  ];

  return (
    <Stack gap="sm">
      <Stack direction="row" justify="between" gap="sm">
        <Stack direction="row" gap="sm" label="Formatting">
          {mode === 'write' && (
            <>
              {tools.map((t) => (
                <Button key={t.id} variant="ghost" size="sm" onClick={actions[t.id]} aria-label={t.hint ? `${t.label} (${t.hint})` : t.label}>{t.label}</Button>
              ))}
              <Button variant="ghost" size="sm" iconStart={<Icon name="Newspaper" size="sm" />} onClick={openPicker}>Insert article</Button>
              <Button variant="ghost" size="sm" disabled={!past.current.length} onClick={undo} aria-label="Undo (Ctrl+Z)">Undo</Button>
              <Button variant="ghost" size="sm" disabled={!future.current.length} onClick={redo} aria-label="Redo (Ctrl+Shift+Z)">Redo</Button>
            </>
          )}
        </Stack>
        <SegmentedControl label="Editor view" options={[{ value: 'write', label: 'Write' }, { value: 'preview', label: 'Preview' }]} value={mode} onValueChange={(v) => setMode(v as 'write' | 'preview')} />
      </Stack>
      {mode === 'write' ? (
        // Unstyled wrapper: gives the toolbar the textarea's selection and catches the shortcuts
        <div ref={wrapRef} onKeyDown={onKeyDown}>
          <TextArea label={label} rows={24} mono value={value} onChange={type} />
        </div>
      ) : (
        <Markdown text={value} />
      )}
      <ArticlePicker open={pickOpen} onOpenChange={setPickOpen} topic={topic} onPick={insertArticle} />
    </Stack>
  );
}

function ArticlePicker({ open, onOpenChange, topic, onPick }: { open: boolean; onOpenChange: (o: boolean) => void; topic: string; onPick: (h: Hit) => void }) {
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const search = async () => {
    if (!q.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ results: Hit[] }>(`/api/vector-search?q=${encodeURIComponent(q.trim())}&top_k=15&topic=${encodeURIComponent(topic)}`);
      setHits(r.results ?? []);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Insert article"
      description={`Search this topic’s articles (${topic}) and insert a link at the cursor.`}
      footer={<DialogClose><Button variant="secondary" size="lg">Close</Button></DialogClose>}
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          {/* Enter searches */}
          <div onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void search(); } }}>
            <TextField label="Search" placeholder="e.g. agentic SOC funding" value={q} onChange={setQ} />
          </div>
          <Button busy={busy} disabled={!q.trim()} onClick={() => void search()}>Search</Button>
        </Stack>
        {error && <Text variant="hint" tone="error">{error}</Text>}
        {busy && !hits ? (
          <Skeleton lines={3} />
        ) : hits && hits.length === 0 ? (
          <EmptyState icon="MagnifyingGlass">No articles matched.</EmptyState>
        ) : (
          hits && (
            <Stack as="ul" gap="sm" label="Search results">
              {hits.map((h) => (
                <li key={h.id}>
                  <SettingRow
                    title={h.metadata.title ?? h.id}
                    description={[h.metadata.news_source, fmtDate(h.metadata.publication_date)].filter(Boolean).join(' · ') || undefined}
                    actions={<Button variant="secondary" size="sm" onClick={() => onPick(h)}>Insert</Button>}
                  />
                </li>
              ))}
            </Stack>
          )
        )}
      </Stack>
    </Dialog>
  );
}
