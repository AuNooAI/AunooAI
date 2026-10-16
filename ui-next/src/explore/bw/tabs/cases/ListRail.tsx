import { useState } from 'react';
import {
  ActivityRow, ArticleCard, Banner, Button, Checkbox, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, FilterChipRow, Icon, Panel,
  Select, Skeleton, Stack, Text, TextField,
} from '@aunoo/ui';
import type { BWAlertEvent, BWIncident } from '@monolith/brandWatcherApi';
import { TitleLink } from '../../../feed/api';

export const STATUSES = ['open', 'investigating', 'contained', 'resolved', 'closed'] as const;
export const SEVERITIES = ['low', 'medium', 'high', 'critical'] as const;
export const STATUS_HELP: Record<string, string> = {
  open: 'New; evidence gathering hasn’t finished', investigating: 'Being worked', contained: 'No longer spreading; still watched',
  resolved: 'Dealt with; kept for the record', closed: 'Archived',
};
export const sevTone = (s: string): 'error' | 'warning' | 'muted' => (s === 'high' || s === 'critical' ? 'error' : s === 'medium' ? 'warning' : 'muted');
export const statusTone = (s: string): 'error' | 'warning' | 'info' | 'success' | 'muted' =>
  s === 'open' ? 'error' : s === 'investigating' ? 'warning' : s === 'contained' ? 'info' : s === 'resolved' ? 'success' : 'muted';
const ACTIVE = ['open', 'investigating', 'contained'];

function ago(iso?: string | null) {
  if (!iso) return '';
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  return d <= 0 ? 'today' : d === 1 ? 'yesterday' : `${d} days ago`;
}

export type Bulk = { status: string; severity: string; owner: string };

/** The incident list: alerts waiting for triage, status filter, case cards and bulk changes. */
export function ListRail(props: {
  incidents: BWIncident[];
  loading: boolean;
  onOpen: (id: number) => void;
  onNew: () => void;
  selected: Set<number>;
  setSelected: (s: Set<number>) => void;
  bulkBusy: boolean;
  applyBulk: (action: 'update' | 'delete', bulk: Bulk) => void;
  alertEvents: BWAlertEvent[];
  onAckAlert: (id: number) => void;
  onCaseAlert: (ev: BWAlertEvent) => void;
}) {
  const { incidents, loading, onOpen, onNew, selected, setSelected, bulkBusy, applyBulk, alertEvents, onAckAlert, onCaseAlert } = props;
  const [filter, setFilter] = useState<string>('active');
  const [bulk, setBulk] = useState<Bulk>({ status: '', severity: '', owner: '' });

  const count = (st: string) => (st === 'active' ? incidents.filter((i) => ACTIVE.includes(i.status)).length : st === 'all' ? incidents.length : incidents.filter((i) => i.status === st).length);
  const shown = filter === 'active' ? incidents.filter((i) => ACTIVE.includes(i.status)) : filter === 'all' ? incidents : incidents.filter((i) => i.status === filter);
  const toggle = (id: number, on: boolean) => {
    const next = new Set(selected);
    if (on) next.add(id);
    else next.delete(id);
    setSelected(next);
  };

  return (
    <Stack gap="lg">
      {alertEvents.length > 0 && (
        <Collapsible>
          <Banner
            tone="warning"
            icon="Bell"
            title={`${alertEvents.length} new ${alertEvents.length === 1 ? 'alert' : 'alerts'} to triage`}
            action={<CollapsibleTrigger variant="secondary">Show</CollapsibleTrigger>}
          />
          <CollapsibleContent>
            <Stack as="ul" gap="sm" label="Alerts to triage">
              {alertEvents.map((ev) => (
                <li key={ev.id}>
                  <Stack direction="row" justify="between" gap="sm">
                    <ActivityRow primary={ev.title} secondary={ev.brand_name ?? undefined} timestamp={(ev.created_at ?? '').slice(5, 16).replace('T', ' ')} dotTone={ev.severity === 'high' ? 'accent' : 'pending'} dotLabel={`${ev.severity} severity`} />
                    <Stack direction="row" gap="sm" wrap={false}>
                      <Button size="sm" variant="secondary" onClick={() => onCaseAlert(ev)}>Open case</Button>
                      <Button size="sm" variant="ghost" onClick={() => onAckAlert(ev.id)}>Dismiss</Button>
                    </Stack>
                  </Stack>
                </li>
              ))}
            </Stack>
          </CollapsibleContent>
        </Collapsible>
      )}

      <Panel
        title="Incidents"
        description="Cases with severity, status, owner, evidence and an audit trail."
        headerAside={<Button iconStart={<Icon name="Plus" size="sm" />} onClick={onNew}>New incident</Button>}
      >
        <Stack gap="md">
          <FilterChipRow
            label="Status"
            allLabel={`All ${count('all')}`}
            options={['active', ...STATUSES].map((st) => ({ value: st, label: `${st === 'active' ? 'Active' : st[0].toUpperCase() + st.slice(1)} ${count(st)}` }))}
            selected={filter === 'all' ? [] : [filter]}
            onChange={(v) => setFilter(v.filter((x) => x !== filter)[0] ?? 'all')}
            maxVisible={8}
          />

          {selected.size > 0 && (
            <Panel title={`${selected.size} selected`} headingLevel={3} headerAside={<Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>Clear</Button>}>
              <Stack gap="sm">
                <Stack direction="row" gap="sm">
                  <Select label="Status" hideLabel placeholder="Set status" options={STATUSES.map((s) => ({ value: s, label: s }))} value={bulk.status || undefined} onValueChange={(status) => setBulk({ ...bulk, status })} />
                  <Select label="Severity" hideLabel placeholder="Set severity" options={SEVERITIES.map((s) => ({ value: s, label: s }))} value={bulk.severity || undefined} onValueChange={(severity) => setBulk({ ...bulk, severity })} />
                  <TextField label="Owner" hideLabel placeholder="Set owner" value={bulk.owner} onChange={(owner) => setBulk({ ...bulk, owner })} />
                </Stack>
                <Stack direction="row" gap="sm">
                  <Button size="sm" disabled={bulkBusy || (!bulk.status && !bulk.severity && !bulk.owner.trim())} onClick={() => { applyBulk('update', bulk); setBulk({ status: '', severity: '', owner: '' }); }}>
                    {bulkBusy ? 'Applying…' : 'Apply'}
                  </Button>
                  <Button size="sm" variant="secondary" disabled={bulkBusy} onClick={() => applyBulk('delete', bulk)}>Delete</Button>
                </Stack>
                <Text variant="caption">Each change is written to the incident’s audit trail.</Text>
              </Stack>
            </Panel>
          )}

          {loading && !incidents.length ? <Skeleton variant="text" lines={5} /> : shown.length === 0 ? (
            <Text>{filter === 'all' ? 'No incidents yet.' : `No ${filter} incidents.`}</Text>
          ) : (
            <Stack as="ul" gap="sm" label="Incidents">
              {shown.map((inc) => (
                <ArticleCard
                  key={inc.id}
                  as="li"
                  variant="row"
                  headingLevel={3}
                  leading={<Checkbox label={<span className="visually-hidden">Select incident #{inc.id}</span>} checked={selected.has(inc.id)} onCheckedChange={(on) => toggle(inc.id, on)} />}
                  meta={`#${inc.id} · ${inc.brand_name} · updated ${ago(inc.updated_at)}`}
                  title={<TitleLink href={`#incident-${inc.id}`} onOpen={() => onOpen(inc.id)}>{inc.title}</TitleLink>}
                  tags={
                    <>
                      <Chip size="sm" tone={statusTone(inc.status)}>{inc.status}</Chip>
                      <Chip size="sm" tone={sevTone(inc.severity)}>Severity: {inc.severity}</Chip>
                      <Chip size="sm" tone="muted" icon={<Icon name="Lock" size="sm" />}>{inc.evidence_count ?? 0} evidence</Chip>
                      {inc.owner && <Chip size="sm" tone="muted">Owner: {inc.owner}</Chip>}
                    </>
                  }
                />
              ))}
            </Stack>
          )}
        </Stack>
      </Panel>
    </Stack>
  );
}
