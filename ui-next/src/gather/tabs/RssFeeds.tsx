import { Button, Chip, EmptyState, Grid, Icon, IconButton, LineItems, Menu, Panel, SettingRow, Skeleton, Stack, StatusDot, Text, TextLink } from '@aunoo/ui';
import type { RSSMonitorStatus } from '@monolith/gatherApi';
import { minutesFor, type Feed } from '../model';
import { ago, fmt, nextLabel } from '../lib';

interface Props {
  feeds: Feed[];
  loading: boolean;
  monitor: RSSMonitorStatus | null;
  now: Date;
  /** Feeds being fetched right now */
  fetching: Set<string>;
  onAdd: () => void;
  onEdit: (feed: Feed) => void;
  onFetch: (feed: Feed) => void;
  onDelete: (feed: Feed) => void;
}

const unitText = (feed: Feed) => `${feed.interval} ${feed.unit === 'minutes' ? 'minutes' : feed.unit === 'hours' ? 'hours' : 'days'}`;

function FeedCard({ feed, fetching, onEdit, onFetch, onDelete }: { feed: Feed; fetching: boolean } & Pick<Props, 'onEdit' | 'onFetch' | 'onDelete'>) {
  return (
    <SettingRow
      title={
        <Stack direction="row" gap="sm" wrap={false}>
          {!feed.error && (feed.lastCheckedAt ? <StatusDot tone="live" label="OK" /> : <StatusDot tone="pending" label="Not checked yet" />)}
          <span>{feed.name}</span>
          {feed.error && <Chip size="sm" tone="error" icon={<Icon name="WarningCircle" size="sm" />}>Error</Chip>}
          {!feed.active && <Chip size="sm" tone="warning">Paused</Chip>}
          {fetching && <Chip size="sm" tone="info" icon={<Icon name="ArrowsClockwise" size="sm" />}>Fetching…</Chip>}
        </Stack>
      }
      description={<TextLink href={feed.url} external>{feed.url}</TextLink>}
      // Menu on the title line, so the stats below span the whole card
      actionsPlacement="title"
      actions={
        <Menu
          trigger={<IconButton icon={<Icon name="DotsThreeOutlineVertical" size="sm" />} label={`Actions for ${feed.name}`} />}
          items={[
            { id: 'edit', label: 'Edit', icon: 'PencilSimple' },
            { id: 'fetch', label: 'Fetch Now', icon: 'ArrowsClockwise' },
            { id: 'delete', label: 'Delete', icon: 'Trash', tone: 'danger', separatorBefore: true },
          ]}
          onSelect={(id) => (id === 'edit' ? onEdit(feed) : id === 'fetch' ? onFetch(feed) : onDelete(feed))}
        />
      }
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <Chip size="sm" tone="accent">{feed.topic}</Chip>
        </Stack>
        {/* Bug 5: label / value lines can't overflow the card the way three stat boxes did */}
        <LineItems
          label={`${feed.name} stats`}
          items={[
            { id: 'scan', label: 'Last scan', amount: feed.lastScan },
            { id: 'detected', label: 'Detected', amount: fmt(feed.detected) },
            { id: 'enriched', label: 'Enriched', amount: fmt(feed.enriched) },
          ]}
        />
        <Text>Checks every {unitText(feed)}</Text>
        {feed.error && (
          <Stack direction="row" gap="sm" wrap={false}>
            <Text tone="error" truncate>Error: {feed.error}</Text>
            <IconButton icon={<Icon name="Info" size="sm" />} label={`Full error: ${feed.error}`} />
          </Stack>
        )}
      </Stack>
    </SettingRow>
  );
}

/** Earliest next check across active feeds: last check + interval (the old tab worked it out the same way). */
function nextRun(feeds: Feed[]) {
  const times = feeds
    .filter((f) => f.active)
    .map((f) => (f.lastCheckedAt ? f.lastCheckedAt.getTime() + minutesFor(f.interval, f.unit) * 60000 : 0));
  return times.length ? new Date(Math.min(...times)) : null;
}

export function RssFeeds({ feeds, loading, monitor, now, fetching, onAdd, ...cardProps }: Props) {
  const active = monitor?.active_feeds ?? feeds.filter((f) => f.active).length;
  const total = monitor?.total_feeds ?? feeds.length;
  const next = nextRun(feeds);
  return (
    <Panel
      title={<><Icon name="Rss" size="sm" /> RSS Feeds</>}
      headerAside={
        <Stack direction="row" gap="sm">
          <Chip size="sm" tone="neutral">{fmt(active)} active / {fmt(total)} total</Chip>
          <Text as="span">Last: {ago(monitor?.last_check_time, now)} · Next: {next ? nextLabel(next, now).replace('In ', '') : 'None'}</Text>
          <Button iconStart={<Icon name="Plus" size="sm" />} onClick={onAdd}>Add Feed</Button>
        </Stack>
      }
    >
      {loading ? (
        <Grid columns={2} gap="sm">
          {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} variant="block" />)}
        </Grid>
      ) : feeds.length === 0 ? (
        <EmptyState icon="Rss" title="No RSS feeds configured" action={<Button iconStart={<Icon name="Plus" size="sm" />} onClick={onAdd}>Add Your First Feed</Button>}>
          Add a feed to collect articles from a site’s RSS or Atom feed.
        </EmptyState>
      ) : (
        <Grid as="ul" columns={2} gap="sm" label="RSS feeds">
          {feeds.map((f) => (
            <li key={f.id}>
              <FeedCard feed={f} fetching={fetching.has(f.id)} {...cardProps} />
            </li>
          ))}
        </Grid>
      )}
    </Panel>
  );
}
