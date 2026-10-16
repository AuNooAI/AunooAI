import { Banner, Chip, Grid, Panel, Stack, Table, Text, TextLink } from '@aunoo/ui';
import { CitedText } from '../components/CitedText';
import { CardExtras, ImpactLevel } from '../components/SignalsParts';
import { Disclosure } from '../components/Disclosure';
import { ViewState } from '../components/ViewState';
import { levelOf, type Payload } from '../lib/model';
import type { ViewProps } from './types';

const label = (v: unknown) => {
  const s = String(v ?? '');
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
};

export function MarketSignals({ analysis, tab }: ViewProps) {
  const data = analysis.data ?? {};
  const signals: Payload[] = Array.isArray(data.future_signals) ? data.future_signals : [];
  const risks: Payload[] = Array.isArray(data.risk_cards) ? data.risk_cards : [];
  const opportunities: Payload[] = Array.isArray(data.opportunity_cards) ? data.opportunity_cards : [];
  const quotes: Payload[] = Array.isArray(data.quotes) ? data.quotes : [];
  return (
    <ViewState
      analysis={analysis}
      generateLabel="Generate analysis"
      empty={{ icon: tab.icon, title: 'No signals yet', text: 'Generate the analysis to detect market signals for this topic.' }}
    >
      <Banner headingLevel={2} title="Market Signals & Strategic Risks" description="Signals with their likely impact and timing, then the risks and opportunities they create." />
      {signals.length > 0 && (
        <Panel title="Future signals">
          <Table
            caption="Future signals"
            hideCaption
            rowKey={(r) => String(r.signal ?? r.title)}
            rows={signals}
            columns={[
              {
                key: 'signal',
                header: 'Future Signal',
                rowHeader: true,
                wrap: true,
                render: (r) => (
                  <div>
                    <div>{String(r.signal ?? r.title ?? '')}</div>
                    <Text variant="caption" as="div"><CitedText text={r.description} /></Text>
                  </div>
                ),
              },
              // A coloured dot and the word (red high, amber medium, blue low), as the old table coloured it; a chip wrapped here
              { key: 'impact', header: 'Impact', render: (r) => <ImpactLevel value={r.impact} /> },
              { key: 'timeline', header: 'Timeline' },
              { key: 'confidence', header: 'Confidence', render: (r) => label(r.confidence) },
            ]}
          />
        </Panel>
      )}
      {(risks.length > 0 || opportunities.length > 0) && (
        <Grid columns={2} gap="md">
          <Panel title="Risks" headingLevel={3}>
            <Stack as="ul" gap="sm" label="Risks">
              {risks.map((r) => (
                <li key={r.title}>
                  {/* Severity comes lowercase from the prompt; the old page compared "High" and coloured every risk the same */}
                  <Banner
                    tone={levelOf(r.severity) === 'critical' || levelOf(r.severity) === 'high' ? 'error' : levelOf(r.severity) === 'medium' ? 'warning' : 'info'}
                    headingLevel={4}
                    icon="Warning"
                    title={`${r.title}${r.severity ? ` · ${label(r.severity)}` : ''}`}
                    description={<Stack gap="sm"><CitedText text={r.description} /><CardExtras card={r} kind="risk" /></Stack>}
                  />
                </li>
              ))}
              {risks.length === 0 && <Text variant="hint">No risks identified.</Text>}
            </Stack>
          </Panel>
          <Panel title="Opportunities" headingLevel={3}>
            <Stack as="ul" gap="sm" label="Opportunities">
              {opportunities.map((o) => (
                <li key={o.title}>
                  <Banner
                    tone="success"
                    headingLevel={4}
                    icon="Target"
                    title={`${o.title}${o.impact ? ` · ${label(o.impact)} impact` : ''}`}
                    description={<Stack gap="sm"><CitedText text={o.description} /><CardExtras card={o} kind="opportunity" /></Stack>}
                  />
                </li>
              ))}
              {opportunities.length === 0 && <Text variant="hint">No opportunities identified.</Text>}
            </Stack>
          </Panel>
        </Grid>
      )}
      {quotes.length > 0 && (
        <Panel title="In their words">
          <Stack as="ul" gap="md" label="Quotes">
            {quotes.map((q, i) => (
              <li key={`${i}-${q.text}`}>
                <Stack gap="sm">
                  <Stack direction="row" gap="sm">
                    <Chip size="sm" tone={q.quote_type === 'direct_quote' ? 'info' : 'warning'}>{q.quote_type === 'direct_quote' ? 'Source quote' : 'Auspex commentary'}</Chip>
                  </Stack>
                  <Text>“{q.text}”</Text>
                  {q.context && <Text variant="hint">{q.context}</Text>}
                  <Text variant="caption">
                    — {q.url ? <TextLink href={q.url} external>{q.source || 'Source'}</TextLink> : q.source}
                    {q.relevance ? ` · ${q.relevance}` : ''}
                  </Text>
                </Stack>
              </li>
            ))}
          </Stack>
        </Panel>
      )}
      <Disclosure dashboard="Market Signals & Strategic Risks" purpose="To identify market trends, risks, and opportunities" model={data.model_used} generatedAt={data.generated_at} />
    </ViewState>
  );
}
