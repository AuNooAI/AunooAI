import { useCallback, useEffect, useState } from 'react';
import { ReportSections } from '../../common/ReportSections';
import {
  Banner, Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, EmptyState, Grid, Icon, Panel, Skeleton, Stack, Stat, Text,
} from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import type { OverviewStats } from '@monolith/geopoliticalHotspotsApi';
import { api, errorText } from '../../../../shell';
import { download } from '../../../feed/api';
import { HotspotRow } from './HotspotRow';
import { RISK_LABEL, RISK_ORDER, RISK_TONE, cap, fmtDateTime } from '../labels';
import '../geo.css';

/*
 * The AI briefing on the hotspots, as the old Insights tab: the latest stored briefing, its earlier
 * versions, and a button to write a new one (POST /generate-narrative, one model call over the
 * current hotspot figures). Opening the tab only reads what's stored.
 *
 * The old key-figures strip listed the top categories from today's figures next to a briefing that
 * may be weeks old; it now uses the categories the briefing itself was written from.
 */

interface Narrative {
  id: number;
  narrative_text: string;
  executive_summary: string | null;
  regional_analysis: string | null;
  emerging_threats: string | null;
  outlook: string | null;
  hotspot_count: number;
  article_count: number;
  top_regions: string[] | null;
  top_categories: string[] | null;
  risk_breakdown: Record<string, number> | null;
  model_used: string | null;
  generated_at: string | null;
}
interface NarrativeSummary {
  id: number;
  executive_summary: string | null;
  hotspot_count: number;
  article_count: number;
  model_used: string | null;
  generated_at: string | null;
}

const sectionsOf = (n: Narrative) => {
  const out: { title: string; text: string }[] = [];
  if (n.executive_summary) out.push({ title: 'Executive summary', text: n.executive_summary });
  if (n.regional_analysis) out.push({ title: 'Regional analysis', text: n.regional_analysis });
  if (n.emerging_threats) out.push({ title: 'Emerging threats', text: n.emerging_threats });
  if (n.outlook) out.push({ title: 'Strategic outlook', text: n.outlook });
  if (!out.length && n.narrative_text) out.push({ title: 'Analysis', text: n.narrative_text });
  return out;
};

function toMarkdown(n: Narrative) {
  const rb = n.risk_breakdown ?? {};
  return [
    '# Strategic intelligence briefing: geopolitical hotspots',
    '',
    `Written: ${fmtDateTime(n.generated_at)} · Model: ${n.model_used || 'unknown'} · ${n.hotspot_count} hotspots · ${n.article_count} articles`,
    '',
    ...sectionsOf(n).flatMap((s) => [`## ${s.title}`, '', s.text, '']),
    '## Key figures',
    '',
    `- Top regions: ${n.top_regions?.join(', ') || 'none'}`,
    `- Top categories: ${n.top_categories?.join(', ') || 'none'}`,
    `- Risk: ${RISK_ORDER.map((r) => `${RISK_LABEL[r]} ${rb[r] || 0}`).join(', ')}`,
    '',
    '*Written by AI from collected news; it may contain errors. Check the sources before acting on it.*',
    '',
  ].join('\n');
}

export function Insights({ stats, model, notify, askConfirm, onHotspot }: {
  stats: OverviewStats | null;
  model: string;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
  onHotspot: (id: number) => void;
}) {
  const [narrative, setNarrative] = useState<Narrative | null | undefined>(undefined);
  const [history, setHistory] = useState<NarrativeSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [writing, setWriting] = useState(false);

  const load = useCallback(() => {
    setError(null);
    api<Narrative | null>('/api/geopolitical-hotspots/narrative').then((n) => setNarrative(n ?? null), (e) => { setNarrative(null); setError(errorText(e)); });
    api<NarrativeSummary[]>('/api/geopolitical-hotspots/narratives?limit=5').then((h) => setHistory(Array.isArray(h) ? h : []), () => setHistory([]));
  }, []);
  useEffect(() => load(), [load]);

  const noHotspots = !stats || stats.total_hotspots === 0;
  const write = () =>
    askConfirm({
      title: narrative ? 'Write a new briefing with AI?' : 'Write a briefing with AI?',
      message: `The AI (${model}) reads the current hotspot figures (${stats?.total_hotspots ?? 0} hotspots) and writes a summary, regional analysis, emerging threats and an outlook. It takes up to a minute. Earlier briefings are kept in the history.`,
      action: 'Write the briefing',
      onConfirm: async () => {
        setWriting(true);
        setError(null);
        try {
          await api('/api/geopolitical-hotspots/generate-narrative', { method: 'POST', json: { model } });
          notify('New briefing written');
          load();
        } catch (e) {
          setError(`The briefing wasn’t written: ${errorText(e)}`);
        } finally {
          setWriting(false);
        }
      },
    });

  const header = (
    <Panel
      title="Strategic intelligence briefing"
      description={narrative ? `Written ${fmtDateTime(narrative.generated_at)} by ${narrative.model_used || 'an unknown model'}, from ${narrative.hotspot_count} hotspots and ${narrative.article_count} articles.` : 'An AI briefing on the hotspot figures: summary, regional analysis, emerging threats and outlook.'}
      headerAside={
        <Stack direction="row" gap="sm">
          {narrative && (
            <Button variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} onClick={() => download(`geopolitical-briefing-${(narrative.generated_at ?? '').slice(0, 10) || 'latest'}.md`, toMarkdown(narrative))}>
              Download
            </Button>
          )}
          <Button iconStart={<Icon name="Sparkle" size="sm" />} disabled={writing || noHotspots} onClick={write}>
            {writing ? 'Writing…' : narrative ? 'Write a new briefing' : 'Write a briefing'}
          </Button>
        </Stack>
      }
    >
      {error && <Banner tone="error" title="Something went wrong" description={error} />}
    </Panel>
  );

  if (narrative === undefined) return <>{header}<Skeleton variant="block" size="card" /></>;
  if (!narrative) {
    return (
      <>
        {header}
        <Panel title="No briefing yet">
          <EmptyState icon="Sparkle" title="No briefing written yet">
            {noHotspots ? 'Read some articles for hotspots first (Update hotspots), then write a briefing.' : 'Write one with the button above. It reads the current hotspot figures.'}
          </EmptyState>
        </Panel>
      </>
    );
  }

  const rb = narrative.risk_breakdown ?? {};
  return (
    <>
      {header}
      <Grid columns={4} gap="sm">
        <Stat label="Hotspots" value={narrative.hotspot_count.toLocaleString()} meta="when written" />
        <Stat label="Articles" value={narrative.article_count.toLocaleString()} />
        <Stat label="Critical and high risk" value={((rb.critical || 0) + (rb.high || 0)).toLocaleString()} tone={(rb.critical || 0) > 0 ? 'error' : 'default'} />
        <Stat label="Regions" value={(narrative.top_regions?.length ?? 0).toLocaleString()} meta={narrative.top_regions?.slice(0, 3).join(', ')} />
      </Grid>
      <Panel title="What it was written from">
        <Stack gap="sm">
          <Stack direction="row" gap="sm">
            {RISK_ORDER.filter((r) => (rb[r] || 0) > 0).map((r) => <Chip key={r} size="sm" tone={RISK_TONE[r]}>{`${RISK_LABEL[r]}: ${rb[r]}`}</Chip>)}
          </Stack>
          {narrative.top_categories?.length ? <Text variant="caption">{`Top categories: ${narrative.top_categories.slice(0, 5).map(cap).join(', ')}`}</Text> : null}
          {narrative.top_regions?.length ? <Text variant="caption">{`Top regions: ${narrative.top_regions.slice(0, 5).join(', ')}`}</Text> : null}
        </Stack>
      </Panel>
      <Panel title="The briefing">
        <ReportSections idPrefix="geo-briefing" sections={sectionsOf(narrative).map((s) => ({ title: s.title, content: s.text }))} />
      </Panel>
      {stats && stats.top_hotspots.length > 0 && (
        <Panel title="Where to look first" description="The most intense hotspots now.">
          <Grid columns={3} as="ul" gap="sm" label="Most intense hotspots">
            {stats.top_hotspots.slice(0, 6).map((h, i) => <li key={h.id}><HotspotRow rank={i + 1} hotspot={h} onOpen={() => onHotspot(h.id)} /></li>)}
          </Grid>
        </Panel>
      )}
      <Text variant="caption">This briefing was written by AI ({narrative.model_used || 'unknown model'}) from collected news and may contain errors. Check the sources before acting on it.</Text>
      {history.length > 1 && (
        <Collapsible>
          <CollapsibleTrigger variant="ghost" className="geo-wrap-trigger">{`Earlier briefings (${history.length})`}</CollapsibleTrigger>
          <CollapsibleContent>
            <Stack as="ul" gap="md" label="Earlier briefings">
              {history.map((h) => (
                <li key={h.id}>
                  <Stack gap="sm">
                    <Text variant="label">{`${fmtDateTime(h.generated_at)}${h.id === narrative.id ? ' (shown above)' : ''} · ${h.hotspot_count} hotspots`}</Text>
                    <Text variant="caption">{h.executive_summary ? (h.executive_summary.length > 400 ? `${h.executive_summary.slice(0, 400)}…` : h.executive_summary) : 'No summary.'}</Text>
                  </Stack>
                </li>
              ))}
            </Stack>
          </CollapsibleContent>
        </Collapsible>
      )}
    </>
  );
}
