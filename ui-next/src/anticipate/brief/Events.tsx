import { useCallback, useEffect, useState } from 'react';
import { Banner, Button, Checkbox, Chip, Dialog, DialogClose, Grid, Icon, Panel, Select, Skeleton, Stack, Table, Text, TextArea, TextField } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { api, errorText } from '../../shell';
import { editor, type BriefApi, type BriefEvent } from './model';
import type { Regen as RegenT } from './sections';

type Rel = { scenario: string; direction: string };
const relOf = (raw: BriefEvent['scenario_relevance']): Rel[] =>
  (raw ?? []).map((r) => (typeof r === 'string' ? { scenario: r, direction: 'neutral' } : { scenario: r.scenario, direction: r.direction || 'neutral' })).filter((r) => r.scenario);
const NEXT_DIR: Record<string, string> = { confirms: 'counters', counters: 'neutral', neutral: 'confirms' };
const DIR_TONE: Record<string, 'success' | 'error' | 'muted'> = { confirms: 'success', counters: 'error', neutral: 'muted' };
const DIR_WORD: Record<string, string> = { confirms: 'Confirms', counters: 'Counters', neutral: 'Neutral' };

interface Form { topic: string; actor: string; action: string; subject: string; event_date: string; magnitude_value: string; magnitude_unit: string; source_urls: string }
const toForm = (e: Partial<BriefEvent>, topic: string): Form => ({
  topic: e.topic ?? topic, actor: e.actor ?? '', action: e.action ?? '', subject: e.subject ?? '', event_date: e.event_date ?? new Date().toISOString().slice(0, 10),
  magnitude_value: e.magnitude_value != null ? String(e.magnitude_value) : '', magnitude_unit: e.magnitude_unit ?? '', source_urls: (e.source_urls ?? []).join('\n'),
});
const fromForm = (f: Form) => ({
  actor: f.actor.trim(), action: f.action.trim(), subject: f.subject.trim(), event_date: f.event_date || null,
  magnitude_value: f.magnitude_value.trim() ? Number(f.magnitude_value) : null, magnitude_unit: f.magnitude_unit.trim() || null,
  source_urls: f.source_urls.split('\n').map((s) => s.trim()).filter(Boolean),
});

/** Curate the extracted events: what goes in the deck, signal direction, edits, manual additions. */
export function Events({ b, regen, notify, askConfirm }: { b: BriefApi; regen: RegenT; notify: (m: string) => void; askConfirm: (c: Confirm) => void }) {
  const topics = b.brief!.per_topic.map((t) => t.topic);
  const ALL = 'all';
  const [filter, setFilter] = useState(ALL);
  const [events, setEvents] = useState<BriefEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<{ id: number | null; f: Form } | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api<{ events: BriefEvent[] }>(`${b.base}/events${filter !== ALL ? `?topic=${encodeURIComponent(filter)}` : ''}`);
      setEvents(r.events ?? []);
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, [b.base, filter]);
  useEffect(() => void load(), [load]);

  const patch = async (id: number, fields: Partial<BriefEvent> | Record<string, unknown>, done?: string) => {
    try {
      await api(`/api/forecast/brief/events/${id}`, { method: 'PATCH', json: { ...fields, edited_by: editor() } });
      await load();
      if (done) notify(done);
    } catch (e) {
      notify(`Not saved: ${errorText(e)}`);
    }
  };
  const remove = (ev: BriefEvent) =>
    askConfirm({
      title: 'Delete this event?',
      message: `“${ev.actor} ${ev.action} ${ev.subject}” will be deleted.`,
      action: 'Delete',
      onConfirm: async () => {
        try {
          await api(`/api/forecast/brief/events/${ev.id}`, { method: 'DELETE' });
          await load();
          notify('Event deleted');
        } catch (e) {
          notify(`Not deleted: ${errorText(e)}`);
        }
      },
    });
  const submit = async () => {
    if (!form) return;
    setSaving(true);
    try {
      if (form.id === null) {
        await api(`${b.base}/events`, { method: 'POST', json: { topic: form.f.topic, ...fromForm(form.f), confidence: 1, requires_review: false, edited_by: editor() } });
        notify('Event added');
      } else {
        await api(`/api/forecast/brief/events/${form.id}`, { method: 'PATCH', json: { ...fromForm(form.f), edited_by: editor() } });
        notify('Event saved');
      }
      setForm(null);
      await load();
    } catch (e) {
      notify(`Not saved: ${errorText(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const cycle = (ev: BriefEvent, i: number) => {
    const rel = relOf(ev.scenario_relevance);
    rel[i] = { ...rel[i], direction: NEXT_DIR[rel[i].direction] ?? 'confirms' };
    void patch(ev.id, { scenario_relevance: rel });
  };

  const table = (rows: BriefEvent[], caption: string, review: boolean) => (
    <Table
      caption={caption}
      hideCaption
      rowKey={(e) => String(e.id)}
      rows={rows}
      columns={[
        { key: 'deck', header: 'In deck', render: (e) => <Checkbox label={`Include “${e.subject}” in the deck`} hideLabel checked={Boolean(e.include_in_deck)} onCheckedChange={(c) => void patch(e.id, { include_in_deck: c })} /> },
        { key: 'event', header: 'Event', rowHeader: true, wrap: true, render: (e) => <Stack gap="sm"><Text>{`${e.actor} ${e.action} ${e.subject}`}</Text><Text variant="caption">{[e.topic, e.event_date, e.magnitude_value != null ? `${e.magnitude_value} ${e.magnitude_unit ?? ''}`.trim() : null, e.origin === 'manual' ? 'added by hand' : e.confidence != null ? `confidence ${e.confidence.toFixed(2)}` : null].filter(Boolean).join(' · ')}</Text></Stack> },
        {
          key: 'signal', header: 'Signal direction', wrap: true,
          render: (e) => {
            const rel = relOf(e.scenario_relevance);
            return rel.length === 0 ? <Text variant="caption">—</Text> : (
              <Stack direction="row" gap="sm">
                {rel.map((r, i) => <Chip key={i} size="sm" tone={DIR_TONE[r.direction] ?? 'muted'} onClick={() => cycle(e, i)} label={`${r.scenario}: ${DIR_WORD[r.direction] ?? r.direction}. Click to change.`}>{`${DIR_WORD[r.direction] ?? r.direction}: ${r.scenario}`}</Chip>)}
              </Stack>
            );
          },
        },
        {
          key: 'act', header: <span className="visually-hidden">Actions</span>, align: 'end',
          render: (e) => (
            <Stack direction="row" gap="sm">
              {review && <Button size="sm" variant="secondary" onClick={() => void patch(e.id, { requires_review: false }, 'Marked as reviewed')}>Reviewed</Button>}
              <Button size="sm" variant="ghost" iconStart={<Icon name="PencilSimple" size="sm" />} onClick={() => setForm({ id: e.id, f: toForm(e, e.topic) })}>Edit</Button>
              <Button size="sm" variant="ghost" iconStart={<Icon name="Trash" size="sm" />} onClick={() => remove(e)}>Delete</Button>
            </Stack>
          ),
        },
      ]}
    />
  );

  const review = (events ?? []).filter((e) => e.requires_review);
  const ready = (events ?? []).filter((e) => !e.requires_review);
  return (
    <Stack gap="lg">
      <Stack direction="row" justify="between" gap="sm">
        <Select label="Topic" options={[{ value: ALL, label: 'All topics' }, ...topics.map((t) => ({ value: t, label: t }))]} value={filter} onValueChange={setFilter} />
        <Stack direction="row" gap="sm">
          <Button variant="ghost" size="sm" iconStart={<Icon name="ArrowsClockwise" size="sm" />} busy={regen.is('events')} disabled={Boolean(regen.running) && !regen.is('events')} onClick={() => void regen.start('events')}>Re-extract events</Button>
          <Button size="sm" iconStart={<Icon name="Plus" size="sm" />} disabled={!topics.length} onClick={() => setForm({ id: null, f: toForm({}, filter !== ALL ? filter : topics[0] || '') })}>Add event</Button>
        </Stack>
      </Stack>
      {error && <Banner tone="error" icon="WarningCircle" title="Couldn’t load events" description={error} />}
      {!events ? (
        <Skeleton lines={4} />
      ) : (
        <>
          {review.length > 0 && <Panel title={`Needs review (${review.length})`} description="Low-confidence extractions. Check them, then mark them reviewed.">{table(review, 'Events to review', true)}</Panel>}
          <Panel title={`Ready for the deck (${ready.length})`}>
            {ready.length === 0 ? <Text variant="hint">No events for this period yet. Add one, or re-extract.</Text> : table(ready, 'Events ready for the deck', false)}
          </Panel>
        </>
      )}
      <Dialog
        open={form !== null}
        onOpenChange={(o) => !o && setForm(null)}
        title={form?.id === null ? 'Add event' : 'Edit event'}
        footer={
          <>
            <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
            <Button size="lg" busy={saving} disabled={!form || !form.f.actor.trim() || !form.f.action.trim() || !form.f.subject.trim()} onClick={() => void submit()}>Save</Button>
          </>
        }
      >
        {form && (
          <Stack gap="md">
            {form.id === null && <Select label="Topic" fullWidth options={topics.map((t) => ({ value: t, label: t }))} value={form.f.topic} onValueChange={(topic) => setForm({ ...form, f: { ...form.f, topic } })} />}
            <Grid columns={3} stackAt="small" gap="sm">
              <TextField label="Who" placeholder="e.g. Pearson" value={form.f.actor} onChange={(actor) => setForm({ ...form, f: { ...form.f, actor } })} />
              <TextField label="Did what" placeholder="e.g. acquired" value={form.f.action} onChange={(action) => setForm({ ...form, f: { ...form.f, action } })} />
              <TextField label="Date" type="date" value={form.f.event_date} onChange={(event_date) => setForm({ ...form, f: { ...form.f, event_date } })} />
            </Grid>
            <TextField label="To what" placeholder="e.g. an AI tutoring start-up" value={form.f.subject} onChange={(subject) => setForm({ ...form, f: { ...form.f, subject } })} />
            <Grid columns={2} stackAt="small" gap="sm">
              <TextField label="Amount (optional)" type="number" value={form.f.magnitude_value} onChange={(magnitude_value) => setForm({ ...form, f: { ...form.f, magnitude_value } })} />
              <TextField label="Unit" placeholder="e.g. USD m" value={form.f.magnitude_unit} onChange={(magnitude_unit) => setForm({ ...form, f: { ...form.f, magnitude_unit } })} />
            </Grid>
            <TextArea label="Sources" rows={2} hint="One link per line." value={form.f.source_urls} onChange={(source_urls) => setForm({ ...form, f: { ...form.f, source_urls } })} />
          </Stack>
        )}
      </Dialog>
    </Stack>
  );
}
