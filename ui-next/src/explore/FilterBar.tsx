import { Button, Checkbox, Icon, IconButton, Popover, Select, Stack, Text, type SelectOption } from '@aunoo/ui';
import type { ExploreWorkspace, DateRange } from './lib/useExploreConfig';

export const DATE_RANGES: SelectOption[] = [
  { value: '24h', label: 'Last 24 hours' },
  { value: '72h', label: 'Last 72 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: '3m', label: 'Last 3 months' },
  { value: '1y', label: 'Last year' },
  { value: 'all', label: 'All time' },
];

const GENERAL = 'general';

interface FilterBarProps {
  ws: ExploreWorkspace;
  busy?: boolean;
  onSchedule: () => void;
  onRefresh: () => void;
  onConfigureProfiles: () => void;
}

/** The filters every tab shares, with Schedule and Refresh together at the right. */
export function FilterBar({ ws, busy, onSchedule, onRefresh, onConfigureProfiles }: FilterBarProps) {
  const { config, setConfig, topics, models, profiles } = ws;
  const picked = config.topics;
  const allPicked = topics.length > 0 && picked.length === topics.length;
  const topicLabel = picked.length === 0 ? 'Select topics' : picked.length === 1 ? picked[0] : allPicked ? 'All topics' : `${picked.length} topics`;

  // A saved model that's no longer offered stays listed, so the trigger isn't blank
  const modelOptions: SelectOption[] = models.map((m) => ({ value: m.id, label: (m as { provider?: string }).provider ? `${m.name} (${(m as { provider?: string }).provider})` : m.name }));
  if (config.model && !models.some((m) => m.id === config.model)) modelOptions.unshift({ value: config.model, label: config.model });

  const profileOptions: SelectOption[] = [
    { value: GENERAL, label: 'General analysis' },
    ...profiles.map((p) => ({ value: String(p.id), label: p.name, tag: (p as { is_default?: boolean }).is_default ? 'Default' : undefined })),
  ];

  return (
    <Stack direction="row" justify="between" gap="sm" as="section" label="Filters">
      <Stack direction="row" gap="sm">
        <Popover
          label="Topics"
          align="start"
          trigger={
            <Button variant="secondary" iconStart={<Icon name="Funnel" size="sm" />} iconEnd={<Icon name="CaretDown" size="sm" />}>
              {topicLabel}
            </Button>
          }
        >
          <Stack gap="sm">
            <Stack direction="row" justify="between" gap="sm">
              <Text variant="label" as="span">Topics</Text>
              <Stack direction="row" gap="sm">
                <Button variant="ghost" size="sm" disabled={allPicked} onClick={() => setConfig({ topics: [...topics] })}>Select all</Button>
                <Button variant="ghost" size="sm" disabled={picked.length === 0} onClick={() => setConfig({ topics: [] })}>Clear all</Button>
              </Stack>
            </Stack>
            <div>
              {topics.map((topic) => (
                <Checkbox
                  key={topic}
                  label={topic}
                  checked={picked.includes(topic)}
                  onCheckedChange={(on) => setConfig({ topics: on ? [...picked, topic] : picked.filter((t) => t !== topic) })}
                />
              ))}
            </div>
            <Text variant="caption">Incidents and narratives cover every topic you pick. The briefing and article list follow a single topic, or all topics when you pick none or several.</Text>
          </Stack>
        </Popover>

        <Select
          label="Date range"
          hideLabel
          icon="CalendarBlank"
          options={DATE_RANGES}
          value={config.dateRange}
          onValueChange={(v) => setConfig({ dateRange: v as DateRange })}
        />
        <Select label="Model" hideLabel icon="Cpu" options={modelOptions} value={config.model} onValueChange={(model) => setConfig({ model })} />
        <Select
          label="Audience profile"
          hideLabel
          icon="Buildings"
          options={profileOptions}
          value={config.profileId == null ? GENERAL : String(config.profileId)}
          onValueChange={(v) => setConfig({ profileId: v === GENERAL ? null : Number(v) })}
          footerAction={{ label: 'Configure profiles', icon: 'GearSix', onSelect: onConfigureProfiles }}
        />
      </Stack>

      <Stack direction="row" gap="sm">
        <IconButton icon={<Icon name="Clock" size="sm" />} label="Scheduled dashboard generation" onClick={onSchedule} />
        <Button iconStart={<Icon name="ArrowClockwise" size="sm" />} onClick={onRefresh} disabled={busy}>
          {busy ? 'Refreshing…' : 'Refresh'}
        </Button>
      </Stack>
    </Stack>
  );
}
