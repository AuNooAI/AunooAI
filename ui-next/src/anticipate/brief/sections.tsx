import { useEffect, useState } from 'react';
import { Banner, Button, Chip, Grid, Icon, LineItems, Panel, Select, SettingRow, Stack, Text, TextArea, TextField } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { api, errorText } from '../../shell';
import { MarkdownEditor } from '../components/MarkdownEditor';
import { useJob } from '../lib/jobs';
import { editor, type BriefApi, type Stage, type TopicSummary } from './model';

/* ── shared pieces ─────────────────────────────────────────────────── */

/** One regenerate at a time; polls the job, then reloads the brief. */
export function useRegenerate(b: BriefApi, notify: (m: string) => void) {
  const job = useJob(1500);
  const [stage, setStage] = useState<string | null>(null);
  const start = async (s: Stage, topic?: string) => {
    try {
      const r = await api<{ task_id: string; status_url?: string }>(`${b.base}/regenerate-stage`, { method: 'POST', json: { stage: s, topic, actor: editor() } });
      setStage(topic ? `${s}:${topic}` : s);
      job.watch(r.status_url ?? `/api/forecast/assessment/job/${r.task_id}`, () => {
        setStage(null);
        notify('Regenerated. Locked parts were kept.');
        void b.reload();
      });
    } catch (e) {
      notify(`Regenerate didn’t start: ${errorText(e)}`);
    }
  };
  const running = job.state.kind === 'running' ? stage : null;
  return { running, failed: job.state.kind === 'failed' ? job.state.message : null, start, is: (s: Stage, topic?: string) => running === (topic ? `${s}:${topic}` : s) };
}
export type Regen = ReturnType<typeof useRegenerate>;

function LockButton({ locked, onToggle }: { locked: boolean; onToggle: () => void }) {
  return (
    <Button variant={locked ? 'secondary' : 'ghost'} size="sm" iconStart={<Icon name="Lock" size="sm" />} onClick={onToggle} aria-pressed={locked}>
      {locked ? 'Locked' : 'Lock'}
    </Button>
  );
}

function RegenButton({ busy, disabled, onClick }: { busy: boolean; disabled: boolean; onClick: () => void }) {
  return (
    <Button variant="ghost" size="sm" iconStart={<Icon name="ArrowsClockwise" size="sm" />} busy={busy} disabled={disabled && !busy} onClick={onClick}>
      Regenerate
    </Button>
  );
}

/** A text draft that follows the saved value until edited. */
function useDraft(saved: string) {
  const [draft, setDraft] = useState(saved);
  useEffect(() => setDraft(saved), [saved]);
  return { draft, setDraft, dirty: draft !== saved, revert: () => setDraft(saved) };
}

function SaveRow({ dirty, onSave, onRevert, label = 'Save' }: { dirty: boolean; onSave: () => void; onRevert: () => void; label?: string }) {
  return (
    <Stack direction="row" gap="sm">
      <Button size="sm" disabled={!dirty} onClick={onSave}>{label}</Button>
      <Button size="sm" variant="ghost" disabled={!dirty} onClick={onRevert}>Revert</Button>
    </Stack>
  );
}

const lines = (v: string[]) => v.join('\n');
const unlines = (t: string) => t.split('\n').map((x) => x.trim()).filter(Boolean);

/* ── Exec summary ──────────────────────────────────────────────────── */

export function ExecSummary({ b, regen, topic }: { b: BriefApi; regen: Regen; topic: string }) {
  const p = b.brief!.payload;
  const letter = useDraft(p.exec_summary?.letter ?? '');
  const signoff = useDraft(p.exec_summary?.signoff ?? '');
  const comm = useDraft(p.expert_commentary ?? '');
  const L = 'exec_summary.letter';
  const C = 'expert_commentary';
  return (
    <Stack gap="lg">
      <Panel
        title="Executive summary letter"
        description="Markdown. Bold lead-ins such as **The bottom line.** become slide subheads. Lock it to keep your edits through a regenerate."
        headerAside={
          <Stack direction="row" gap="sm">
            <LockButton locked={b.isLocked(L)} onToggle={() => void b.lock(L, !b.isLocked(L))} />
            <RegenButton busy={regen.is('exec_summary')} disabled={Boolean(regen.running)} onClick={() => void regen.start('exec_summary')} />
          </Stack>
        }
      >
        <Stack gap="md">
          <MarkdownEditor label="Letter" value={letter.draft} onChange={letter.setDraft} topic={topic} />
          <SaveRow dirty={letter.dirty} onSave={() => void b.patch(L, letter.draft)} onRevert={letter.revert} label="Save letter" />
          <TextField label="Signoff" placeholder="AunooAI Editorial Team · Q2 2026" value={signoff.draft} onChange={signoff.setDraft} />
          <SaveRow dirty={signoff.dirty} onSave={() => void b.patch('exec_summary.signoff', signoff.draft)} onRevert={signoff.revert} label="Save signoff" />
        </Stack>
      </Panel>
      <Panel
        title="Expert view: emerging themes"
        description="One or two paragraphs interpreting the period’s emerging themes. It appears in the deck, the executive summary document and the HTML version."
        headerAside={
          <Stack direction="row" gap="sm">
            <LockButton locked={b.isLocked(C)} onToggle={() => void b.lock(C, !b.isLocked(C))} />
            <RegenButton busy={regen.is('expert_commentary')} disabled={Boolean(regen.running)} onClick={() => void regen.start('expert_commentary')} />
          </Stack>
        }
      >
        <Stack gap="md">
          <TextArea label="Commentary" rows={8} value={comm.draft} onChange={comm.setDraft} />
          <SaveRow dirty={comm.dirty} onSave={() => void b.patch(C, comm.draft)} onRevert={comm.revert} label="Save commentary" />
        </Stack>
      </Panel>
    </Stack>
  );
}

/* ── Themes and decision framework (lists of {lead|headline, body}) ── */

function ListItem({ b, path, item, fields, index, onRemove }: { b: BriefApi; path: string; item: Record<string, string>; fields: [string, string]; index: number; onRemove: () => void }) {
  const head = useDraft(item[fields[0]] ?? '');
  const body = useDraft(item[fields[1]] ?? '');
  const locked = b.isLocked(path);
  return (
    <SettingRow
      title={`${index + 1}. ${item[fields[0]] || 'Untitled'}`}
      actionsPlacement="title"
      actions={
        <Stack direction="row" gap="sm">
          <LockButton locked={locked} onToggle={() => void b.lock(path, !locked)} />
          <Button variant="ghost" size="sm" iconStart={<Icon name="Trash" size="sm" />} onClick={onRemove}>Remove</Button>
        </Stack>
      }
    >
      <Stack gap="sm">
        <TextField label={fields[0] === 'lead' ? 'Lead' : 'Headline'} value={head.draft} onChange={head.setDraft} />
        <TextArea label="Body" rows={4} value={body.draft} onChange={body.setDraft} />
        <SaveRow
          dirty={head.dirty || body.dirty}
          onSave={() => void b.patch(path, { ...item, [fields[0]]: head.draft, [fields[1]]: body.draft })}
          onRevert={() => { head.revert(); body.revert(); }}
        />
      </Stack>
    </SettingRow>
  );
}

export function ListSection({ b, regen, rootKey, title, description, fields, askConfirm }: {
  b: BriefApi; regen: Regen; rootKey: 'cross_cutting_themes' | 'executive_decision_framework'; title: string; description: string; fields: [string, string]; askConfirm: (c: Confirm) => void;
}) {
  const items = b.brief!.payload[rootKey] ?? [];
  return (
    <Panel
      title={title}
      description={`${description} Themes and the decision framework regenerate together.`}
      headerAside={<RegenButton busy={regen.is('cross_topic')} disabled={Boolean(regen.running)} onClick={() => void regen.start('cross_topic')} />}
    >
      <Stack gap="md">
        {items.length === 0 && <Text variant="hint">No items yet.</Text>}
        <Stack as="ul" gap="sm" label={title}>
          {items.map((it, i) => (
            // Keyed by content as well as position, so a removal can't leave stale text in the boxes
            <li key={`${i}-${it[fields[0]] ?? ''}`}>
              <ListItem
                b={b}
                path={`${rootKey}[${i}]`}
                item={it}
                fields={fields}
                index={i}
                onRemove={() =>
                  askConfirm({
                    title: 'Remove this item?',
                    message: `“${it[fields[0]] || `Item ${i + 1}`}” will be removed from the brief.`,
                    action: 'Remove',
                    onConfirm: () => void b.patch(rootKey, items.filter((_, j) => j !== i)),
                  })
                }
              />
            </li>
          ))}
        </Stack>
        <Stack direction="row">
          <Button variant="secondary" size="sm" iconStart={<Icon name="Plus" size="sm" />} onClick={() => void b.patch(rootKey, [...items, { [fields[0]]: '', [fields[1]]: '' }])}>Add item</Button>
        </Stack>
      </Stack>
    </Panel>
  );
}

/* ── What's changed ────────────────────────────────────────────────── */

const WC: { key: string; title: string; help: string }[] = [
  { key: 'events', title: 'Named events this period', help: 'Filled from event extraction. Choose what goes in the deck on the Events tab.' },
  { key: 'scenario_drift', title: 'Scenarios that moved in our framing', help: 'One line per scenario: its name and how its position changed.' },
  { key: 'emerging', title: 'New on the watch', help: 'New emerging themes found this period.' },
  { key: 'coverage_shifts', title: 'Where press attention shifted', help: 'Press attention only. Never framed as forecast accuracy.' },
];

function WcBlock({ b, k, title, help, items }: { b: BriefApi; k: string; title: string; help: string; items: string[] }) {
  const d = useDraft(lines(items));
  const path = `whats_changed.${k}`;
  const locked = b.isLocked(path);
  return (
    <SettingRow title={title} description={help} actionsPlacement="title" actions={<LockButton locked={locked} onToggle={() => void b.lock(path, !locked)} />}>
      <Stack gap="sm">
        <TextArea label={title} hideLabel rows={Math.max(3, items.length + 1)} value={d.draft} onChange={d.setDraft} hint="One line per item." />
        <SaveRow dirty={d.dirty} onSave={() => void b.patch(path, unlines(d.draft))} onRevert={d.revert} />
      </Stack>
    </SettingRow>
  );
}

export function WhatsChanged({ b }: { b: BriefApi }) {
  const wc = b.brief!.payload.whats_changed ?? {};
  return (
    <Panel title="What’s changed since the last period" description="Four signals in slide order. When space is short the slide drops lines from the bottom.">
      <Stack as="ul" gap="sm" label="What’s changed">
        {WC.map((s) => (
          <li key={s.key}>
            <WcBlock b={b} k={s.key} title={s.title} help={s.help} items={Array.isArray(wc[s.key]) ? wc[s.key] : []} />
          </li>
        ))}
      </Stack>
    </Panel>
  );
}

/* ── Per topic ─────────────────────────────────────────────────────── */

type Item = Record<string, string> | string;
// Current runs store objects; these are the fields the editor shows for each list
const REC_FIELDS = ['headline', 'rationale', 'horizon'];
const STEP_FIELDS = ['action', 'category'];
const label = (f: string) => f[0].toUpperCase() + f.slice(1);

/** Edits a list of objects (or old plain strings) field by field and saves the whole list. */
function ObjectList({ items, fields, onSave }: { items: Item[]; fields: string[]; onSave: (next: Item[]) => void }) {
  const saved = JSON.stringify(items);
  const [draft, setDraft] = useState<Item[]>(items);
  useEffect(() => setDraft(JSON.parse(saved)), [saved]);
  const dirty = JSON.stringify(draft) !== saved;
  const setAt = (i: number, f: string | null, v: string) =>
    setDraft((d) => d.map((x, j) => (j !== i ? x : f === null ? v : { ...(typeof x === 'string' ? {} : x), [f]: v })));
  return (
    <Stack gap="md">
      {draft.length === 0 && <Text variant="hint">None yet.</Text>}
      {draft.map((it, i) => (
        <SettingRow
          key={i}
          title={`${i + 1}.`}
          actionsPlacement="title"
          actions={<Button variant="ghost" size="sm" iconStart={<Icon name="Trash" size="sm" />} onClick={() => setDraft((d) => d.filter((_, j) => j !== i))}>Remove</Button>}
        >
          {typeof it === 'string' ? (
            <TextArea label="Text" rows={2} value={it} onChange={(v) => setAt(i, null, v)} />
          ) : (
            <Grid columns={fields.length > 2 ? 3 : 2} stackAt="small" gap="sm">
              {fields.map((f) =>
                f === 'rationale' ? (
                  <TextArea key={f} label={label(f)} rows={3} value={it[f] ?? ''} onChange={(v) => setAt(i, f, v)} />
                ) : (
                  <TextField key={f} label={label(f)} value={it[f] ?? ''} onChange={(v) => setAt(i, f, v)} />
                ),
              )}
            </Grid>
          )}
        </SettingRow>
      ))}
      <Stack direction="row" gap="sm">
        <Button variant="secondary" size="sm" iconStart={<Icon name="Plus" size="sm" />} onClick={() => setDraft((d) => [...d, Object.fromEntries(fields.map((f) => [f, '']))])}>Add</Button>
        <Button size="sm" disabled={!dirty} onClick={() => onSave(draft)}>Save</Button>
        <Button size="sm" variant="ghost" disabled={!dirty} onClick={() => setDraft(JSON.parse(saved))}>Revert</Button>
      </Stack>
    </Stack>
  );
}

function TopicBriefing({ save, briefing }: { save: (path: string, v: unknown) => void; briefing: NonNullable<TopicSummary['topic_briefing']> }) {
  const headline = useDraft(briefing.headline ?? '');
  const lede = useDraft(briefing.lede ?? '');
  const view = useDraft(briefing.intelligence_view ?? '');
  const savedT = JSON.stringify(briefing.tensions ?? []);
  const [tensions, setTensions] = useState<{ name?: string; body?: string }[]>(briefing.tensions ?? []);
  useEffect(() => setTensions(JSON.parse(savedT)), [savedT]);
  const tDirty = JSON.stringify(tensions) !== savedT;
  const dirty = headline.dirty || lede.dirty || view.dirty || tDirty;
  return (
    <Stack gap="md">
      <TextField label="Headline" value={headline.draft} onChange={headline.setDraft} />
      <TextArea label="Lede" rows={3} value={lede.draft} onChange={lede.setDraft} />
      <TextArea label="Intelligence view" rows={4} value={view.draft} onChange={view.setDraft} />
      {tensions.map((t, i) => (
        <Grid key={i} columns={2} stackAt="small" gap="sm">
          <TextField label={`Tension ${i + 1}: name`} value={t.name ?? ''} onChange={(v) => setTensions((x) => x.map((y, j) => (j === i ? { ...y, name: v } : y)))} />
          <TextArea label="Body" rows={2} value={t.body ?? ''} onChange={(v) => setTensions((x) => x.map((y, j) => (j === i ? { ...y, body: v } : y)))} />
        </Grid>
      ))}
      <SaveRow
        dirty={dirty}
        onSave={() => save('topic_briefing', { ...briefing, headline: headline.draft, lede: lede.draft, intelligence_view: view.draft, tensions })}
        onRevert={() => { headline.revert(); lede.revert(); view.revert(); setTensions(JSON.parse(savedT)); }}
      />
    </Stack>
  );
}

export function PerTopic({ b, regen }: { b: BriefApi; regen: Regen }) {
  const topics = b.brief!.per_topic;
  const [active, setActive] = useState(topics[0]?.topic ?? '');
  const t = topics.find((x) => x.topic === active) ?? topics[0];
  if (!t) return <Text variant="hint">No topics in this brief.</Text>;
  if (!t.assessment_id) return <Banner tone="warning" icon="Warning" title={`${t.topic} has no assessment yet`} description="Run its forecast assessment first; the per-topic sections come from it." />;
  const s = t.summary ?? {};
  const locked = (p: string) => t.summary_locked_keys.includes(p);
  const save = (path: string, v: unknown) => void b.patchTopic(t.topic, t.assessment_id, path, v);
  // There is no separate lock route for topic fields: the lock rides on a patch of the current value
  const toggle = (path: string, value: unknown) => void b.patchTopic(t.topic, t.assessment_id, path, value, !locked(path));
  const head = (path: string, value: unknown, stage: Stage) => (
    <Stack direction="row" gap="sm">
      <LockButton locked={locked(path)} onToggle={() => toggle(path, value)} />
      <RegenButton busy={regen.is(stage, t.topic)} disabled={Boolean(regen.running)} onClick={() => void regen.start(stage, t.topic)} />
    </Stack>
  );
  return (
    <Stack gap="lg">
      <Select label="Topic" options={topics.map((x) => ({ value: x.topic, label: x.topic }))} value={t.topic} onValueChange={setActive} />
      <Panel title="Briefing" description={t.assessed_at ? `From the assessment of ${new Date(t.assessed_at).toLocaleDateString('en-GB')}` : undefined} headerAside={head('topic_briefing', s.topic_briefing ?? {}, 'briefing')}>
        <TopicBriefing key={t.topic} save={save} briefing={s.topic_briefing ?? {}} />
      </Panel>
      <Panel title="Strategic recommendations" headerAside={head('strategic_recommendations', s.strategic_recommendations ?? [], 'recommendations')}>
        <ObjectList key={t.topic} items={s.strategic_recommendations ?? []} fields={REC_FIELDS} onSave={(v) => save('strategic_recommendations', v)} />
      </Panel>
      <Panel title="Next steps" headerAside={head('next_steps', s.next_steps ?? [], 'next_steps')}>
        <ObjectList key={t.topic} items={s.next_steps ?? []} fields={STEP_FIELDS} onSave={(v) => save('next_steps', v)} />
      </Panel>
    </Stack>
  );
}

/* ── Approval ──────────────────────────────────────────────────────── */

export function Approval({ b, onApprove }: { b: BriefApi; onApprove: () => void }) {
  const r = b.brief!.review ?? {};
  const findings = r.reviewer_findings ?? [];
  const errors = findings.filter((f) => f.severity === 'error').length;
  const warnings = findings.filter((f) => f.severity === 'warning').length;
  return (
    <Stack gap="lg">
      <LineItems
        label="Review"
        items={[
          { id: 'status', label: 'Review status', amount: (r.status ?? 'not reviewed').replace(/_/g, ' ') },
          { id: 'errors', label: 'Errors', amount: String(errors) },
          { id: 'warnings', label: 'Warnings', amount: String(warnings) },
          ...(r.approved_at ? [{ id: 'approved', label: 'Approved', amount: `${new Date(r.approved_at).toLocaleString('en-GB')}${r.approved_by ? ` by ${r.approved_by}` : ''}` }] : []),
        ]}
      />
      <Panel title={`Locked sections (${b.brief!.locked_keys.length})`} description="A regenerate keeps these as they are.">
        {b.brief!.locked_keys.length === 0 ? (
          <Text variant="hint">Nothing locked. Lock anything you’ve edited so a regenerate keeps it.</Text>
        ) : (
          <Stack direction="row" gap="sm">
            {b.brief!.locked_keys.map((k) => <Chip key={k} size="sm" tone="warning">{k}</Chip>)}
          </Stack>
        )}
      </Panel>
      <Panel title="Reviewer findings">
        {findings.length === 0 ? (
          <Text variant="hint">No findings on record.</Text>
        ) : (
          <Stack as="ul" gap="sm" label="Reviewer findings">
            {findings.map((f, i) => (
              <li key={i}>
                <SettingRow
                  title={f.finding ?? ''}
                  description={f.suggested_fix ? `Suggested fix: ${f.suggested_fix}` : undefined}
                  actionsPlacement="title"
                  actions={<Chip size="sm" tone={f.severity === 'error' ? 'error' : f.severity === 'warning' ? 'warning' : 'muted'}>{`${f.severity ?? 'info'} · ${f.artefact_key || f.stage || '—'}`}</Chip>}
                />
              </li>
            ))}
          </Stack>
        )}
      </Panel>
      <Stack gap="sm">
        <Stack direction="row">
          <Button iconStart={<Icon name="CheckCircle" size="sm" />} onClick={onApprove}>Approve and release</Button>
        </Stack>
        <Text variant="hint">Records who approved it and when. The bundle download then works for the recipient.</Text>
      </Stack>
    </Stack>
  );
}
