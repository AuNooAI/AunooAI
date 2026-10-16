import { useEffect, useState } from 'react';
import { useToasts } from '@aunoo/shell';
import {
  Banner,
  Button,
  EmptyState,
  Eyebrow,
  Grid,
  Icon,
  type IconName,
  LineItems,
  Meter,
  NewsTicker,
  type NewsTickerItem,
  Panel,
  Skeleton,
  Stack,
  Stat,
  Chip,
  TextLink,
} from '@aunoo/ui';
import { AppShell } from '../shell';
import { useHeadlines, useOperations, type Health } from './useOperations';
import { NewsTickerSettings } from './NewsTickerSettings';
import { useTickerSettings } from './tickerSettings';
import { ClockSettings } from './ClockSettings';
import { PageSettings } from './PageSettings';
import { usePageLayout, type MetricId } from './pageLayout';

const num = new Intl.NumberFormat('en-US');
const dec = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const EMPTY = '—';

/** Re-renders every second with the current time. */
function useNow() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

function formatUptime(totalSeconds: number) {
  const d = Math.floor(totalSeconds / 86400);
  const h = Math.floor((totalSeconds % 86400) / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  return `${d}d ${h}h ${m}m`;
}

/** Overall status from /health/detailed: healthy or degraded (anything else counts as a problem). */
// Green, amber and red as on the old page (the design system's status pill has no red, so chips are used)
type Tone = 'success' | 'warning' | 'error';
const STATUS: Record<string, { label: string; tone: Tone }> = {
  healthy: { label: 'Healthy', tone: 'success' },
  degraded: { label: 'Degraded', tone: 'warning' },
  warning: { label: 'Warning', tone: 'warning' },
  critical: { label: 'Critical', tone: 'error' },
};
/** A usage meter's colour: green below 75%, amber from 75%, red from 90%, as the old progress bars */
const usageTone = (pct: number) => (pct >= 90 ? 'error' : pct >= 75 ? 'warning' : 'success');

const API_LABELS: Record<string, string> = { collector: 'News collector', ai_provider: 'AI provider', firecrawl: 'Firecrawl' };

const when = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : EMPTY;

function PanelTitle({ icon, children }: { icon: IconName; children: React.ReactNode }) {
  return (
    <>
      <Icon name={icon} size="sm" /> {children}
    </>
  );
}

export function OperationsHQ() {
  const now = useNow();
  const [loadedAt] = useState(() => Date.now());
  const pageLayout = usePageLayout();
  const { sections, metricOrder, hiddenMetrics, clocks } = pageLayout.layout;
  const [clockSettingsOpen, setClockSettingsOpen] = useState(false);
  const [tickerSettingsOpen, setTickerSettingsOpen] = useState(false);
  const [ticker, setTicker] = useTickerSettings();
  const [refreshedAt, setRefreshedAt] = useState(loadedAt);

  // Auto-refresh: quietly reload the headlines on the chosen interval
  useEffect(() => {
    if (ticker.refresh === 'off') return;
    const t = window.setInterval(() => setRefreshedAt(Date.now()), Number(ticker.refresh) * 60000);
    return () => window.clearInterval(t);
  }, [ticker.refresh]);

  const headlines = useHeadlines(Number(ticker.count), ticker.range, refreshedAt);
  const tickerItems: NewsTickerItem[] = (headlines ?? []).map((h) => {
    const published = h.published;
    const today = published && published.toDateString() === new Date().toDateString();
    return {
      id: h.id,
      title: h.title,
      href: h.href,
      source: ticker.showSource ? h.source : undefined,
      // Many feeds give only a date (midnight), so show the time just for today's items
      time:
        ticker.showTime && published
          ? today && (published.getHours() || published.getMinutes())
            ? published.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
            : published.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
          : undefined,
      dateTime: published?.toISOString(),
    };
  });
  const { stats, health, error, loadedAt: healthAt } = useOperations();
  const { toasts, notify } = useToasts();

  const uptime = health ? formatUptime(Math.floor(health.uptime.seconds) + Math.max(0, Math.floor((now.getTime() - healthAt) / 1000))) : EMPTY;
  const status = health ? (STATUS[health.status] ?? { label: health.status, tone: 'warning' as Tone }) : null;
  // Each tile links where the old page's tiles did
  const totals: { id: string; label: string; value?: number; icon: IconName; href: string; link: string }[] = [
    { id: 'articles', label: 'Total articles', value: stats?.total_articles, icon: 'Newspaper', href: '/database-editor', link: 'Database Editor' },
    { id: 'today', label: 'Articles in the last 24h', value: stats?.articles_today, icon: 'TrendUp', href: '/gather', link: 'Gather' },
    { id: 'keywords', label: 'Keyword groups', value: stats?.keyword_groups, icon: 'Tag', href: '/gather#keywords', link: 'Keyword groups' },
    { id: 'topics', label: 'Topics', value: stats?.topics, icon: 'Folder', href: '/explore', link: 'Explore' },
  ];

  const metricPanels = health ? panels(health) : null;
  function panels(h: Health): Record<MetricId, React.ReactNode> {
  const { cpu } = h;
  // memory and disk come back as { error } when the probe fails
  const memory = 'process' in h.memory ? h.memory : null;
  const disk = 'root' in h.disk && h.disk.root ? h.disk.root : null;
  const notReported = <EmptyState>Not reported.</EmptyState>;
  const apis = h.api_health;
  const polling = h.autopolling;
  const database = h.database;
  return {
    cpu: (
      <Panel key="cpu" headingLevel={3} title={<PanelTitle icon="Cpu">CPU</PanelTitle>}>
        <LineItems
          label="CPU"
          items={[
            { id: 'process', label: 'Process', amount: `${dec.format(cpu.process_percent)}%` },
            { id: 'system', label: 'System', amount: `${dec.format(cpu.system_percent)}%` },
            { id: 'cores', label: 'Cores', amount: cpu.core_count },
            { id: 'load', label: 'Load (1/5/15m)', amount: cpu.load_average ? cpu.load_average.map((l) => dec.format(l)).join(' / ') : EMPTY },
          ]}
        />
      </Panel>
    ),
    memory: (
      <Panel key="memory" headingLevel={3} title={<PanelTitle icon="Memory">Memory</PanelTitle>}>
        {!memory ? notReported : <Stack>
          <LineItems
            label="Memory"
            items={[
              { id: 'rss', label: 'Process RSS', amount: `${dec.format(memory.process.rss_mb)} MB` },
              { id: 'process', label: 'Process %', amount: `${dec.format(memory.process.percent)}%` },
              { id: 'threads', label: 'Threads', amount: memory.process.num_threads },
              { id: 'system', label: 'System', amount: `${dec.format(memory.system.used_gb)} / ${dec.format(memory.system.total_gb)} GB` },
            ]}
          />
          <Meter label="System memory used" value={memory.system.percent} valueText={`${memory.system.percent}%`} tone={usageTone(memory.system.percent)} />
        </Stack>}
      </Panel>
    ),
    disk: (
      <Panel key="disk" headingLevel={3} title={<PanelTitle icon="HardDrives">Disk</PanelTitle>}>
        {!disk ? notReported : <Stack>
          <LineItems
            label="Disk"
            items={[
              { id: 'used', label: 'Used', amount: `${dec.format(disk.used_gb)} / ${num.format(disk.total_gb)} GB` },
              { id: 'free', label: 'Free', amount: `${dec.format(disk.free_gb)} GB` },
            ]}
          />
          <Meter label="Disk used" value={disk.percent} valueText={`${disk.percent}%`} tone={usageTone(disk.percent)} />
        </Stack>}
      </Panel>
    ),
    apiKeys: (
      <Panel key="apiKeys"
        headingLevel={3}
        title={<PanelTitle icon="Key">API keys</PanelTitle>}
        headerAside={
          apis && (
            <Chip tone={apis.status === 'healthy' ? 'success' : apis.status === 'degraded' ? 'warning' : 'error'}>
              {apis.status === 'healthy' ? 'All configured' : apis.status === 'degraded' ? 'Missing keys' : 'Critical'}
            </Chip>
          )
        }
      >
        {apis ? (
          <LineItems
            label="API keys"
            items={[
              { id: 'configured', label: 'Configured', amount: `${apis.configured_count} / ${apis.total_checked}` },
              ...Object.entries(apis.apis).map(([id, state]) => ({
                id,
                label: API_LABELS[id] ?? id,
                amount: state === 'configured' ? <Icon name="Check" size="sm" label="Configured" /> : 'Not configured',
              })),
            ]}
          />
        ) : (
          <EmptyState>Not reported.</EmptyState>
        )}
      </Panel>
    ),
    polling: (
      <Panel key="polling"
        headingLevel={3}
        title={<PanelTitle icon="ArrowsClockwise">Auto-polling</PanelTitle>}
        headerAside={
          polling && (
            <Chip tone={polling.status === 'error' ? 'error' : polling.is_enabled ? 'success' : 'warning'}>
              {polling.status === 'error' ? 'Error' : polling.is_enabled ? 'Enabled' : 'Paused'}
            </Chip>
          )
        }
      >
        {polling ? (
          <Stack>
            <LineItems
              label="Auto-polling"
              items={[
                {
                  id: 'requests',
                  label: 'Requests today',
                  amount: `${num.format(polling.requests_today ?? 0)} / ${polling.daily_request_limit != null ? num.format(polling.daily_request_limit) : EMPTY}`,
                },
                { id: 'last-run', label: 'Last run', amount: when(polling.last_poll_time) },
                ...(polling.last_error ? [{ id: 'error', label: 'Last error', amount: polling.last_error }] : []),
              ]}
            />
            {polling.daily_request_limit ? (
              <Meter
                label="Daily request limit used"
                value={Math.min(100, ((polling.requests_today ?? 0) / polling.daily_request_limit) * 100)}
                valueText={`${Math.round(((polling.requests_today ?? 0) / polling.daily_request_limit) * 100)}%`}
                tone={usageTone(((polling.requests_today ?? 0) / polling.daily_request_limit) * 100)}
              />
            ) : null}
          </Stack>
        ) : (
          <EmptyState>Not reported.</EmptyState>
        )}
      </Panel>
    ),
    database: (
      <Panel key="database"
        headingLevel={3}
        title={<PanelTitle icon="Database">Database</PanelTitle>}
        headerAside={
          database && (
            <Chip tone={database.status === 'healthy' ? 'success' : database.status === 'error' || database.status === 'critical' ? 'error' : 'warning'}>
              {database.status === 'healthy' ? 'Healthy' : database.status === 'error' || database.status === 'critical' ? 'Error' : 'Degraded'}
            </Chip>
          )
        }
      >
        {database ? (
          <LineItems
            label="Database"
            items={[
              { id: 'articles', label: 'Articles', amount: database.article_count != null ? num.format(database.article_count) : EMPTY },
              // The check can't size a PostgreSQL database and reports 0, so the row is left out then
              ...(database.size_mb ? [{ id: 'size', label: 'Size', amount: `${num.format(database.size_mb)} MB` }] : []),
              { id: 'locked', label: 'Locked', amount: database.locked ? 'Yes' : 'No' },
              ...(database.error ? [{ id: 'error', label: 'Error', amount: database.error }] : []),
            ]}
          />
        ) : (
          <EmptyState>Not reported.</EmptyState>
        )}
      </Panel>
    ),
  };
  }
  const visibleMetrics = metricOrder.filter((id) => !hiddenMetrics.includes(id));

  return (
    <AppShell
      current="operations-hq"
      page="System Health"
      navActions={<PageSettings {...pageLayout} />}
      title="System Health"
      pageWidth="default"
      toasts={toasts}
    >
      {error && <Banner tone="error" icon="WarningCircle" title="Some figures couldn’t be loaded" description={error} />}
      <ClockSettings
        open={clockSettingsOpen}
        onOpenChange={setClockSettingsOpen}
        clocks={clocks}
        onSave={(next) => {
          pageLayout.setClocks(next);
          notify(`World clocks saved (${next.length})`, 'Clock');
        }}
      />
      <NewsTickerSettings
        open={tickerSettingsOpen}
        onOpenChange={setTickerSettingsOpen}
        settings={ticker}
        onSave={(next) => {
          setTicker(next);
          notify('News ticker settings saved', 'GearSix');
        }}
      />
      {sections.ticker && (
        <NewsTicker
          // Remount on refresh so the new list starts from the beginning
          key={`${refreshedAt}-${headlines?.length ?? 0}`}
          items={tickerItems}
          cycleSeconds={Number(ticker.speed)}
          defaultPaused={!ticker.playOnLoad}
          onRefresh={() => {
            setRefreshedAt(Date.now());
            notify('Headlines refreshed', 'ArrowClockwise');
          }}
          onSettings={() => setTickerSettingsOpen(true)}
          onDismiss={() => {
            pageLayout.setSection('ticker', false);
            notify('News ticker hidden — turn it back on in Settings');
          }}
        />
      )}

      {sections.status && (
        <Panel
          title="System status"
          description={`Uptime: ${uptime}`}
          headerAside={status && <Chip tone={status.tone} size="md">{status.label}</Chip>}
        >
          {health?.warnings && health.warnings.length > 0 && (
            <Stack as="ul" gap="sm" label="Warnings">
              {health.warnings.map((w) => (
                <li key={w}>
                  <Banner tone="warning" icon="Warning" title="Warning" description={w} />
                </li>
              ))}
            </Stack>
          )}
        </Panel>
      )}

      {sections.clock && (
        <Panel
          title={<PanelTitle icon="Clock">World clock</PanelTitle>}
          headerAside={
            <Button
              variant="secondary"
              size="sm"
              iconStart={<Icon name="GearSix" size="sm" />}
              onClick={() => setClockSettingsOpen(true)}
            >
              Configure
            </Button>
          }
        >
          {clocks.length > 0 ? (
            <Grid as="ul" columns={4} stackAt="small" label="World clock">
              {clocks.map(({ city, timeZone }) => {
                const time = now.toLocaleTimeString('en-GB', { timeZone, hour12: false });
                const date = now.toLocaleDateString('en-US', { timeZone, month: 'short', day: 'numeric' });
                return (
                  <li key={city}>
                    <Stat size="compact" mono label={city} value={<time>{time}</time>} meta={date} />
                  </li>
                );
              })}
            </Grid>
          ) : (
            <EmptyState action={<Button variant="secondary" onClick={() => setClockSettingsOpen(true)}>Add clocks</Button>}>
              No clocks yet.
            </EmptyState>
          )}
        </Panel>
      )}

      {sections.totals && (
        <Grid as="ul" columns={4} stackAt="small" gap="md" label="Totals">
          {totals.map((total) => (
            <li key={total.id}>
              <Stat
                surface="panel"
                label={total.label}
                value={total.value != null ? num.format(total.value) : EMPTY}
                meta={<TextLink href={total.href}>{total.link}</TextLink>}
                icon={<Icon name={total.icon} size="lg" />}
              />
            </li>
          ))}
        </Grid>
      )}

      {visibleMetrics.length > 0 && (
        <>
          <Eyebrow as="h2">Detailed metrics</Eyebrow>
          {metricPanels ? (
            <Grid columns={3} gap="md">
              {visibleMetrics.map((id) => metricPanels[id])}
            </Grid>
          ) : (
            <Grid columns={3} gap="md">
              {visibleMetrics.map((id) => <Skeleton key={id} variant="block" />)}
            </Grid>
          )}
        </>
      )}
    </AppShell>
  );
}
