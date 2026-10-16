import { useEffect, useState } from 'react';
import { Button, Dialog, DialogClose, Eyebrow, Icon, PanelDivider, Select, Stack, Switch } from '@aunoo/ui';
import { COUNT_OPTIONS, DEFAULT_TICKER, RANGE_OPTIONS, REFRESH_OPTIONS, SPEED_OPTIONS, type TickerSettings as Settings } from './tickerSettings';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  settings: Settings;
  onSave: (settings: Settings) => void;
}

/** "News Ticker Settings" dialog (Latest strip → gear). Edits a draft; nothing changes until Save. */
export function NewsTickerSettings({ open, onOpenChange, settings, onSave }: Props) {
  const [draft, setDraft] = useState(settings);
  useEffect(() => {
    if (open) setDraft(settings);
  }, [open, settings]);
  const set = <K extends keyof Settings>(key: K) => (value: Settings[K]) => setDraft((d) => ({ ...d, [key]: value }));

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={<><Icon name="GearSix" size="sm" /> News Ticker Settings</>}
      footer={
        <>
          {/* Resets the form only — Save applies it */}
          <Button variant="secondary" size="lg" onClick={() => setDraft(DEFAULT_TICKER)}>Reset to Defaults</Button>
          <DialogClose>
            <Button
              size="lg"
              onClick={() => {
                onSave(draft);
              }}
            >
              Save Settings
            </Button>
          </DialogClose>
        </>
      }
    >
      <Stack gap="lg">
        <Select label="Number of Articles" fullWidth options={COUNT_OPTIONS} value={draft.count} onValueChange={set('count')} hint="More articles = longer scroll cycle" />
        <Select label="Time Range" fullWidth options={RANGE_OPTIONS} value={draft.range} onValueChange={set('range')} />
        <Select label="Scroll Speed" fullWidth options={SPEED_OPTIONS} value={draft.speed} onValueChange={set('speed')} hint="Slower speeds are easier to read" />
        <Select label="Auto-Refresh" fullWidth options={REFRESH_OPTIONS} value={draft.refresh} onValueChange={set('refresh')} />
        <Stack gap="md">
          <Eyebrow as="h3">Display Options</Eyebrow>
          <Switch label="Show article source" checked={draft.showSource} onCheckedChange={set('showSource')} />
          <Switch label="Show publish time" checked={draft.showTime} onCheckedChange={set('showTime')} />
        </Stack>
        <PanelDivider />
        <Switch
          label="Enable ticker on page load"
          description="Start scrolling as soon as the page opens. When off, the ticker waits until you press Play."
          checked={draft.playOnLoad}
          onCheckedChange={set('playOnLoad')}
        />
      </Stack>
    </Dialog>
  );
}
