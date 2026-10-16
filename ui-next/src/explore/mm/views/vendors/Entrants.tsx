import { useState } from 'react';
import { Banner, Button, Icon, Panel, Stack, Table, Text } from '@aunoo/ui';
import { discoverCandidates, type CandidateVendor, type DiscoveryResult } from '@monolith/marketMonitorApi';
import { errorText } from '../../../../shell';
import type { MmContext } from '../../context';
import { Missing } from '../../shared/SortTable';

/*
 * New entrants, as the old segment: scans funding articles already collected for companies that
 * aren't in the registry. It costs nothing external, but it writes its proposals to the review
 * queue, so it runs only from the button. Results are proposals, not additions.
 */
export function Entrants({ ctx, onChanged }: { ctx: MmContext; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DiscoveryResult | null>(null);

  const scan = async () => {
    setBusy(true);
    try {
      const r = await discoverCandidates(ctx.marketId, 30, false);
      setResult(r);
      if (!r.error) ctx.notify(`Scanned ${r.scanned} articles: ${r.candidates} candidates.`);
      onChanged();
    } catch (e) {
      ctx.notify(`Scan failed: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack gap="lg">
      <Panel title="New entrants" description="Scans the funding articles already collected for companies not in the registry. Results are proposals for review, not additions.">
        <Stack gap="sm">
          <div>
            <Button iconStart={<Icon name="MagnifyingGlass" size="sm" />} busy={busy} disabled={busy} onClick={() => void scan()}>Scan the last 30 days</Button>
          </div>
          {result && !result.error && (
            <Text variant="caption">
              Scanned {result.scanned} articles{result.below_alignment_floor ? `, and skipped ${result.below_alignment_floor} below the relevance floor` : ''}.
            </Text>
          )}
          {result?.error && <Banner tone="warning" title="The scan didn’t run" description={result.error} />}
        </Stack>
      </Panel>
      {result && !result.error && (result.proposals.length ? (
        <Table<CandidateVendor>
          caption="Companies found outside the registry"
          rows={result.proposals}
          rowKey={(c) => c.name}
          columns={[
            { key: 'name', header: 'Company', rowHeader: true },
            { key: 'amount_musd', header: 'Raised', align: 'end', render: (c) => (c.amount_musd !== null ? `$${c.amount_musd}M` : <Missing />) },
            { key: 'round', header: 'Round', render: (c) => c.round ?? <Missing /> },
            { key: 'mentions', header: 'Seen in', render: (c) => `${c.mentions} article${c.mentions === 1 ? '' : 's'}` },
            { key: 'source', header: 'Source', wrap: true, render: (c) => [c.news_source, c.article_title].filter(Boolean).join(': ') || <Missing /> },
          ]}
        />
      ) : <Text>No companies found outside the registry.</Text>)}
    </Stack>
  );
}
