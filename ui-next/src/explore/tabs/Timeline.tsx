import { useCallback, useEffect, useState } from 'react';
import {
  ArticleCard, Banner, Button, Chip, Icon, IconButton, Panel, SegmentedControl, Select, Skeleton, Stack, Text, TextArea, TextField, TextLink,
} from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { api, errorText } from '../../shell';

/*
 * Timeline: dated developments ("mementos") per brand or topic, on /api/timeline as the old tab
 * (ui/src/components/newsfeed/TimelineTab.tsx). "Extract now" runs the AI over the last 14 days;
 * the scheduler does the same daily at 01:00 UTC.
 */

interface Scope {
  scope_type: 'topic' | 'brand';
  scope_id: string;
  label: string;
  event_count: number;
}

interface TimelineEvent {
  id: number;
  event_type: string;
  title: string;
  description: string | null;
  significance: 'low' | 'medium' | 'high' | 'critical';
  event_data: { key_developments?: string[] } & Record<string, unknown>;
  entities: string[];
  article_uris: string[];
  article_count: number;
  event_date: string;
  last_seen_date: string | null;
  occurrence_count: number;
}

interface Summary {
  label: string;
  state_doc: { summary: string; key_entities: string[]; current_trend: string | null; generated_at: string | null } | null;
  escalation_tier?: { label: string; triggered: string[]; window_days: number } | null;
  monthly: TimelineEvent[];
  weekly: TimelineEvent[];
  analyst_notes: TimelineEvent[];
  daily: TimelineEvent[];
}

// The trend values describe coverage volume; say so instead of echoing words like "escalating"
const TREND: Record<string, string> = { escalating: 'Coverage rising', 'de-escalating': 'Coverage falling', stable: 'Steady', emerging: 'New', mixed: 'Mixed' };
const TYPE: Record<string, string> = {
  new_development: 'Development', volume_spike: 'Coverage spike', sentiment_shift: 'Sentiment shift', source_shift: 'New sources',
  story_emergence: 'Syndicated story', risk_finding: 'Risk finding', alert: 'Alert', analyst_note: 'Analyst note', weekly_rollup: 'Weekly rollup', monthly_rollup: 'Monthly rollup',
};
const SIG_TONE: Record<string, 'error' | 'warning' | 'info' | 'muted'> = { critical: 'error', high: 'warning', medium: 'info', low: 'muted' };
const VIEWS = [
  { value: 'summary', label: 'Summary' }, { value: 'daily', label: 'Daily' }, { value: 'weekly', label: 'Weekly' }, { value: 'monthly', label: 'Monthly' },
];
const keyOf = (s: Scope) => `${s.scope_type}:${s.scope_id}`;

function EventCard({ e, onDelete }: { e: TimelineEvent; onDelete?: () => void }) {
  const links = (e.article_uris ?? []).filter((u) => u?.startsWith('http'));
  const devs = Array.isArray(e.event_data?.key_developments) ? e.event_data.key_developments : [];
  const hasDetails = !!e.description || devs.length > 0 || links.length > 0;
  return (
    <ArticleCard
      as="li"
      variant="row"
      headingLevel={4}
      meta={e.event_date}
      flag={<Chip size="sm" tone={SIG_TONE[e.significance] ?? 'info'}>{TYPE[e.event_type] ?? e.event_type.replace(/_/g, ' ')}</Chip>}
      title={e.title}
      leading={onDelete ? <IconButton icon={<Icon name="Trash" size="sm" />} label={`Delete note “${e.title}”`} onClick={onDelete} /> : undefined}
      tags={
        <>
          {e.occurrence_count > 1 && <Chip size="sm" tone="warning">Ongoing, seen {e.occurrence_count} times (last {e.last_seen_date})</Chip>}
          {e.article_count > 1 && <Chip size="sm" tone="muted">{e.article_count} articles</Chip>}
          {(e.entities ?? []).slice(0, 3).map((x) => <Chip key={x} size="sm" tone="neutral">{x}</Chip>)}
        </>
      }
      details={
        hasDetails ? (
          <Stack gap="sm">
            {e.description && <Text variant="description">{e.description}</Text>}
            {devs.length > 0 && (
              <Stack as="ul" gap="sm" label="Key developments">
                {devs.map((d, i) => <li key={i}><Text variant="caption">{d}</Text></li>)}
              </Stack>
            )}
            {links.slice(0, 5).map((u) => <TextLink key={u} href={u} external>{u}</TextLink>)}
          </Stack>
        ) : undefined
      }
    />
  );
}

function List({ items, empty, onDelete }: { items: TimelineEvent[]; empty: string; onDelete?: (e: TimelineEvent) => void }) {
  if (!items.length) return <Text>{empty}</Text>;
  return (
    <Stack as="ul" gap="sm" label="Mementos">
      {items.map((e) => <EventCard key={e.id} e={e} onDelete={onDelete ? () => onDelete(e) : undefined} />)}
    </Stack>
  );
}

export function Timeline({ notify, askConfirm }: { notify: (m: string) => void; askConfirm: (c: Confirm) => void }) {
  const [scopes, setScopes] = useState<Scope[] | null>(null);
  const [scope, setScope] = useState<Scope | null>(null);
  const [view, setView] = useState('summary');
  const [summary, setSummary] = useState<Summary | null>(null);
  const [events, setEvents] = useState<TimelineEvent[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);
  const [noteTitle, setNoteTitle] = useState('');
  const [noteBody, setNoteBody] = useState('');

  useEffect(() => {
    api<{ scopes?: Scope[] }>('/api/timeline/scopes').then(
      (r) => {
        const s = r.scopes ?? [];
        setScopes(s);
        // The scope with the most mementos first
        setScope([...s].sort((a, b) => (b.event_count || 0) - (a.event_count || 0))[0] ?? null);
      },
      (e: unknown) => {
        setScopes([]);
        setError(errorText(e));
      },
    );
  }, []);

  const load = useCallback(async (s: Scope, v: string) => {
    setLoading(true);
    setError(null);
    const p = new URLSearchParams({ scope_type: s.scope_type, scope_id: s.scope_id });
    try {
      if (v === 'summary') {
        setSummary(await api<Summary>(`/api/timeline/summary?${p}`));
        setEvents(null);
      } else {
        setEvents((await api<{ events?: TimelineEvent[] }>(`/api/timeline/events?${p}&granularity=${v}&include_stale=true&limit=100`)).events ?? []);
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    if (scope) void load(scope, view);
  }, [scope, view, load]);

  const extract = async () => {
    if (!scope) return;
    setBusy(true);
    try {
      await api('/api/timeline/generate', { method: 'POST', json: { scope_type: scope.scope_type, scope_id: scope.scope_id, days_back: 14 } });
      notify('Timeline extracted for the last 14 days');
      await load(scope, view);
    } catch (e) {
      notify(`Extraction failed: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const addNote = async () => {
    if (!scope) return;
    try {
      await api('/api/timeline/notes', { method: 'POST', json: { scope_type: scope.scope_type, scope_id: scope.scope_id, title: noteTitle.trim(), description: noteBody.trim() } });
      setNoteTitle('');
      setNoteBody('');
      setNoteOpen(false);
      notify('Note pinned');
      await load(scope, view);
    } catch (e) {
      notify(`Note not saved: ${errorText(e)}`);
    }
  };

  const deleteNote = (e: TimelineEvent) =>
    askConfirm({
      title: 'Delete this note?',
      message: `“${e.title}” leaves the timeline and stops feeding its summary.`,
      action: 'Delete note',
      onConfirm: () =>
        void api(`/api/timeline/notes/${e.id}`, { method: 'DELETE' }).then(
          () => scope && load(scope, view),
          (err: unknown) => notify(`Not deleted: ${errorText(err)}`),
        ),
    });

  if (!scopes) return <Skeleton variant="block" size="card" />;
  const brands = scopes.filter((s) => s.scope_type === 'brand');
  const topics = scopes.filter((s) => s.scope_type === 'topic');
  const option = (s: Scope) => ({ value: keyOf(s), label: `${s.label}${s.event_count ? ` (${s.event_count})` : ''}`, description: s.scope_type === 'brand' ? 'Brand' : 'Topic' });
  const trend = summary?.state_doc?.current_trend;

  return (
    <>
      <Panel
        title="Timeline"
        description="Dated developments for each brand and topic. A story that keeps coming back raises one memento’s count instead of repeating."
        headerAside={
          <Stack direction="row" gap="sm">
            <Select
              label="Brand or topic"
              hideLabel
              placeholder="Pick a brand or topic"
              options={[...brands, ...topics].map(option)}
              value={scope ? keyOf(scope) : undefined}
              onValueChange={(v) => {
                setScope(scopes.find((s) => keyOf(s) === v) ?? null);
                setView('summary');
              }}
            />
            <SegmentedControl label="Timeline view" options={VIEWS} value={view} onValueChange={setView} />
            <Button iconStart={<Icon name="Lightning" size="sm" />} disabled={!scope || busy} onClick={() => void extract()}>
              {busy ? 'Extracting…' : 'Extract now'}
            </Button>
          </Stack>
        }
      />
      {error && <Banner tone="error" title="The timeline didn’t load" description={error} />}
      {!scope ? <Text>No brands or topics have a timeline yet.</Text> : loading ? <Skeleton variant="block" size="card" /> : view !== 'summary' ? (
        <Panel title={`${VIEWS.find((v) => v.value === view)?.label} mementos`} headingLevel={3}>
          <List items={events ?? []} empty={`No ${view} mementos yet for ${scope.label}.`} />
        </Panel>
      ) : summary ? (
        <>
          {summary.state_doc && (
            <Panel
              title={`State of ${summary.label}`}
              description={summary.state_doc.generated_at ? `Written ${summary.state_doc.generated_at.slice(0, 16).replace('T', ' ')}` : undefined}
              headingLevel={3}
              headerAside={
                <Stack direction="row" gap="sm">
                  {trend && <Chip tone="info">{TREND[trend.toLowerCase()] ?? trend}</Chip>}
                  {summary.escalation_tier && <Chip tone="warning">{summary.escalation_tier.label}</Chip>}
                </Stack>
              }
            >
              <Stack gap="md">
                <Text variant="description">{summary.state_doc.summary}</Text>
                {summary.escalation_tier && !!summary.escalation_tier.triggered.length && (
                  <Text variant="caption">Status set by your rules, triggered by: {summary.escalation_tier.triggered.join('; ')}</Text>
                )}
                {!!summary.state_doc.key_entities?.length && (
                  <Stack as="ul" direction="row" gap="sm" label="Key entities">
                    {summary.state_doc.key_entities.slice(0, 10).map((e) => <li key={e}><Chip tone="neutral">{e}</Chip></li>)}
                  </Stack>
                )}
              </Stack>
            </Panel>
          )}
          {(summary.monthly.length > 0 || summary.weekly.length > 0) && (
            <Panel title="Rollups" headingLevel={3}>
              <List items={[...summary.monthly, ...summary.weekly]} empty="" />
            </Panel>
          )}
          <Panel
            title="Analyst notes"
            description="Pinned notes are permanent. They feed the summary above and what the agents know."
            headingLevel={3}
            headerAside={
              <Button variant="secondary" size="sm" iconStart={<Icon name="NotePencil" size="sm" />} onClick={() => setNoteOpen((o) => !o)}>
                {noteOpen ? 'Cancel' : 'Pin note'}
              </Button>
            }
          >
            <Stack gap="md">
              {noteOpen && (
                <Stack gap="sm">
                  <TextField label="Note title" value={noteTitle} onChange={setNoteTitle} maxLength={300} hint="At least 3 characters." />
                  <TextArea label="Detail (optional)" rows={2} value={noteBody} onChange={setNoteBody} />
                  <div><Button size="sm" disabled={noteTitle.trim().length < 3} onClick={() => void addNote()}>Save note</Button></div>
                </Stack>
              )}
              <List items={summary.analyst_notes} empty="No notes yet." onDelete={deleteNote} />
            </Stack>
          </Panel>
          <Panel title="Recent mementos" headingLevel={3}>
            <List items={summary.daily} empty="No mementos yet. The scheduler extracts daily at 01:00 UTC, or use “Extract now” to start with the last 14 days." />
          </Panel>
        </>
      ) : null}
    </>
  );
}
