import { useEffect, useState } from 'react';
import { Banner, Chip, DonutChart, EmptyState, Grid, Panel, Skeleton, Stack, Stat, Table, Text } from '@aunoo/ui';
import { errorText } from '../../../../shell';
import { getCampaigns, getIOCs, type Campaign, type IOC } from '../api';
import type { ThreatCtx } from '../context';
import { iocTypeLabel } from '../labels';
import { LinkButton, ValueChips } from '../parts';
import { CampaignDialog } from './CampaignDialog';

/*
 * Indicators of compromise and active campaigns, as the old ThreatAnalysisTab. Indicators are what a
 * security team searches its own logs for: addresses, domains, file hashes, URLs.
 *
 * The old view counted "high confidence" over the first 100 indicators but showed it as a total, and
 * printed "null%" for an indicator with no confidence. Counts here say which slice they cover, and a
 * missing confidence says so.
 */

const COLORS = [1, 2, 3, 4, 5] as const;

export function Analysis(ctx: ThreatCtx) {
  const [iocs, setIocs] = useState<{ list: IOC[]; total: number } | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Campaign | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([getIOCs(), getCampaigns(true)]).then(
      ([i, c]) => {
        if (!live) return;
        setIocs({ list: i.data, total: i.total });
        setCampaigns(c.data);
      },
      (e) => live && setError(errorText(e)),
    );
    return () => {
      live = false;
    };
  }, []);

  if (error) return <Banner tone="error" title="Indicators and campaigns didn’t load" description={error} />;
  if (!iocs || !campaigns) return <Skeleton variant="block" size="card" />;

  const byType = Object.entries(iocs.list.reduce<Record<string, number>>((a, i) => ({ ...a, [i.indicator_type]: (a[i.indicator_type] ?? 0) + 1 }), {})).sort((a, b) => b[1] - a[1]);
  const rated = iocs.list.filter((i) => i.confidence !== null && i.confidence !== undefined);
  const high = rated.filter((i) => (i.confidence ?? 0) >= 80).length;
  const shown = [...iocs.list].sort((a, b) => (b.confidence ?? -1) - (a.confidence ?? -1)).slice(0, 25);
  const slice = iocs.total > iocs.list.length ? ` of the ${iocs.list.length} newest` : '';

  return (
    <>
      <Grid columns={4} label="Indicators and campaigns at a glance">
        <Stat label="Indicators" value={String(iocs.total)} />
        <Stat label="High confidence" value={rated.length ? String(high) : '—'} meta={rated.length ? `80% or more${slice}` : 'The AI gave no confidence for any indicator'} />
        <Stat label="Indicator types" value={String(byType.length)} />
        <Stat label="Active campaigns" value={String(campaigns.length)} />
      </Grid>

      <Grid columns="main-aside">
        <Panel title="Indicators" description={`What to look for in your own logs. ${iocs.total > shown.length ? `The ${shown.length} with the highest confidence of ${iocs.total}.` : ''}`}>
          {!shown.length ? <EmptyState icon="Target" title="No indicators yet">The AI records an indicator when an article names an address, domain, hash or URL tied to a threat.</EmptyState> : (
            <Table
              caption="Indicators of compromise"
              hideCaption
              rows={shown}
              rowKey={(i) => String(i.id)}
              columns={[
                { key: 'indicator_type', header: 'Type', render: (i) => iocTypeLabel(i.indicator_type) },
                { key: 'indicator_value', header: 'Value', wrap: true, render: (i) => <span className="threat-mono">{i.indicator_value}</span> },
                { key: 'confidence', header: 'Confidence', align: 'end', render: (i) => (i.confidence === null || i.confidence === undefined ? 'not given' : `${i.confidence}%`) },
                { key: 'is_active', header: 'State', render: (i) => (i.is_active ? 'active' : 'inactive') },
              ]}
            />
          )}
        </Panel>
        <Panel title="By type">
          <DonutChart
            title="Indicators by type"
            segments={byType.slice(0, 5).map(([t, n], k) => ({ id: t, label: iocTypeLabel(t), value: n, color: COLORS[k] }))}
            centerLabel={String(iocs.list.length)}
            emptyText="No indicators yet."
          />
        </Panel>
      </Grid>

      <Panel title="Active campaigns" description={`${campaigns.length} active. A campaign is a coordinated run of activity the AI grouped from several threats.`}>
        {!campaigns.length ? <Text>No active campaigns tracked.</Text> : (
          <ul className="threat-plainlist">
            {campaigns.map((c) => (
              <li key={c.id}>
                <Stack gap="sm">
                  <Stack direction="row" gap="sm">
                    <LinkButton onClick={() => setOpen(c)}>{c.name}</LinkButton>
                    <Chip tone="error" size="sm">Active</Chip>
                    {c.threat_actor_name && <Text as="span" variant="caption">{c.threat_actor_name}</Text>}
                  </Stack>
                  {c.description && <Text variant="caption">{c.description}</Text>}
                  <Stack direction="row" gap="sm"><ValueChips values={[...(c.target_countries ?? []).slice(0, 3), ...(c.target_industries ?? []).slice(0, 2)]} /></Stack>
                </Stack>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <CampaignDialog
        campaign={open}
        onClose={() => setOpen(null)}
        onArticles={(c) => {
          setOpen(null);
          ctx.showArticles({ campaign: { id: c.id, name: c.name } });
        }}
      />
    </>
  );
}
