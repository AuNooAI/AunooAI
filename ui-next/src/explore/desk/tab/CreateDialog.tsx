import { useEffect, useState } from 'react';
import { Banner, Button, Dialog, DialogClose, Stack, TextArea, TextField } from '@aunoo/ui';
import { createBriefing } from '@monolith/briefingDeskApi';
import { errorText } from '../../../shell';

/** A new empty briefing, filled later from "Add to briefing" on articles, incidents and themes */
export function CreateDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (o: boolean) => void; onCreated: () => void }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName('');
    setDescription('');
    setError(null);
  }, [open]);

  const create = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createBriefing(name.trim(), description.trim() || undefined);
      onOpenChange(false);
      onCreated();
    } catch (e) {
      setError(`Not created: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="New briefing"
      description="An empty draft. Add articles, incidents and emerging themes to it with “Add to briefing”, then write the summary yourself or have the AI write it."
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" busy={busy} disabled={!name.trim() || busy} onClick={() => void create()}>Create briefing</Button>
        </>
      }
    >
      <Stack gap="md">
        {error && <Banner tone="error" title="Something went wrong" description={error} />}
        <TextField label="Name" placeholder="e.g. Weekly strategy review" value={name} onChange={setName} maxLength={200} onSubmit={() => void create()} />
        <TextArea label="Description (optional)" rows={2} value={description} onChange={setDescription} />
      </Stack>
    </Dialog>
  );
}
