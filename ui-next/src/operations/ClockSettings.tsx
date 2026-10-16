import { useEffect, useState } from 'react';
import {
  Button,
  Dialog,
  DialogClose,
  Eyebrow,
  Grid,
  Icon,
  Stack,
  Text,
  TextField,
  TopicCard,
  TopicPill,
} from '@aunoo/ui';
import type { Clock } from './pageLayout';
import { TIME_ZONES, canonicalTimeZone, cityFromTimeZone, matchesQuery, resolveTimeZone } from './timezones';

interface ClockSettingsProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Clocks on the page now. */
  clocks: Clock[];
  onSave: (clocks: Clock[]) => void;
}

/** "Configure world clocks" dialog. Edits a draft; nothing changes on the page until Save. */
export function ClockSettings({ open, onOpenChange, clocks, onSave }: ClockSettingsProps) {
  const [draft, setDraft] = useState(clocks);
  const [entry, setEntry] = useState('');
  const [entryError, setEntryError] = useState<string>();
  const [query, setQuery] = useState('');

  // Start every visit from what's on the page
  useEffect(() => {
    if (open) {
      setDraft(clocks);
      setEntry('');
      setEntryError(undefined);
      setQuery('');
    }
  }, [open, clocks]);

  // Compared by resolved zone, so an alias typed in the field marks its card in the list as added
  const selected = new Set(draft.map((clock) => canonicalTimeZone(clock.timeZone)));
  const isSelected = (timeZone: string) => selected.has(canonicalTimeZone(timeZone));
  const results = TIME_ZONES.filter((option) => matchesQuery(option, query));

  const add = (timeZone: string, city = cityFromTimeZone(timeZone)) => {
    setDraft((current) => [...current, { timeZone, city }]);
    setEntryError(undefined);
  };
  const remove = (timeZone: string) => {
    setDraft((current) => current.filter((clock) => canonicalTimeZone(clock.timeZone) !== canonicalTimeZone(timeZone)));
    setEntryError(undefined);
  };

  const addTyped = () => {
    const timeZone = resolveTimeZone(entry);
    if (!timeZone) {
      setEntryError(entry.trim() ? `“${entry.trim()}” isn’t an IANA timezone. Try a name like Europe/London.` : 'Enter a timezone first.');
      return;
    }
    if (isSelected(timeZone)) {
      setEntryError(`${timeZone} is already in your clocks.`);
      return;
    }
    add(timeZone);
    setEntry('');
    setEntryError(undefined);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Configure world clocks"
      description={`Add any IANA timezone. Currently showing ${clocks.length} ${clocks.length === 1 ? 'clock' : 'clocks'}.`}
      footer={
        <>
          <DialogClose>
            <Button variant="secondary" size="lg">Cancel</Button>
          </DialogClose>
          <Button
            size="lg"
            onClick={() => {
              onSave(draft);
              onOpenChange(false);
            }}
          >
            Save changes
          </Button>
        </>
      }
    >
      <Stack gap="lg">
        <TextField
          label="Add a timezone"
          hideLabel
          placeholder="Enter timezone, e.g. Europe/London"
          value={entry}
          error={entryError}
          onChange={(value) => {
            setEntry(value);
            if (entryError) setEntryError(undefined);
          }}
          onSubmit={addTyped}
          action={
            <Button size="lg" iconStart={<Icon name="Plus" size="sm" />} onClick={addTyped}>
              Add
            </Button>
          }
        />

        <Stack gap="sm">
          <Eyebrow as="h3">Selected clocks ({draft.length})</Eyebrow>
          {draft.length > 0 ? (
            <Stack as="ul" direction="row" gap="sm" label="Selected clocks">
              {draft.map((clock) => (
                <li key={clock.timeZone}>
                  <TopicPill label={clock.city} selected onToggle={() => remove(clock.timeZone)} />
                </li>
              ))}
            </Stack>
          ) : (
            <Text>No clocks selected. Add one above or pick from the list below.</Text>
          )}
          {draft.length > 0 && <Text variant="caption">Click a clock to remove it.</Text>}
        </Stack>

        <Stack gap="sm">
          <TextField
            label="Search timezones"
            hideLabel
            type="search"
            placeholder="Search timezones…"
            value={query}
            onChange={setQuery}
          />
          <Text variant="label" as="div">
            <span role="status">
              {results.length} {results.length === 1 ? 'timezone' : 'timezones'}
            </span>
          </Text>
          {results.length > 0 ? (
            <Grid as="ul" columns={2} stackAt="small" label="Timezones">
              {results.map((option) => (
                <li key={option.timeZone}>
                  <TopicCard
                    name={option.city}
                    description={option.region || option.timeZone}
                    selected={isSelected(option.timeZone)}
                    onToggle={(next) => (next ? add(option.timeZone) : remove(option.timeZone))}
                  />
                </li>
              ))}
            </Grid>
          ) : (
            <Text>No timezones match “{query.trim()}”. You can still add an exact IANA name above.</Text>
          )}
        </Stack>
      </Stack>
    </Dialog>
  );
}
