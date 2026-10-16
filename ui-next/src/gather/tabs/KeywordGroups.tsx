import { Button, Chip, EmptyState, Eyebrow, Grid, Icon, IconButton, Panel, Skeleton, Sparkline, Stack, Stat, Text } from '@aunoo/ui';
import type { KeywordGroup } from '../model';
import { fmt, nextLabel, plural } from '../lib';

interface Props {
  groups: KeywordGroup[];
  loading: boolean;
  now: Date;
  onOpenDetails: (id: string) => void;
  onOpenSettings: (id: string) => void;
  onDeleteUnscored: (id: string) => void;
  onCreate: () => void;
}

const STATUS = {
  success: { text: 'OK', tone: 'success' },
  error: { text: 'Error', tone: 'error' },
  pending: { text: 'Running', tone: 'default' },
  never_run: { text: 'Never run', tone: 'default' },
} as const;

function GroupCard({ g, now, onOpenDetails, onOpenSettings, onDeleteUnscored }: { g: KeywordGroup } & Pick<Props, 'now' | 'onOpenDetails' | 'onOpenSettings' | 'onDeleteUnscored'>) {
  const status = g.paused ? { text: 'Paused', tone: 'default' as const } : STATUS[g.status] ?? STATUS.never_run;
  const trendTotal = Math.round(g.trend.reduce((a, b) => a + b, 0));
  return (
    <Panel
      title={<><Icon name="FileText" size="sm" /> {g.name}</>}
      description={`${g.topic} · ${plural(g.keywords.length, 'keyword')} monitored`}
      headerAside={<IconButton icon={<Icon name="GearSix" size="sm" />} label={`Collection settings for ${g.name}`} onClick={() => onOpenSettings(g.id)} />}
    >
      <Stack gap="md">
        {(g.customSettings || g.paused) && (
          <Stack direction="row" gap="sm">
            {g.customSettings && (
              <Chip size="sm" tone="info" variant="outline" icon={<Icon name="SlidersHorizontal" size="sm" />}>Custom settings</Chip>
            )}
            {g.paused && <Chip size="sm" tone="muted" icon={<Icon name="Pause" size="sm" />}>Paused</Chip>}
          </Stack>
        )}
        {/* 2 × 2: four inset tiles don't fit the label and the delete button at card width */}
        <Grid columns={2} stackAt="never" gap="sm">
          <Stat size="compact" label="Total" value={fmt(g.total)} />
          <Stat size="compact" label="Relevant" value={fmt(g.relevant)} tone="success" />
          <Stat size="compact" label="Irrelevant" value={fmt(g.irrelevant)} tone="error" />
          <Stat
            size="compact"
            label="Unscored"
            value={fmt(g.unscored)}
            action={
              g.unscored > 0 && (
                <IconButton icon={<Icon name="X" size="sm" />} label={`Delete ${fmt(g.unscored)} unscored articles in ${g.name}`} tone="danger" onClick={() => onDeleteUnscored(g.id)} />
              )
            }
          />
        </Grid>
        <Grid columns={3} stackAt="small" gap="sm">
          <Stat size="compact" label="Last 24h" value={fmt(g.last24h)} />
          <Stat size="compact" label="This week" value={fmt(g.week)} />
          <Stat size="compact" label="Status" value={status.text} tone={status.tone} />
        </Grid>
        <Stack gap="sm">
          <Eyebrow as="h3">30-day trend</Eyebrow>
          <Sparkline label={`30-day trend for ${g.name}: ${plural(trendTotal, 'article')}`} values={g.trend} />
        </Stack>
        <Stack direction="row" justify="between" gap="sm">
          <Text variant="hint">Last checked: {g.lastChecked} · Next: {g.paused ? 'Paused' : nextLabel(g.nextAt, now)}</Text>
          <Button variant="ghost" size="sm" iconEnd={<Icon name="CaretRight" size="sm" />} aria-label={`View details for ${g.name}`} onClick={() => onOpenDetails(g.id)}>
            View Details
          </Button>
        </Stack>
      </Stack>
    </Panel>
  );
}

export function KeywordGroups({ groups, loading, onCreate, ...cardProps }: Props) {
  if (loading) {
    return (
      <Grid columns={2} gap="md">
        {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} variant="block" />)}
      </Grid>
    );
  }
  if (groups.length === 0) {
    return (
      <Panel title="Keyword Groups">
        <EmptyState icon="ListBullets" title="No keyword groups yet" action={<Button iconStart={<Icon name="Plus" size="sm" />} onClick={onCreate}>Create First Group</Button>}>
          Keyword groups decide what Gather collects. Create one to start.
        </EmptyState>
      </Panel>
    );
  }
  return (
    <Grid as="ul" columns={2} gap="md" label="Keyword groups">
      {groups.map((g) => (
        <li key={g.id}>
          <GroupCard g={g} {...cardProps} />
        </li>
      ))}
    </Grid>
  );
}
