import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Banner, Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, EmptyState, Eyebrow, Grid, Icon, LineItems, Panel, Select, Sheet,
  Skeleton, Stack, Switch, Text, TextArea, TextLink,
} from '@aunoo/ui';
import type { Confirm, Notify } from '@aunoo/shell';
import { ConfirmDialog } from '@aunoo/shell';
import { Disclosure } from '../../anticipate/components/Disclosure';
import { api, errorText } from '../api';
import { Markdown } from '../Markdown';
import {
  ALL_TOPICS, createSession, deleteSession, listSessions, loadMessages, streamChat, streamResearch, summarise,
  type Insights, type ModelInfo, type ResearchMode, type Session,
} from './api';
import { ChartView } from './ChartView';
import { parseAnswer, plainText } from './markers';

/** A question to open with, from `auspex:open` events or `?auspex_query=` (see AppShell). */
export interface AuspexRequest { query: string; autoSend?: boolean; topic?: string; nonce: number }

export interface AuspexPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  notify: Notify;
  request?: AuspexRequest | null;
}

interface Msg { id: string; role: 'user' | 'assistant'; content: string; model?: string; streaming?: boolean; status?: string; stopped?: boolean; failed?: string }
interface Settings { topic: string; model: string; cited: number; sampling: string; research: 'off' | ResearchMode; charts: boolean; searchArticles: boolean }

const KEY = 'aunoo.auspex.settings';
const DEFAULTS: Settings = { topic: ALL_TOPICS, model: '', cited: 25, sampling: 'auto', research: 'off', charts: false, searchArticles: true };
const loadSettings = (): Settings => {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) ?? '{}') };
  } catch {
    return DEFAULTS;
  }
};
// The server's presets (app/services/sampling/registry.py); "auto" sends none
const SAMPLING = [
  { value: 'auto', label: 'Automatic' },
  { value: 'all_topics_default', label: 'Recent and diverse' },
  { value: 'quality_first', label: 'Quality first' },
  { value: 'latest', label: 'Latest only' },
  { value: 'diverse', label: 'Most diverse' },
  { value: 'balanced_topics', label: 'Balanced across topics' },
];
const CITED = [10, 25, 50, 100].map((n) => ({ value: String(n), label: `${n} articles` }));
const RESEARCH = [
  { value: 'off', label: 'Off: chat' },
  { value: 'internal', label: 'Our articles' },
  { value: 'hybrid', label: 'Our articles and the web' },
  { value: 'external', label: 'The web' },
];
let seq = 0;
const nextId = () => `m${++seq}`;
const fmtWhen = (s?: string) => (s ? new Date(s).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '');

function saveFile(text: string, name: string) {
  const href = URL.createObjectURL(new Blob([text], { type: 'text/markdown' }));
  const a = document.createElement('a');
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(href), 1000);
}

/* ── one message ───────────────────────────────────────────────────── */

const Charts = memo(function Charts({ raw }: { raw: string }) {
  const { charts, chartErrors } = parseAnswer(raw);
  return (
    <>
      {charts.map((c, i) => <ChartView key={i} spec={c} />)}
      {chartErrors.map((e, i) => <Text key={`e${i}`} variant="hint">{`A chart couldn’t be drawn: ${e}`}</Text>)}
    </>
  );
});

function Message({ m, notify }: { m: Msg; notify: Notify }) {
  const parsed = useMemo(() => parseAnswer(m.content, m.streaming), [m.content, m.streaming]);
  // Charts arrive whole before the prose, so they only change when a new marker completes
  const chartKey = (m.content.match(/<!-- CHART_(DATA|ERROR):[\s\S]*?:END_CHART -->/g) ?? []).join('');
  const stats = parsed.stats;
  if (m.role === 'user') {
    return (
      <Stack gap="sm">
        <Eyebrow>You</Eyebrow>
        <Text variant="description">{m.content}</Text>
      </Stack>
    );
  }
  const sources = (stats?.top_sources ?? []).slice(0, 12);
  const sentiment = stats?.sentiment_breakdown ?? {};
  return (
    <Stack gap="sm">
      <Stack direction="row" justify="between" gap="sm">
        <Eyebrow>{`Auspex${m.model ? ` · ${m.model}` : ''}`}</Eyebrow>
        {!m.streaming && parsed.text && (
          <Button variant="ghost" size="sm" iconStart={<Icon name="Copy" size="sm" />} onClick={() => navigator.clipboard.writeText(parsed.text).then(() => notify('Copied'), () => notify('Couldn’t copy'))}>Copy</Button>
        )}
      </Stack>
      {m.status && m.streaming && <Text variant="hint">{m.status}</Text>}
      {chartKey && <Charts raw={chartKey} />}
      {parsed.text ? <Markdown text={parsed.text} /> : m.streaming ? <Skeleton lines={2} /> : null}
      {m.stopped && <Text variant="hint">Stopped.</Text>}
      {m.failed && <Banner tone="error" icon="WarningCircle" title="The answer didn’t finish" description={m.failed} />}
      {stats && !m.streaming && (
        <Collapsible>
          <Stack gap="sm">
            <Stack direction="row">
              <CollapsibleTrigger variant="ghost" size="sm">{`Based on ${stats.total_articles ?? 0} articles`}</CollapsibleTrigger>
            </Stack>
            <CollapsibleContent>
              <Stack gap="sm">
                <LineItems
                  label="Article sentiment"
                  items={Object.entries(sentiment).filter(([, n]) => n > 0).map(([k, n]) => ({ id: k, label: k[0].toUpperCase() + k.slice(1), amount: String(n) }))}
                />
                {sources.length > 0 && (
                  <Stack as="ul" gap="sm" label="Top sources">
                    {sources.map((s) => (
                      <li key={s.name}>
                        <Text variant="caption">
                          {s.sample_url ? <TextLink href={s.sample_url} external>{s.name}</TextLink> : s.name}
                          {` · ${s.count}`}
                        </Text>
                      </li>
                    ))}
                  </Stack>
                )}
              </Stack>
            </CollapsibleContent>
          </Stack>
        </Collapsible>
      )}
    </Stack>
  );
}

/* ── the panel ─────────────────────────────────────────────────────── */

/**
 * Auspex, the research assistant: chat about a topic's articles, or run deep research, in a side
 * panel. Conversations are stored per topic on the server.
 */
export default function AuspexPanel({ open, onOpenChange, notify, request }: AuspexPanelProps) {
  const [s, setS] = useState<Settings>(loadSettings);
  const set = (p: Partial<Settings>) =>
    setS((x) => {
      const n = { ...x, ...p };
      try {
        localStorage.setItem(KEY, JSON.stringify(n));
      } catch {
        // per visit only
      }
      return n;
    });
  const [topics, setTopics] = useState<string[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [chatId, setChatIdState] = useState<number | null>(null);
  // send() reads the conversation from here, so a send queued during a topic switch can't reach the old chat
  const chatRef = useRef<number | null>(null);
  const setChatId = (id: number | null) => {
    chatRef.current = id;
    setChatIdState(id);
  };
  const [messages, setMessages] = useState<Msg[]>([]);
  const [loadingChat, setLoadingChat] = useState(false);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [summarising, setSummarising] = useState(false);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const abort = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement>(null);
  // A question to send once the requested topic is in place
  const pendingSend = useRef<{ query: string; topic: string } | null>(null);

  // Topics and models, once
  useEffect(() => {
    void Promise.all([
      api<{ name: string }[]>('/api/topics').catch(() => []),
      api<ModelInfo[]>('/api/trend-convergence/models').catch(() => []),
    ]).then(([t, m]) => {
      setTopics(t.map((x) => x.name).filter(Boolean));
      setModels(m);
      setS((x) => (x.model && m.some((y) => y.id === x.model) ? x : { ...x, model: m[0]?.id ?? '' }));
    });
  }, []);

  const refreshSessions = useCallback(() => listSessions(s.topic).then(setSessions, () => setSessions([])), [s.topic]);
  // A new topic starts a new conversation
  useEffect(() => {
    setChatId(null);
    setMessages([]);
    setInsights(null);
    void refreshSessions();
  }, [refreshSessions]);

  useEffect(() => end.current?.scrollIntoView({ block: 'end' }), [messages]);

  const openSession = async (id: number) => {
    abort.current?.abort();
    setChatId(id);
    setInsights(null);
    setLoadingChat(true);
    try {
      const ms = await loadMessages(id);
      setMessages(ms.map((m) => ({ id: `s${m.id}`, role: m.role, content: m.content, model: m.model_used })));
    } catch (e) {
      notify(`Couldn’t open it: ${errorText(e)}`, 'WarningCircle');
    } finally {
      setLoadingChat(false);
    }
  };
  const newChat = () => {
    abort.current?.abort();
    setChatId(null);
    setMessages([]);
    setInsights(null);
  };

  const patchMsg = (id: string, fn: (m: Msg) => Msg) => setMessages((ms) => ms.map((m) => (m.id === id ? fn(m) : m)));

  const send = async (text?: string) => {
    const message = (text ?? input).trim();
    if (!message || busy || !s.model) return;
    setInput('');
    setBusy(true);
    const ctrl = new AbortController();
    abort.current = ctrl;
    const aid = nextId();
    setMessages((ms) => [...ms, { id: nextId(), role: 'user', content: message }, { id: aid, role: 'assistant', content: '', streaming: true, model: s.research === 'off' ? models.find((m) => m.id === s.model)?.name : 'deep research' }]);
    try {
      // Sessions are created on the first message, so "New chat" doesn't leave empty ones behind
      let id = chatRef.current;
      if (id === null) {
        id = (await createSession(s.topic)).chat_id;
        setChatId(id);
      }
      if (s.research === 'off') {
        for await (const chunk of streamChat(
          { chatId: id, message, model: s.model, limit: Math.max(50, s.cited * 2), detailLimit: s.cited, samplingStrategy: s.sampling === 'auto' ? null : s.sampling, includeCharts: s.charts, searchArticles: s.searchArticles },
          ctrl.signal,
        )) patchMsg(aid, (m) => ({ ...m, content: m.content + chunk }));
      } else {
        for await (const u of streamResearch({ chatId: id, message, topic: s.topic, mode: s.research, includeCharts: s.charts }, ctrl.signal)) {
          if (u.report !== undefined) patchMsg(aid, (m) => ({ ...m, content: u.report!, status: undefined }));
          else if (u.text) patchMsg(aid, (m) => ({ ...m, content: m.content + u.text }));
          else if (u.detail) patchMsg(aid, (m) => ({ ...m, status: u.detail }));
        }
      }
      patchMsg(aid, (m) => ({ ...m, streaming: false }));
    } catch (e) {
      if (ctrl.signal.aborted) patchMsg(aid, (m) => ({ ...m, streaming: false, stopped: true }));
      else patchMsg(aid, (m) => ({ ...m, streaming: false, failed: errorText(e) }));
    } finally {
      setBusy(false);
      abort.current = null;
      void refreshSessions();
    }
  };

  // Opened with a question from elsewhere: switch topic if asked, then fill (or send) it
  useEffect(() => {
    if (!request) return;
    const topic = request.topic && (request.topic === 'All' ? ALL_TOPICS : topics.find((t) => t.toLowerCase() === request.topic!.toLowerCase()));
    const target = topic || s.topic;
    if (target !== s.topic) set({ topic: target });
    if (request.autoSend) pendingSend.current = { query: request.query, topic: target };
    else setInput(request.query);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request?.nonce, topics.length]);
  // Send once the topic switch has settled and a model is known
  useEffect(() => {
    const p = pendingSend.current;
    if (p && p.topic === s.topic && s.model && !busy) {
      pendingSend.current = null;
      void send(p.query);
    }
  });

  const removeChat = () => {
    if (chatId === null) return;
    const id = chatId;
    setConfirm({
      title: 'Delete this conversation?',
      message: 'It will be deleted for good.',
      action: 'Delete',
      onConfirm: async () => {
        try {
          await deleteSession(id);
          newChat();
          await refreshSessions();
          notify('Conversation deleted', 'Trash');
        } catch (e) {
          notify(`Not deleted: ${errorText(e)}`, 'WarningCircle');
        }
      },
    });
  };
  const clearAll = () =>
    setConfirm({
      title: `Delete all ${sessions.length} conversations?`,
      message: `Every conversation under ${s.topic === ALL_TOPICS ? 'All topics' : s.topic} will be deleted for good.`,
      action: 'Delete all',
      onConfirm: async () => {
        const results = await Promise.allSettled(sessions.map((x) => deleteSession(x.id)));
        const failed = results.filter((r) => r.status === 'rejected').length;
        newChat();
        await refreshSessions();
        notify(failed ? `${failed} couldn’t be deleted` : 'All conversations deleted', failed ? 'WarningCircle' : 'Trash');
      },
    });

  const exportChat = () => {
    const topic = s.topic === ALL_TOPICS ? 'All topics' : s.topic;
    const body = messages.map((m) => `## ${m.role === 'user' ? 'You' : 'Auspex'}\n\n${m.role === 'user' ? m.content : plainText(m.content)}`).join('\n\n');
    saveFile(`# Auspex conversation\n\nTopic: ${topic}\nExported: ${new Date().toLocaleString('en-GB')}\n\n${body}\n`, `auspex-${new Date().toISOString().slice(0, 10)}.md`);
  };
  const runSummary = async () => {
    if (chatId === null) return;
    setSummarising(true);
    try {
      const r = await summarise(chatId);
      if (!r.insights) notify(r.message ?? 'Not enough conversation to summarise yet');
      setInsights(r.insights);
    } catch (e) {
      notify(`No summary: ${errorText(e)}`, 'WarningCircle');
    } finally {
      setSummarising(false);
    }
  };

  const topicOptions = [{ value: ALL_TOPICS, label: 'All topics' }, ...topics.map((t) => ({ value: t, label: t }))];
  const NEW = 'new';
  const sessionOptions = [
    { value: NEW, label: 'New conversation' },
    ...sessions.map((x) => ({ value: String(x.id), label: `${x.title || `Chat ${x.id}`} · ${fmtWhen(x.updated_at ?? x.created_at)}` })),
  ];
  const answered = messages.filter((m) => m.role === 'assistant' && !m.streaming && m.content).length;

  return (
    <>
      <Sheet
        open={open}
        onOpenChange={onOpenChange}
        size="lg"
        title="Auspex"
        description="Ask about your topics. Answers cite the articles they draw on."
        meta={
          <Grid columns={2} gap="sm">
            <Select label="Topic" fullWidth options={topicOptions} value={s.topic} onValueChange={(topic) => set({ topic })} />
            <Select label="Model" fullWidth options={models.map((m) => ({ value: m.id, label: m.name }))} value={s.model} onValueChange={(model) => set({ model })} />
          </Grid>
        }
      >
        <Stack gap="lg">
          <Stack gap="sm">
            <Select label="Conversation" fullWidth options={sessionOptions} value={chatId === null ? NEW : String(chatId)} onValueChange={(v) => (v === NEW ? newChat() : void openSession(Number(v)))} />
            <Stack direction="row" gap="sm">
              <Button variant="ghost" size="sm" iconStart={<Icon name="Plus" size="sm" />} disabled={busy} onClick={newChat}>New</Button>
              <Button variant="ghost" size="sm" iconStart={<Icon name="Sparkle" size="sm" />} disabled={chatId === null || answered === 0 || busy} busy={summarising} onClick={() => void runSummary()}>Summarise</Button>
              <Button variant="ghost" size="sm" iconStart={<Icon name="DownloadSimple" size="sm" />} disabled={!messages.length} onClick={exportChat}>Export</Button>
              <Button variant="ghost" size="sm" iconStart={<Icon name="Trash" size="sm" />} disabled={chatId === null || busy} onClick={removeChat}>Delete</Button>
              {sessions.length > 1 && <Button variant="ghost" size="sm" disabled={busy} onClick={clearAll}>Delete all</Button>}
            </Stack>
          </Stack>

          <Collapsible>
            <Stack gap="sm">
              <Stack direction="row">
                <CollapsibleTrigger variant="ghost" size="sm">Settings</CollapsibleTrigger>
              </Stack>
              <CollapsibleContent>
                <Stack gap="md">
                  <Select label="Deep research" fullWidth options={RESEARCH} value={s.research} onValueChange={(v) => set({ research: v as Settings['research'] })} hint="Runs a multi-step research report instead of a chat answer. The web options search outside our article store." />
                  {s.research === 'off' && (
                    <Grid columns={2} stackAt="small" gap="sm">
                      <Select label="Articles cited" fullWidth options={CITED} value={String(s.cited)} onValueChange={(v) => set({ cited: Number(v) })} hint="Auspex searches at least twice as many." />
                      <Select label="Article selection" fullWidth options={SAMPLING} value={s.sampling} onValueChange={(sampling) => set({ sampling })} />
                    </Grid>
                  )}
                  <Switch label="Charts" description="Ask for a chart in your message (e.g. “sentiment over time”) and it appears under the answer." checked={s.charts} onCheckedChange={(charts) => set({ charts })} />
                  {s.research === 'off' && <Switch label="Search our articles" description="Off: Auspex answers from the conversation alone." checked={s.searchArticles} onCheckedChange={(searchArticles) => set({ searchArticles })} />}
                </Stack>
              </CollapsibleContent>
            </Stack>
          </Collapsible>

          {insights && (
            <Panel
              title="Summary"
              headerAside={
                <Button variant="ghost" size="sm" iconStart={<Icon name="DownloadSimple" size="sm" />} onClick={() => saveFile(
                  `# Auspex summary\n\n## Key themes\n${(insights.key_themes ?? []).map((t) => `- ${t}`).join('\n')}\n\n## Findings\n${(insights.main_findings ?? []).map((t) => `- ${t}`).join('\n')}\n\n## Sentiment\n${insights.sentiment_overview ?? ''}\n\n## Quotes\n${(insights.notable_quotes ?? []).map((t) => `> ${t}`).join('\n\n')}\n`,
                  `auspex-summary-${new Date().toISOString().slice(0, 10)}.md`,
                )}>Export</Button>
              }
            >
              <Stack gap="sm">
                {(insights.key_themes ?? []).length > 0 && <Stack direction="row" gap="sm">{insights.key_themes!.map((t) => <Chip key={t} size="sm" tone="accent">{t}</Chip>)}</Stack>}
                {(insights.main_findings ?? []).slice(0, 4).map((f, i) => <Text key={i}>{`• ${f}`}</Text>)}
                {insights.sentiment_overview && <Text variant="hint">{insights.sentiment_overview}</Text>}
                {(insights.notable_quotes ?? []).slice(0, 3).map((q, i) => <Text key={`q${i}`} variant="caption">{`“${q}”`}</Text>)}
              </Stack>
            </Panel>
          )}

          {loadingChat ? (
            <Skeleton lines={5} />
          ) : messages.length === 0 ? (
            <EmptyState icon="Robot" title="Ask Auspex">
              {`Ask about ${s.topic === ALL_TOPICS ? 'any of your topics' : s.topic}: what changed this month, who the key players are, where coverage disagrees. Switch on deep research in Settings for a full report.`}
            </EmptyState>
          ) : (
            <Stack gap="lg">
              {messages.map((m) => <Message key={m.id} m={m} notify={notify} />)}
            </Stack>
          )}
          {/* The composer follows the conversation: the panel footer can't stretch a text box */}
          <Stack gap="sm">
            {/* Unstyled wrapper: Enter sends, Shift+Enter adds a line */}
            <div onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); } }}>
              <TextArea
                label={s.research === 'off' ? 'Message' : 'Research question'}
                hideLabel
                rows={3}
                placeholder={s.research === 'off' ? 'Ask about this topic…' : 'What should the deep research answer?'}
                value={input}
                onChange={setInput}
              />
            </div>
            <Stack direction="row" justify="between" gap="sm">
              <Text variant="caption">{s.research === 'off' ? `Cites up to ${s.cited} articles · Enter to send` : 'Deep research takes a few minutes'}</Text>
              {busy ? (
                <Button variant="secondary" iconStart={<Icon name="Pause" size="sm" />} onClick={() => abort.current?.abort()}>Stop</Button>
              ) : (
                <Button iconStart={<Icon name="ArrowUp" size="sm" />} disabled={!input.trim() || !s.model} onClick={() => void send()}>{s.research === 'off' ? 'Send' : 'Research'}</Button>
              )}
            </Stack>
          </Stack>
          {/* Unstyled sentinel: new messages scroll it into view */}
          <div ref={end} />
          <Disclosure dashboard="Auspex" purpose="To answer questions about collected articles and write research reports" model={models.find((m) => m.id === s.model)?.name} />
        </Stack>
      </Sheet>
      <ConfirmDialog confirm={confirm} onClose={() => setConfirm(null)} />
    </>
  );
}
