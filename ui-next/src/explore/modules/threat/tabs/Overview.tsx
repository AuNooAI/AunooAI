import { Chip, DonutChart, EmptyState, Grid, Panel, Skeleton, Stack, StackedBars, Stat, Text } from '@aunoo/ui';
import type { SeverityLevel } from '../api';
import type { ThreatCtx } from '../context';
import { categoryLabel, SEVERITY_CHART, SEVERITY_LABELS, SEVERITY_LEVELS } from '../labels';
import { LinkButton, SeverityChip } from '../parts';

/*
 * The one-look state of things, as the old ThreatOverviewTab: counts, severity, the most common threat
 * types and the threats with the most coverage. Each figure opens the articles behind it.
 */
export function Overview(ctx: ThreatCtx) {
  const { stats, loading } = ctx;
  if (!stats) {
    return loading ? <Skeleton variant="block" size="card" /> : (
      <Panel title="Overview">
        <EmptyState icon="ShieldCheck" title="No threat data yet">
          Nothing has been filed yet. “Update” has the AI read collected articles and file the threats they describe.
        </EmptyState>
      </Panel>
    );
  }

  const severity = SEVERITY_LEVELS.map((l) => ({ level: l, count: stats.by_severity?.[l] ?? 0 }));
  const types = Object.entries(stats.by_type ?? {}).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const period = ctx.daysBack === 365 ? 'the last year' : `the last ${ctx.daysBack} days`;

  return (
    <>
      <Grid columns={3} label="Threats at a glance">
        <Stat label="Threats" value={String(stats.total_threats)} meta={`With coverage in ${period}`} />
        <Stat label="Threat actors" value={String(stats.total_actors)} meta="Groups and individuals the AI has named" />
        <Stat label="Articles" value={String(stats.total_articles)} meta={`${stats.recent_articles} of them in the last 7 days`} />
        <Stat label="New threats" value={String(stats.new_threats)} meta="First seen in the last 7 days" />
        <Stat label="Escalating" value={String(stats.escalating_count)} tone={stats.escalating_count ? 'error' : 'default'} meta="Coverage growing" />
        <Stat label="Declining" value={String(stats.declining_count)} tone={stats.declining_count ? 'success' : 'default'} meta="Coverage falling away" />
      </Grid>

      <Grid columns={3}>
        <Panel title="Severity" description="How serious the AI rated each threat. Pick a level to see its articles.">
          <Stack gap="md">
            <DonutChart
              title="Threats by severity"
              segments={severity.filter((s) => s.count > 0).map((s) => ({ id: s.level, label: SEVERITY_LABELS[s.level], value: s.count, color: SEVERITY_CHART[s.level] }))}
              centerLabel={String(stats.total_threats)}
              emptyText="No threats in this period."
            />
            <Stack direction="row" gap="sm">
              {severity.filter((s) => s.count > 0).map((s) => (
                <Chip key={s.level} tone="neutral" onClick={() => ctx.showArticles({ severity: s.level as SeverityLevel })} label={`Show articles about ${SEVERITY_LABELS[s.level]} threats`}>
                  {`${SEVERITY_LABELS[s.level]} (${s.count})`}
                </Chip>
              ))}
            </Stack>
          </Stack>
        </Panel>

        <Panel title="Threat types" description="The most common kinds of threat. Pick one to see its articles.">
          <Stack gap="md">
            <StackedBars
              title="Threats by type"
              series={[{ id: 'n', label: 'Threats', color: 1 }]}
              rows={types.map(([t, n]) => ({ id: t, label: categoryLabel(t), values: [n] }))}
              emptyText="No threats in this period."
            />
            <Stack direction="row" gap="sm">
              {types.map(([t, n]) => (
                <Chip key={t} tone="neutral" onClick={() => ctx.showArticles({ threatType: t })} label={`Show articles about ${categoryLabel(t)} threats`}>
                  {`${categoryLabel(t)} (${n})`}
                </Chip>
              ))}
            </Stack>
          </Stack>
        </Panel>

        <Panel title="Most covered threats" description="The threats with the most articles. Pick one to read them.">
          {!stats.top_threats?.length ? <Text>No threats in this period.</Text> : (
            <ul className="threat-plainlist">
              {stats.top_threats.slice(0, 6).map((t) => (
                <li key={t.id}>
                  <Stack gap="sm">
                    <LinkButton onClick={() => ctx.showArticles({ threat: { id: t.id, name: t.threat_name } })}>{t.threat_name}</LinkButton>
                    <Stack direction="row" gap="sm">
                      <SeverityChip level={t.severity_level} />
                      <Text as="span" variant="caption">
                        {[categoryLabel(t.threat_type), `${t.article_count} article${t.article_count === 1 ? '' : 's'}`, t.threat_actor_name ? `actor: ${t.threat_actor_name}` : null].filter(Boolean).join(' · ')}
                      </Text>
                    </Stack>
                  </Stack>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </Grid>
    </>
  );
}
