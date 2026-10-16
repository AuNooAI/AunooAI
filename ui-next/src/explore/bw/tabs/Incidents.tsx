import { useCallback, useEffect, useState } from 'react';
import {
  ActivityRow, Button, Checkbox, Dialog, DialogClose, Select, Skeleton, Stack, Text, TextArea, TextField,
} from '@aunoo/ui';
import {
  ackAlertEvent, createIncident, deleteIncident, listAlertEvents, listIncidents, updateIncident, type BWAlertEvent, type BWIncident,
} from '@monolith/brandWatcherApi';
import { errorText } from '../../../shell';
import type { BwContext } from '../context';
import { AddToIncidentDialog, type IncidentSource } from '../overlays/AddToIncidentDialog';
import { CaseFile } from './cases/CaseFile';
import { ListRail, SEVERITIES, type Bulk } from './cases/ListRail';
import { useIncidentCase, type IncidentCase } from './cases/useIncidentCase';

/*
 * Incident case management (old incidents/IncidentsWorkspace.tsx): alerts waiting for triage,
 * the case list, and one case at a time. Creating, editing and attaching evidence write straight
 * to /api/brand-watcher/incidents; only "Investigate with AI", translation and the report summary
 * call the AI.
 */

const STEPS: [string, string][] = [
  ['Open', 'Start a case from an alert, article or post, or from scratch.'],
  ['Investigate', 'The AI sweeps for coverage, checks who is spreading it and how credible it is.'],
  ['Accept', 'One click folds the AI’s findings into the case; reject anything off target.'],
  ['Assess', 'Coverage, reach, accounts and credibility in one view. Set the severity to match.'],
  ['Resolve', 'Close it and download the case file.'],
];

function SearchDialog({ c }: { c: IncidentCase }) {
  const s = c.search;
  return (
    <Dialog
      open={!!c.detail && s.open}
      onOpenChange={(open) => c.setSearch((x) => ({ ...x, open }))}
      title={`Add articles or posts to incident #${c.detail?.id ?? ''}`}
      size="lg"
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" disabled={!s.sel.size || s.busy} onClick={() => void c.attachSearchSelection()}>Add {s.sel.size || ''} selected</Button>
        </>
      }
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <TextField
            label="Search"
            hideLabel
            placeholder="Search titles and summaries, or paste a link"
            value={s.q}
            onChange={(q) => c.setSearch((x) => ({ ...x, q }))}
            onSubmit={() => void c.doAttachSearch()}
          />
          <Select label="Kind" hideLabel options={[{ value: 'all', label: 'News and social' }, { value: 'news', label: 'News' }, { value: 'social', label: 'Social' }]} value={s.kind} onValueChange={(kind) => c.setSearch((x) => ({ ...x, kind: kind as 'all' }))} />
          <Button disabled={s.busy || !s.q.trim()} onClick={() => void c.doAttachSearch()}>{s.busy ? 'Searching…' : 'Search'}</Button>
        </Stack>
        <Stack as="ul" gap="sm" label="Search results">
          {s.results.map((r) => (
            <li key={r.uri}>
              <Checkbox
                label={`${r.is_social ? r.platform || 'Social' : 'News'}: ${r.title || r.uri} · ${[r.news_source, r.author ? `@${r.author}` : null, (r.publication_date ?? '').slice(0, 10)].filter(Boolean).join(' · ')}`}
                checked={s.sel.has(r.uri)}
                onCheckedChange={(on) => c.setSearch((x) => {
                  const sel = new Set(x.sel);
                  if (on) sel.add(r.uri);
                  else sel.delete(r.uri);
                  return { ...x, sel };
                })}
              />
            </li>
          ))}
        </Stack>
        {s.searched && !s.busy && !s.results.length && <Text>Nothing matches in the last year of collected content.</Text>}
      </Stack>
    </Dialog>
  );
}

function ProfileDialog({ c }: { c: IncidentCase }) {
  const p = c.profilePick;
  const f = p.filter.trim().toLowerCase();
  const list = p.profiles.filter((x) => !f || `${x.handle} ${x.display_name ?? ''} ${x.platform}`.toLowerCase().includes(f));
  return (
    <Dialog
      open={!!c.detail && p.open}
      onOpenChange={(open) => c.setProfilePick((x) => ({ ...x, open }))}
      title={`Add an account profile to incident #${c.detail?.id ?? ''}`}
      footer={<DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>}
    >
      <Stack gap="md">
        <TextField label="Filter" hideLabel placeholder="Filter by handle, name or platform" value={p.filter} onChange={(filter) => c.setProfilePick((x) => ({ ...x, filter }))} />
        {!p.profiles.length ? <Text>No profiled accounts yet. Build profiles from the Social or Accounts tab first.</Text> : (
          <Stack as="ul" gap="sm" label="Profiled accounts">
            {list.map((x) => (
              <li key={x.id}>
                <Stack direction="row" justify="between" gap="sm">
                  <ActivityRow primary={`${x.display_name || `@${x.handle}`} (@${x.handle} · ${x.platform})`} secondary={[x.followers_count != null ? `${Number(x.followers_count).toLocaleString('en-GB')} followers` : null, x.summary || x.bio].filter(Boolean).join(' · ')} />
                  <Button size="sm" variant="secondary" onClick={() => void c.attachProfile(x)}>Add</Button>
                </Stack>
              </li>
            ))}
          </Stack>
        )}
      </Stack>
    </Dialog>
  );
}

export function Incidents(ctx: BwContext) {
  const { bw, notify, askConfirm } = ctx;
  const [incidents, setIncidents] = useState<BWIncident[]>([]);
  const [loading, setLoading] = useState(true);
  const [alerts, setAlerts] = useState<BWAlertEvent[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [create, setCreate] = useState<{ open: boolean; title: string; description: string; severity: string; brandId: string }>({ open: false, title: '', description: '', severity: 'medium', brandId: '' });
  const [attach, setAttach] = useState<IncidentSource | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    listIncidents().then(setIncidents, (e: unknown) => notify(`Incidents didn’t load: ${errorText(e)}`)).finally(() => setLoading(false));
  }, [notify]);
  const reloadAlerts = useCallback(() => {
    listAlertEvents(true, 20).then(setAlerts, () => setAlerts([]));
  }, []);
  useEffect(() => {
    reload();
    reloadAlerts();
  }, [reload, reloadAlerts]);

  const c = useIncidentCase({ reloadIncidents: reload, notify, askConfirm });

  const applyBulk = (action: 'update' | 'delete', bulk: Bulk) => {
    const ids = Array.from(selected);
    if (!ids.length) return;
    const run = async () => {
      setBulkBusy(true);
      try {
        for (const id of ids) {
          if (action === 'delete') {
            await deleteIncident(id);
            if (c.detail?.id === id) c.setDetail(null);
          } else {
            const updates: Record<string, string> = {};
            if (bulk.status) updates.status = bulk.status;
            if (bulk.severity) updates.severity = bulk.severity;
            if (bulk.owner.trim()) updates.owner = bulk.owner.trim();
            if (Object.keys(updates).length) await updateIncident(id, updates);
          }
        }
        setSelected(new Set());
        reload();
        notify(action === 'delete' ? `${ids.length} deleted` : `${ids.length} updated`);
      } catch (e) {
        notify(`Not done: ${errorText(e)}`);
      } finally {
        setBulkBusy(false);
      }
    };
    if (action === 'delete') {
      askConfirm({
        title: `Delete ${ids.length} ${ids.length === 1 ? 'incident' : 'incidents'}?`,
        message: 'Their timelines and evidence are deleted with them.',
        action: 'Delete',
        onConfirm: () => void run(),
      });
    } else void run();
  };

  const doCreate = async () => {
    const brandId = Number(create.brandId);
    if (!create.title.trim() || !brandId) return;
    try {
      const r = await createIncident(brandId, create.title.trim(), create.description.trim() || undefined, create.severity);
      setCreate((x) => ({ ...x, open: false }));
      reload();
      c.openIncident(r.id);
    } catch (e) {
      notify(`Not created: ${errorText(e)}`);
    }
  };

  const brands = bw.brands.filter((b) => b.enabled);

  return (
    <>
      {c.detail ? (
        <CaseFile key={c.detail.id} c={c} onBack={c.closeIncident} notify={notify} openSignals={ctx.openSignals} />
      ) : (
        <>
          <ListRail
            incidents={incidents}
            loading={loading}
            onOpen={c.openIncident}
            onNew={() => setCreate({ open: true, title: '', description: '', severity: 'medium', brandId: String(ctx.focusBrand?.id ?? brands[0]?.id ?? '') })}
            selected={selected}
            setSelected={setSelected}
            bulkBusy={bulkBusy}
            applyBulk={applyBulk}
            alertEvents={alerts}
            onAckAlert={(id) => void ackAlertEvent(id).then(reloadAlerts, (e: unknown) => notify(`Not dismissed: ${errorText(e)}`))}
            onCaseAlert={(ev) => setAttach({ kind: 'alert_event', ref: String(ev.id), label: ev.title, brandId: ev.brand_id })}
          />
          {!loading && incidents.length === 0 && (
            <Stack as="ul" gap="sm" label="How case management works">
              {STEPS.map(([step, text]) => <ActivityRow key={step} as="li" primary={step} secondary={text} dotTone="accent" />)}
            </Stack>
          )}
          {loading && !incidents.length && <Skeleton variant="text" lines={3} />}
        </>
      )}

      <SearchDialog c={c} />
      <ProfileDialog c={c} />
      <AddToIncidentDialog source={attach} onClose={() => setAttach(null)} notify={notify} onDone={(id) => { reload(); c.openIncident(id); }} />
      <Dialog
        open={create.open}
        onOpenChange={(open) => setCreate((x) => ({ ...x, open }))}
        title="New incident"
        footer={
          <>
            <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
            <Button size="lg" disabled={!create.title.trim() || !create.brandId} onClick={() => void doCreate()}>Create</Button>
          </>
        }
      >
        <Stack gap="md">
          <Select label="Brand" fullWidth options={brands.map((b) => ({ value: String(b.id), label: b.display_name }))} value={create.brandId || undefined} onValueChange={(brandId) => setCreate((x) => ({ ...x, brandId }))} />
          <TextField label="Title" value={create.title} onChange={(title) => setCreate((x) => ({ ...x, title }))} />
          <TextArea label="Description" hint="What is this incident? Leave it blank and the AI drafts one from the evidence." rows={3} value={create.description} onChange={(description) => setCreate((x) => ({ ...x, description }))} />
          <Select label="Severity" fullWidth options={SEVERITIES.map((s) => ({ value: s, label: s }))} value={create.severity} onValueChange={(severity) => setCreate((x) => ({ ...x, severity }))} />
        </Stack>
      </Dialog>
    </>
  );
}
