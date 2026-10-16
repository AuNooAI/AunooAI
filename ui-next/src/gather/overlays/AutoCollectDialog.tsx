import { useEffect, useState } from 'react';
import { Button, Dialog, DialogClose, type SelectOption } from '@aunoo/ui';
import type { AvailableProvider } from '@monolith/gatherApi';
import type { CollectSettings } from '../model';
import { SettingsSections, settingsErrors } from './SettingsSections';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  settings: CollectSettings;
  onSave: (settings: CollectSettings) => void;
  providers: AvailableProvider[];
  models: SelectOption[];
}

export function AutoCollectDialog({ open, onOpenChange, settings, onSave, providers, models }: Props) {
  const [draft, setDraft] = useState(settings);
  useEffect(() => {
    if (open) setDraft(settings);
  }, [open, settings]);
  const errors = settingsErrors(draft);
  const valid = Object.keys(errors).length === 0;

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Auto-Collect Settings"
      description="Configure automatic article collection settings"
      footer={
        <>
          <DialogClose>
            <Button variant="secondary" size="lg">Cancel</Button>
          </DialogClose>
          <Button
            size="lg"
            disabled={!valid}
            onClick={() => {
              onSave(draft);
              onOpenChange(false);
            }}
          >
            Save Settings
          </Button>
        </>
      }
    >
      <SettingsSections value={draft} onChange={setDraft} errors={errors} providers={providers} models={models} />
    </Dialog>
  );
}
