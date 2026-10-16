import { useEffect, useState } from 'react';
import { Banner, Button, Chip, Dialog, DialogClose, Grid, Select, Stack, TextArea, TextField } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { createOrganizationalProfile, deleteOrganizationalProfile, updateOrganizationalProfile, type OrganizationalProfile } from '@monolith/api';
import { errorText } from '../../shell';

/** The server's profile fields. monitored_brands feeds the daily briefings. */
type Profile = Omit<OrganizationalProfile, 'id' | 'is_default'> & { monitored_brands: string[] };

const NEW = 'new';
const EMPTY: Profile = {
  name: '', description: '', industry: '', organization_type: '', region: '',
  key_concerns: [], strategic_priorities: [], risk_tolerance: 'medium', innovation_appetite: 'moderate', decision_making_style: 'collaborative',
  stakeholder_focus: [], competitive_landscape: [], regulatory_environment: [], custom_context: '', monitored_brands: [],
};
// Lists edit as one item per line: profile items are often whole sentences
const LISTS = ['key_concerns', 'strategic_priorities', 'stakeholder_focus', 'competitive_landscape', 'regulatory_environment', 'monitored_brands'] as const;
type ListKey = (typeof LISTS)[number];
const textsOf = (f: Profile) => Object.fromEntries(LISTS.map((k) => [k, f[k].join('\n')])) as Record<ListKey, string>;
const unlines = (t: string) => t.split('\n').map((x) => x.trim()).filter(Boolean);

const arr = (v: unknown) => (Array.isArray(v) ? v.map(String) : []);
const toForm = (p: OrganizationalProfile): Profile => {
  const r = p as OrganizationalProfile & { monitored_brands?: unknown };
  return {
    ...EMPTY,
    name: p.name ?? '', description: p.description ?? '', industry: p.industry ?? '', organization_type: p.organization_type ?? '', region: p.region ?? '',
    key_concerns: arr(p.key_concerns), strategic_priorities: arr(p.strategic_priorities), stakeholder_focus: arr(p.stakeholder_focus),
    competitive_landscape: arr(p.competitive_landscape), regulatory_environment: arr(p.regulatory_environment), monitored_brands: arr(r.monitored_brands),
    risk_tolerance: p.risk_tolerance || 'medium', innovation_appetite: p.innovation_appetite || 'moderate', decision_making_style: p.decision_making_style || 'collaborative',
    custom_context: p.custom_context ?? '',
  };
};

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  profiles: OrganizationalProfile[];
  /** Profile to open on; new when absent */
  initialId?: number | null;
  /** After a save or delete: reload the list; `selectId` is the saved profile */
  onChanged: (selectId?: number) => Promise<void> | void;
  notify: (message: string) => void;
  askConfirm: (c: Confirm) => void;
}

/**
 * Create, edit and delete organisational profiles (the old modal's Save never wrote anything).
 * Default profiles can be edited but not deleted, as the server enforces.
 */
export function ProfilesDialog({ open, onOpenChange, profiles, initialId, onChanged, notify, askConfirm }: Props) {
  const [pick, setPick] = useState(NEW);
  const [form, setForm] = useState<Profile>(EMPTY);
  // The list boxes' raw text, split into items only on save so Enter can start a new line
  const [texts, setTexts] = useState<Record<ListKey, string>>(textsOf(EMPTY));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const current = profiles.find((p) => String(p.id) === pick);

  const choose = (value: string) => {
    setPick(value);
    setError(null);
    const p = profiles.find((x) => String(x.id) === value);
    const f = p ? toForm(p) : EMPTY;
    setForm(f);
    setTexts(textsOf(f));
  };
  useEffect(() => {
    if (open) choose(initialId != null && profiles.some((p) => p.id === initialId) ? String(initialId) : NEW);
    // Only when it opens: a list refresh after saving must not reset the form
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const set = (patch: Partial<Profile>) => setForm((f) => ({ ...f, ...patch }));

  const save = async () => {
    setBusy(true);
    setError(null);
    const body = { ...form, ...Object.fromEntries(LISTS.map((k) => [k, unlines(texts[k])])), name: form.name.trim() } as Profile;
    try {
      if (current?.id != null) {
        await updateOrganizationalProfile(current.id, body);
        await onChanged(current.id);
      } else {
        const r = await createOrganizationalProfile(body);
        await onChanged(r.profile_id);
        setPick(String(r.profile_id));
      }
      notify(`Profile “${body.name}” saved`);
    } catch (e) {
      const t = errorText(e);
      setError(t.includes('409') || /already exists/i.test(t) ? 'A profile with this name already exists.' : t);
    } finally {
      setBusy(false);
    }
  };

  const remove = () => {
    if (current?.id == null) return;
    const { id, name } = current;
    askConfirm({
      title: 'Delete profile?',
      message: `“${name}” will be deleted. Analyses already saved with it keep their copy.`,
      action: 'Delete',
      onConfirm: async () => {
        try {
          await deleteOrganizationalProfile(id);
          notify(`Profile “${name}” deleted`);
          await onChanged();
          choose(NEW);
        } catch (e) {
          notify(`Not deleted: ${errorText(e)}`);
        }
      },
    });
  };

  const isDefault = Boolean(current?.is_default);
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title="Organizational profiles"
      description="Who the analyses are written for. The AI uses the profile to judge what matters and to tailor recommendations."
      footer={
        <>
          {current && !isDefault && <Button variant="ghost" size="lg" onClick={remove}>Delete</Button>}
          <DialogClose>
            <Button variant="secondary" size="lg">Close</Button>
          </DialogClose>
          <Button size="lg" busy={busy} disabled={!form.name.trim()} onClick={save}>{current ? 'Save changes' : 'Create profile'}</Button>
        </>
      }
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <Select
            label="Profile"
            fullWidth
            options={[{ value: NEW, label: 'New profile' }, ...profiles.filter((p) => p.id != null).map((p) => ({ value: String(p.id), label: p.name }))]}
            value={pick}
            onValueChange={choose}
          />
          {isDefault && <Chip size="sm" tone="muted">Default</Chip>}
        </Stack>
        {error && <Banner tone="error" icon="WarningCircle" title="Not saved" description={error} />}
        <Grid columns={2} stackAt="small" gap="md">
          <TextField label="Name" value={form.name} onChange={(name) => set({ name })} />
          <TextField label="Industry" value={form.industry ?? ''} onChange={(industry) => set({ industry })} />
          <TextField label="Organization type" placeholder="e.g. Publisher, Bank, Agency" value={form.organization_type ?? ''} onChange={(organization_type) => set({ organization_type })} />
          <TextField label="Region" value={form.region ?? ''} onChange={(region) => set({ region })} />
        </Grid>
        <TextArea label="Description" rows={2} value={form.description ?? ''} onChange={(description) => set({ description })} />
        {/* Free text: sites store values like "data-driven" or a sentence, which a fixed list would drop */}
        <Grid columns={3} stackAt="small" gap="md">
          <TextField label="Risk tolerance" placeholder="low, medium or high" value={form.risk_tolerance} onChange={(risk_tolerance) => set({ risk_tolerance })} />
          <TextField label="Innovation appetite" placeholder="conservative, moderate or aggressive" value={form.innovation_appetite} onChange={(innovation_appetite) => set({ innovation_appetite })} />
          <TextField label="Decision making" placeholder="e.g. data-driven, collaborative" value={form.decision_making_style} onChange={(decision_making_style) => set({ decision_making_style })} />
        </Grid>
        <Grid columns={2} stackAt="small" gap="md">
          <TextArea label="Key concerns" rows={4} hint="One per line." value={texts.key_concerns} onChange={(t) => setTexts((x) => ({ ...x, key_concerns: t }))} />
          <TextArea label="Strategic priorities" rows={4} hint="One per line." value={texts.strategic_priorities} onChange={(t) => setTexts((x) => ({ ...x, strategic_priorities: t }))} />
          <TextArea label="Stakeholder focus" rows={4} hint="One per line." value={texts.stakeholder_focus} onChange={(t) => setTexts((x) => ({ ...x, stakeholder_focus: t }))} />
          <TextArea label="Competitors" rows={4} hint="One per line." value={texts.competitive_landscape} onChange={(t) => setTexts((x) => ({ ...x, competitive_landscape: t }))} />
          <TextArea label="Regulatory environment" rows={4} hint="One per line." value={texts.regulatory_environment} onChange={(t) => setTexts((x) => ({ ...x, regulatory_environment: t }))} />
          <TextArea label="Monitored brands" rows={4} hint="One per line. Named in the daily briefings." value={texts.monitored_brands} onChange={(t) => setTexts((x) => ({ ...x, monitored_brands: t }))} />
        </Grid>
        <TextArea label="Other context" rows={3} value={form.custom_context ?? ''} onChange={(custom_context) => set({ custom_context })} hint="Anything else the AI should know about the organization." />
      </Stack>
    </Dialog>
  );
}
