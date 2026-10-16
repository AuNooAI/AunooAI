import { Icon, IconButton, Select, Stack, Text, type SelectOption } from '@aunoo/ui';

interface Props {
  topic: string;
  topics: string[];
  onTopicChange: (topic: string) => void;
  saved: string;
  savedOptions: SelectOption[];
  onSavedChange: (value: string) => void;
  lastUpdated?: string;
  generateLabel: string;
  busy: boolean;
  /** Analysis tabs: saved analyses and the refresh action apply. */
  canGenerate: boolean;
  onGenerate: () => void;
}

/** Topic, saved analysis, last updated, and the tab's refresh action. */
export function ContextRow({ topic, topics, onTopicChange, saved, savedOptions, onSavedChange, lastUpdated, generateLabel, busy, canGenerate, onGenerate }: Props) {
  return (
    <Stack direction="row" justify="between" gap="sm" label="Analysis context">
      <Stack direction="row" gap="sm">
        <Select label="Topic" hideLabel icon="Folder" options={topics.map((t) => ({ value: t, label: t }))} value={topic} onValueChange={onTopicChange} />
        {canGenerate && <Select label="Saved analysis" hideLabel icon="BookmarkSimple" options={savedOptions} value={saved} onValueChange={onSavedChange} />}
        {lastUpdated && (
          <Stack direction="row" wrap={false} gap="sm">
            <Icon name="Clock" size="sm" />
            <Text variant="label" as="span">Last updated: {lastUpdated}</Text>
          </Stack>
        )}
      </Stack>
      {canGenerate && <IconButton icon={<Icon name="ArrowClockwise" size="sm" />} label={generateLabel} onClick={onGenerate} disabled={busy} />}
    </Stack>
  );
}
