import { useEffect, useState } from 'react';
import { Banner, Button, Dialog, DialogClose, Select, Skeleton, Stack, TabPanel, Tabs, Text, TextField } from '@aunoo/ui';
import { attachIncidentEvidence, createIncident, listIncidents, type BWIncident } from '@monolith/brandWatcherApi';
import { errorText } from '../../../shell';

/*
 * "Add to incident", shared by every Brand Watcher sub-tab (Dashboard, Articles, Incidents, Social,
 * Accounts). The server snapshots each item (content, engagement, risks, a checksum) into the
 * incident's evidence locker: POST /api/brand-watcher/incidents/{id}/evidence, after
 * POST /api/brand-watcher/incidents when a new incident is opened. No AI here.
 */

export type IncidentEvidenceKind = 'article' | 'alert_event' | 'account_profile' | 'social_post';

export interface IncidentSource {
  /** What the refs are; articles and social posts are both stored by article uri. Default 'article'. */
  kind?: IncidentEvidenceKind;
  /** One item… */
  ref?: string;
  /** …or several (an alert's evidence posts, say) */
  refs?: string[];
  label: string;
  /** Needed to open a new incident; without it the item can only go into an existing one */
  brandId: number | null;
}

export function AddToIncidentDialog({ source, onClose, notify, onDone }: {
  source: IncidentSource | null;
  onClose: () => void;
  notify: (m: string) => void;
  /** After a successful add, with the incident it went into */
  onDone?: (incidentId: number) => void;
}) {
  const [list, setList] = useState<BWIncident[] | null>(null);
  const [tab, setTab] = useState('existing');
  const [pick, setPick] = useState('');
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!source) return;
    setList(null);
    setPick('');
    setTitle('');
    setError(null);
    listIncidents().then(
      (l) => {
        const open = l.filter((i) => i.status !== 'closed' && i.status !== 'resolved');
        setList(open);
        setPick(open[0] ? String(open[0].id) : '');
        setTab(open.length ? 'existing' : 'new');
      },
      (e: unknown) => {
        setList([]);
        setTab('new');
        setError(`Open incidents didn’t load: ${errorText(e)}`);
      },
    );
  }, [source]);

  const refs = source ? (source.refs?.length ? source.refs : source.ref ? [source.ref] : []) : [];

  const attach = async () => {
    if (!source || !refs.length) return;
    setBusy(true);
    setError(null);
    try {
      let id = Number(pick);
      if (tab === 'new') {
        if (!source.brandId) throw new Error('This item has no single brand, so a new incident can’t be opened for it. Pick an existing incident, or pick one brand in the header first.');
        id = (await createIncident(source.brandId, title.trim(), undefined, 'high')).id;
      }
      for (const r of refs) await attachIncidentEvidence(id, { evidence_type: source.kind ?? 'article', source_ref: r });
      notify(`${refs.length > 1 ? `${refs.length} items` : 'Evidence'} added to incident #${id}`);
      onDone?.(id);
      onClose();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={!!source}
      onOpenChange={(o) => !o && onClose()}
      title="Add to incident"
      description={source?.label}
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" busy={busy} disabled={busy || !refs.length || (tab === 'existing' ? !pick : title.trim().length < 3)} onClick={() => void attach()}>
            {tab === 'existing' ? 'Add to incident' : 'Create and add'}
          </Button>
        </>
      }
    >
      <Stack gap="md">
        <Text variant="caption">
          {refs.length > 1 ? `${refs.length} items are` : 'The item is'} copied into the incident with its content, engagement and risks, and a checksum,
          so it survives the original being deleted and later changes show.
        </Text>
        {error && <Banner tone="error" title="Not added" description={error} />}
        {!list ? <Skeleton variant="text" lines={3} /> : (
          <Tabs label="Incident" stretch value={tab} onValueChange={setTab} items={[{ value: 'existing', label: `Open incidents (${list.length})` }, { value: 'new', label: 'New incident' }]}>
            <TabPanel value="existing">
              {list.length === 0 ? <Text>No open incidents. Open a new one instead.</Text> : (
                <Select
                  label="Incident"
                  fullWidth
                  placeholder="Pick an incident"
                  options={list.map((i) => ({ value: String(i.id), label: `#${i.id} ${i.title}`, description: `${i.brand_name} · ${i.severity} · ${i.status}` }))}
                  value={pick || undefined}
                  onValueChange={setPick}
                />
              )}
            </TabPanel>
            <TabPanel value="new">
              <TextField
                label="Incident title"
                value={title}
                onChange={setTitle}
                hint={source?.brandId ? 'At least 3 characters. Opened at high severity; change it on the Incidents tab.' : 'This item has no single brand, so it can only go into an existing incident.'}
              />
            </TabPanel>
          </Tabs>
        )}
      </Stack>
    </Dialog>
  );
}
