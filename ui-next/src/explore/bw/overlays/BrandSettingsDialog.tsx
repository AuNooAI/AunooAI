import { useState } from 'react';
import {
  Banner, Button, Checkbox, Chip, Dialog, DialogClose, Eyebrow, Grid, Icon, IconButton, PanelDivider, SettingRow, Stack, Switch, TagInput, Text, TextField,
} from '@aunoo/ui';
import {
  searchWikidata, setupBrandMonitoring, suggestKeywords, updateBrandConfig,
  type Brand, type BrandCreate, type SuggestionVerification,
} from '@monolith/brandWatcherApi';
import { errorText } from '../../../shell';
import type { BwContext } from '../context';

/*
 * Add, edit, enable, delete and pick the primary brand, as the old Brand Configuration modal did.
 * "Suggest keywords" asks the AI and checks people and firms against Wikidata. Saving can also set
 * up the "Brand Monitoring <name>" topic and keyword group that collects the brand's articles.
 */

type Form = Partial<BrandCreate>;
type KwField = 'brand_keywords' | 'product_keywords' | 'people_keywords' | 'competitor_keywords';
const KW: [KwField, string][] = [['brand_keywords', 'Brand keywords'], ['product_keywords', 'Product keywords'], ['people_keywords', 'People keywords'], ['competitor_keywords', 'Competitor keywords']];

function verifiedHint(v: SuggestionVerification | null, field: KwField, tags: string[]) {
  if (!v?.available) return undefined;
  const list = field === 'people_keywords' ? v.people : field === 'competitor_keywords' ? v.competitors : undefined;
  if (!list?.length) return undefined;
  const ok = list.filter((x) => x.verified && tags.includes(x.name)).map((x) => x.name);
  const not = list.filter((x) => !x.verified && tags.includes(x.name)).map((x) => x.name);
  return [ok.length && `Checked on Wikidata: ${ok.join(', ')}.`, not.length && `Suggested by the AI, not found on Wikidata: ${not.join(', ')}.`].filter(Boolean).join(' ') || undefined;
}

export function BrandSettingsDialog({ open, onOpenChange, ctx }: { open: boolean; onOpenChange: (o: boolean) => void; ctx: BwContext }) {
  const { bw, notify, askConfirm } = ctx;
  const [form, setForm] = useState<Form>({});
  const [editing, setEditing] = useState<number | null>(null);
  const [verification, setVerification] = useState<SuggestionVerification | null>(null);
  const [qid, setQid] = useState<string | null>(null);
  const [wikidataIds, setWikidataIds] = useState<string[]>([]);
  const [monitor, setMonitor] = useState(true);
  const [busy, setBusy] = useState<null | 'suggest' | 'save'>(null);
  const [status, setStatus] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  const reset = () => {
    setForm({});
    setEditing(null);
    setVerification(null);
    setQid(null);
    setWikidataIds([]);
    setMonitor(true);
  };

  const edit = (b: Brand) => {
    setEditing(b.id);
    setForm({
      name: b.name, display_name: b.display_name, description: b.description || '', color: b.color || '',
      brand_keywords: b.brand_keywords || [], product_keywords: b.product_keywords || [], people_keywords: b.people_keywords || [], competitor_keywords: b.competitor_keywords || [],
    });
    const ids: string[] = (b.config as { wikidata_ids?: string[] } | undefined)?.wikidata_ids ?? [];
    setVerification(null);
    setQid(ids[0] ?? null);
    setWikidataIds(ids);
    setMonitor(false);
  };

  const suggest = async (qidOverride?: string) => {
    const name = form.display_name?.trim();
    if (!name) return;
    setBusy('suggest');
    try {
      const s = await suggestKeywords(name, form.description || undefined, { qid: qidOverride ?? qid ?? undefined });
      const merge = (a: string[] | undefined, b: string[]) => [...new Set([...(a ?? []), ...b])];
      setForm((f) => ({
        ...f,
        brand_keywords: merge(f.brand_keywords, s.brand_keywords), product_keywords: merge(f.product_keywords, s.product_keywords),
        people_keywords: merge(f.people_keywords, s.people_keywords), competitor_keywords: merge(f.competitor_keywords, s.competitor_keywords),
      }));
      const v = s.verification ?? null;
      setVerification(v);
      if (v?.available && v.brand?.matched && v.brand.qid) {
        const next = v.brand.qid;
        // Replace the last suggested entity instead of piling them up
        setWikidataIds((ids) => [...ids.filter((x) => x !== qid && x !== next), next]);
        setQid(next);
      }
    } catch (e) {
      notify(`No suggestions: ${errorText(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const changeEntity = async () => {
    const name = form.display_name?.trim();
    if (!name) return;
    setQid(null);
    try {
      const { candidates } = await searchWikidata(name);
      setVerification((v) => ({ ...(v ?? { available: true }), available: true, brand: { matched: false, candidates } }));
    } catch (e) {
      notify(`Wikidata search failed: ${errorText(e)}`);
    }
  };

  const save = async () => {
    setBusy('save');
    setStatus(null);
    try {
      let id: number;
      const kw = { brand_keywords: form.brand_keywords ?? [], product_keywords: form.product_keywords, people_keywords: form.people_keywords, competitor_keywords: form.competitor_keywords };
      if (editing) {
        await bw.updateBrand(editing, { display_name: form.display_name, description: form.description, color: form.color, ...kw });
        id = editing;
      } else {
        const created = await bw.createBrand({
          name: form.name || (form.display_name ?? '').toLowerCase().replace(/[^a-z0-9]+/g, '-'),
          display_name: form.display_name ?? '', description: form.description, color: form.color, ...kw,
        });
        id = created.id;
      }
      // The config PUT replaces keys wholesale, so the entity list is written in full (empty = removed)
      const before: string[] = ((editing ? bw.brands.find((b) => b.id === editing)?.config : undefined) as { wikidata_ids?: string[] } | undefined)?.wikidata_ids ?? [];
      const changed = before.length !== wikidataIds.length || before.some((q, i) => q !== wikidataIds[i]);
      if (verification?.available || changed) {
        await updateBrandConfig(id, {
          wikidata_ids: wikidataIds,
          ...(verification?.available ? {
            verified_entities: {
              brand: verification.brand ? { qid: verification.brand.qid, label: verification.brand.label, description: verification.brand.description } : { qid },
              people: verification.people ?? [], competitors: verification.competitors ?? [], retrieved_at: verification.retrieved_at,
            },
          } : {}),
        }).catch((e: unknown) => notify(`Brand saved, but the Wikidata links weren’t: ${errorText(e)}`));
      }
      if (monitor) {
        try {
          const r = await setupBrandMonitoring(id);
          setStatus({
            tone: 'success',
            text: `Topic “${r.topic_name}” ${r.topic_created ? 'created' : 'already existed'}. Keyword group “${r.group_name}” ${r.group_created ? 'created' : 'updated'} with ${r.keywords_added} keywords.`,
          });
        } catch (e) {
          setStatus({ tone: 'error', text: `Brand saved, but setting up collection failed: ${errorText(e)}` });
        }
      } else {
        notify(`Brand “${form.display_name}” saved`);
      }
      reset();
    } catch (e) {
      setStatus({ tone: 'error', text: `Not saved: ${errorText(e)}` });
    } finally {
      setBusy(null);
    }
  };

  const del = (b: Brand) =>
    askConfirm({
      title: `Delete ${b.display_name}?`,
      message: 'This removes the brand, its monitoring topic and its keyword group. Articles already collected stay in the database.',
      action: 'Delete brand',
      onConfirm: () => void bw.deleteBrand(b.id, true).then(() => notify(`${b.display_name} deleted`), (e: unknown) => notify(`Not deleted: ${errorText(e)}`)),
    });

  const v = verification;
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) reset();
        onOpenChange(o);
      }}
      title="Brand settings"
      footer={<DialogClose><Button variant="secondary" size="lg">Close</Button></DialogClose>}
    >
      <Stack gap="lg">
        {status && <Banner tone={status.tone} title={status.tone === 'success' ? 'Saved' : 'Something went wrong'} description={status.text} />}
        <Stack gap="sm">
          <Eyebrow as="h3">Tracked brands</Eyebrow>
          {bw.brands.length === 0 && <Text>No brands yet. Add one below.</Text>}
          <Stack as="ul" gap="sm" label="Tracked brands">
            {bw.brands.map((b) => (
              <li key={b.id}>
                <SettingRow
                  title={`${b.display_name}${b.is_primary ? ' (primary)' : ''}`}
                  description={(b.brand_keywords ?? []).join(', ') || 'No keywords'}
                  actions={
                    <Stack direction="row" gap="sm" wrap={false}>
                      <IconButton
                        icon={<Icon name="Star" size="sm" />}
                        label={b.is_primary ? `${b.display_name} is the primary brand` : `Make ${b.display_name} the primary brand`}
                        disabled={b.is_primary}
                        onClick={() => void bw.setPrimary(b.id).catch((e: unknown) => notify(`Not changed: ${errorText(e)}`))}
                      />
                      <Switch label={<span className="visually-hidden">{b.display_name} on</span>} checked={b.enabled} onCheckedChange={() => void bw.toggleBrand(b.id).catch((e: unknown) => notify(`Not changed: ${errorText(e)}`))} />
                      <IconButton icon={<Icon name="PencilSimple" size="sm" />} label={`Edit ${b.display_name}`} onClick={() => edit(b)} />
                      <IconButton icon={<Icon name="Trash" size="sm" />} label={`Delete ${b.display_name}`} onClick={() => del(b)} />
                    </Stack>
                  }
                />
              </li>
            ))}
          </Stack>
        </Stack>

        <PanelDivider />

        <Stack gap="md">
          <Eyebrow as="h3">{editing ? `Edit ${form.display_name ?? 'brand'}` : 'Add a brand'}</Eyebrow>
          <Grid columns={2} stackAt="small" gap="md">
            <TextField label="Name" value={form.display_name ?? ''} onChange={(display_name) => setForm({ ...form, display_name })} placeholder="e.g. Apple Inc" />
            <TextField label="Colour" value={form.color ?? ''} onChange={(color) => setForm({ ...form, color })} placeholder="#2563eb" hint="Used in charts." />
          </Grid>
          <TextField label="Description" value={form.description ?? ''} onChange={(description) => setForm({ ...form, description })} placeholder="What the company does" />
          <div>
            <Button variant="secondary" iconStart={<Icon name="Sparkle" size="sm" />} disabled={!form.display_name?.trim() || busy !== null} onClick={() => void suggest()}>
              {busy === 'suggest' ? 'Suggesting…' : 'Suggest keywords'}
            </Button>
          </div>

          {v && (v.available === false ? (
            <Banner tone="warning" title="Wikidata check unavailable" description="The suggestions couldn’t be checked." />
          ) : v.brand?.matched ? (
            <Banner
              tone="success"
              title={`Matched on Wikidata: ${v.brand.label}`}
              description={`${v.brand.description ?? ''}${v.retrieved_at ? ` (checked ${v.retrieved_at})` : ''}`}
              action={<Button variant="secondary" size="sm" onClick={() => void changeEntity()}>Wrong match?</Button>}
            />
          ) : v.brand?.candidates?.length ? (
            <Stack gap="sm">
              <Text>Several Wikidata entries match “{form.display_name}”. Pick the right one so people and firms can be checked:</Text>
              <Stack direction="row" gap="sm">
                {v.brand.candidates.map((c) => (
                  <Button key={c.qid} size="sm" variant="secondary" disabled={busy !== null} onClick={() => { setQid(c.qid); void suggest(c.qid); }}>
                    {c.label}{c.description ? `: ${c.description}` : ''} ({c.qid})
                  </Button>
                ))}
              </Stack>
              <Text variant="caption">None of these? The suggestions stay unchecked.</Text>
            </Stack>
          ) : (
            <Banner tone="warning" title="Not found on Wikidata" description={`No entry matches “${form.display_name}”, so the suggestions are unchecked.`} />
          ))}

          {wikidataIds.length > 0 && (
            <Stack gap="sm">
              <Text variant="label" as="span">Wikidata entries</Text>
              <Stack direction="row" gap="sm">
                {wikidataIds.map((q) => (
                  <Chip key={q} size="sm" tone="success" icon={<Icon name="X" size="sm" />} label={`Remove ${q}`} onClick={() => { setWikidataIds((ids) => ids.filter((x) => x !== q)); if (qid === q) setQid(null); }}>
                    {q === v?.brand?.qid && v.brand.label ? `${v.brand.label} (${q})` : q}
                  </Chip>
                ))}
              </Stack>
              <Text variant="caption">Used to match articles to this brand. Remove a wrong one, then suggest keywords again to pick the right one.</Text>
            </Stack>
          )}

          {KW.map(([field, label]) => (
            <TagInput
              key={field}
              label={label}
              tags={(form[field] as string[] | undefined) ?? []}
              onChange={(tags) => setForm({ ...form, [field]: tags })}
              hint={verifiedHint(v, field, (form[field] as string[] | undefined) ?? [])}
            />
          ))}

          <Checkbox
            label={editing ? 'Update the monitoring topic and keyword group' : 'Create a monitoring topic and keyword group'}
            checked={monitor}
            onCheckedChange={setMonitor}
          />
          <Text variant="caption">
            {editing ? 'Refreshes' : 'Creates'} the “Brand Monitoring {form.display_name || '…'}” topic and its keyword group, which collect this brand’s articles.
          </Text>
          <Stack direction="row" gap="sm">
            <Button disabled={!form.display_name?.trim() || busy !== null} onClick={() => void save()}>{busy === 'save' ? 'Saving…' : editing ? 'Save brand' : 'Add brand'}</Button>
            {editing && <Button variant="ghost" onClick={reset}>Cancel edit</Button>}
          </Stack>
        </Stack>
      </Stack>
    </Dialog>
  );
}
