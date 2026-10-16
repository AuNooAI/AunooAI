import { useEffect, useState } from 'react';
import { Button, Chip, EmptyState, Icon, IconButton, Panel, Select, Stack, Text, TextArea, TextField } from '@aunoo/ui';
import type { BriefingAction, BriefingReview, BriefingTheme, DeskBriefing } from '@monolith/briefingDeskApi';
import { Markdown } from '../../../shell/Markdown';
import { MarkdownEditor } from '../../../anticipate/components/MarkdownEditor';
import { errorText } from '../../../shell';
import { fmtDate, URGENCY_LABEL, URGENCY_TONE } from './format';
import { ReviewNote } from './Review';

/*
 * The briefing's written part: the executive summary, key themes and priority actions, each
 * editable on its own. A save that fails keeps the edit open and says why.
 */

function EditBar({ editing, saving, onEdit, onSave, onCancel, editLabel = 'Edit' }: {
  editing: boolean; saving: boolean; onEdit: () => void; onSave: () => void; onCancel: () => void; editLabel?: string;
}) {
  return editing ? (
    <Stack direction="row" gap="sm">
      <Button variant="secondary" size="sm" disabled={saving} onClick={onCancel}>Cancel</Button>
      <Button size="sm" busy={saving} iconStart={<Icon name="Check" size="sm" />} onClick={onSave}>Save</Button>
    </Stack>
  ) : (
    <Button variant="ghost" size="sm" iconStart={<Icon name="PencilSimple" size="sm" />} onClick={onEdit}>{editLabel}</Button>
  );
}

function useSection<T>(stored: T, save: (v: T) => Promise<void>, notify: (m: string) => void) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<T>(stored);
  const [saving, setSaving] = useState(false);
  // Keyed on the content, not the object: a briefing with no themes passes a fresh [] each render
  const key = JSON.stringify(stored);
  useEffect(() => {
    if (!editing) setDraft(JSON.parse(key) as T);
  }, [key, editing]);
  return {
    editing, draft, setDraft, saving,
    edit: () => { setDraft(stored); setEditing(true); },
    cancel: () => { setDraft(stored); setEditing(false); },
    save: async () => {
      setSaving(true);
      try {
        await save(draft);
        setEditing(false);
      } catch (e) {
        notify(`Not saved: ${errorText(e)}`);
      } finally {
        setSaving(false);
      }
    },
  };
}

export function Synthesis({ briefing, modelNames, onSaveSummary, onSaveThemes, onSaveActions, notify }: {
  briefing: DeskBriefing;
  /** The models this site actually ran, for the disclosure when the briefing doesn't name one */
  modelNames: string | null;
  onSaveSummary: (v: string) => Promise<void>;
  onSaveThemes: (v: BriefingTheme[]) => Promise<void>;
  onSaveActions: (v: BriefingAction[]) => Promise<void>;
  notify: (m: string) => void;
}) {
  const isDraft = briefing.status === 'draft';
  const review = (briefing.metadata as { review?: BriefingReview } | undefined)?.review;
  const summary = useSection(briefing.synthesis ?? '', onSaveSummary, notify);
  const themes = useSection<BriefingTheme[]>(briefing.themes ?? [], onSaveThemes, notify);
  const actions = useSection<BriefingAction[]>(briefing.priority_actions ?? [], onSaveActions, notify);
  const topic = briefing.topic ?? '';

  if (!briefing.synthesis && !isDraft) return <EmptyState icon="Sparkle" title="No summary">This briefing was finalized without a summary.</EmptyState>;

  const setTheme = (i: number, patch: Partial<BriefingTheme>) => themes.setDraft(themes.draft.map((t, k) => (k === i ? { ...t, ...patch } : t)));
  const setAction = (i: number, patch: Partial<BriefingAction>) => actions.setDraft(actions.draft.map((a, k) => (k === i ? { ...a, ...patch } : a)));

  return (
    <Stack gap="lg">
      <Panel
        title="Executive summary"
        headingLevel={3}
        headerAside={<EditBar editing={summary.editing} saving={summary.saving} onEdit={summary.edit} onSave={() => void summary.save()} onCancel={summary.cancel} editLabel={briefing.synthesis ? 'Edit' : 'Write'} />}
      >
        {summary.editing ? (
          <MarkdownEditor label="Executive summary (Markdown)" value={summary.draft} onChange={summary.setDraft} topic={topic} />
        ) : briefing.synthesis ? (
          <Markdown text={briefing.synthesis} />
        ) : (
          <Text variant="hint">No summary yet. Write your own with “Write”, or have the AI write one with “Write with AI” above.</Text>
        )}
      </Panel>

      {(themes.editing || (briefing.themes?.length ?? 0) > 0 || briefing.synthesis) && (
        <Panel
          title="Key themes"
          headingLevel={3}
          headerAside={<EditBar editing={themes.editing} saving={themes.saving} onEdit={themes.edit} onSave={() => void themes.save()} onCancel={themes.cancel} />}
        >
          {themes.editing ? (
            <Stack gap="md">
              {themes.draft.map((t, i) => (
                <Stack key={i} gap="sm">
                  <Stack direction="row" gap="sm" wrap={false}>
                    <TextField label={`Theme ${i + 1}`} value={t.theme_name} onChange={(v) => setTheme(i, { theme_name: v })} />
                    <IconButton tone="danger" icon={<Icon name="Trash" size="sm" />} label={`Remove theme ${i + 1}`} onClick={() => themes.setDraft(themes.draft.filter((_, k) => k !== i))} />
                  </Stack>
                  <TextArea label="Description" rows={2} value={t.description} onChange={(v) => setTheme(i, { description: v })} />
                  <TextField label="Strategic implication" value={t.strategic_implication ?? ''} onChange={(v) => setTheme(i, { strategic_implication: v })} />
                </Stack>
              ))}
              <div><Button variant="ghost" size="sm" iconStart={<Icon name="Plus" size="sm" />} onClick={() => themes.setDraft([...themes.draft, { theme_name: '', description: '', strategic_implication: '' }])}>Add a theme</Button></div>
            </Stack>
          ) : (briefing.themes?.length ?? 0) === 0 ? (
            <Text variant="hint">No themes.</Text>
          ) : (
            <Stack as="ul" gap="md" label="Key themes">
              {briefing.themes!.map((t, i) => (
                <li key={i}>
                  <Stack gap="sm">
                    <Text variant="label">{t.theme_name}</Text>
                    <Text>{t.description}</Text>
                    {t.strategic_implication && <Text variant="caption">{`Strategic implication: ${t.strategic_implication}`}</Text>}
                  </Stack>
                </li>
              ))}
            </Stack>
          )}
        </Panel>
      )}

      {(actions.editing || (briefing.priority_actions?.length ?? 0) > 0 || briefing.synthesis) && (
        <Panel
          title="Priority actions"
          headingLevel={3}
          headerAside={<EditBar editing={actions.editing} saving={actions.saving} onEdit={actions.edit} onSave={() => void actions.save()} onCancel={actions.cancel} />}
        >
          {actions.editing ? (
            <Stack gap="md">
              {actions.draft.map((a, i) => (
                <Stack key={i} gap="sm">
                  <Stack direction="row" gap="sm" wrap={false}>
                    <TextField label={`Action ${i + 1}`} value={a.action} onChange={(v) => setAction(i, { action: v })} />
                    <IconButton tone="danger" icon={<Icon name="Trash" size="sm" />} label={`Remove action ${i + 1}`} onClick={() => actions.setDraft(actions.draft.filter((_, k) => k !== i))} />
                  </Stack>
                  <Select
                    label="When"
                    options={(Object.keys(URGENCY_LABEL) as BriefingAction['urgency'][]).map((u) => ({ value: u, label: URGENCY_LABEL[u] }))}
                    value={a.urgency}
                    onValueChange={(v) => setAction(i, { urgency: v as BriefingAction['urgency'] })}
                  />
                  <TextField label="Rationale (optional)" value={a.rationale ?? ''} onChange={(v) => setAction(i, { rationale: v })} />
                </Stack>
              ))}
              <div><Button variant="ghost" size="sm" iconStart={<Icon name="Plus" size="sm" />} onClick={() => actions.setDraft([...actions.draft, { action: '', urgency: 'this_week', rationale: '' }])}>Add an action</Button></div>
            </Stack>
          ) : (briefing.priority_actions?.length ?? 0) === 0 ? (
            <Text variant="hint">No actions.</Text>
          ) : (
            <Stack as="ul" gap="md" label="Priority actions">
              {briefing.priority_actions!.map((a, i) => (
                <li key={i}>
                  <Stack gap="sm">
                    <Stack direction="row" gap="sm">
                      <Chip tone={URGENCY_TONE[a.urgency] ?? 'muted'} size="sm">{URGENCY_LABEL[a.urgency] ?? a.urgency}</Chip>
                      <Text as="span" variant="label">{a.action}</Text>
                    </Stack>
                    {a.rationale && <Text variant="caption">{a.rationale}</Text>}
                  </Stack>
                </li>
              ))}
            </Stack>
          )}
        </Panel>
      )}

      {briefing.synthesis && briefing.metadata && (
        <Stack gap="sm">
          <Text variant="caption">
            {`Written with ${briefing.model_used || modelNames || 'the AI models configured for this site'}${briefing.finalized_at ? ` on ${fmtDate(briefing.finalized_at)}` : ', still a draft'}.`}
          </Text>
          {review && <ReviewNote review={review} />}
        </Stack>
      )}
    </Stack>
  );
}
