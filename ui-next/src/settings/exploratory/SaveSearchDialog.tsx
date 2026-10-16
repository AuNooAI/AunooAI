import { useEffect, useState } from 'react';
import { Banner, Button, Dialog, DialogClose, Stack, TextArea, TextField } from '@aunoo/ui';
import { errorText } from '../../shell';
import { saveSearch, type SavedSearch } from './api';

/** Saves the current query under a name, as the old page's Save Search modal */
export function SaveSearchDialog({ open, query, onOpenChange, onSaved }: {
  open: boolean;
  query: string;
  onOpenChange: (o: boolean) => void;
  onSaved: (s: SavedSearch) => void;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('');
  const [q, setQ] = useState(query);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName('');
    setDescription('');
    setTags('');
    setQ(query);
    setErr(null);
  }, [open, query]);

  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      const s = await saveSearch({ id: `search_${Math.random().toString(36).slice(2, 12)}`, name: name.trim(), description: description.trim(), tags: tags.trim(), query: q.trim(), created_at: new Date().toISOString() });
      onSaved(s);
      onOpenChange(false);
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Save this search"
      description="Saved searches are shared by everyone on this site and listed under Saved searches."
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" busy={busy} disabled={!name.trim() || !q.trim() || busy} onClick={() => void save()}>Save</Button>
        </>
      }
    >
      <Stack gap="md">
        <TextField label="Name" value={name} onChange={setName} maxLength={200} />
        <TextArea label="Description (optional)" rows={2} value={description} onChange={setDescription} />
        <TextField label="Tags (optional, separated by commas)" value={tags} onChange={setTags} />
        <TextArea label="Query" rows={2} mono value={q} onChange={setQ} />
        {err && <Banner tone="error" title="Not saved" description={err} />}
      </Stack>
    </Dialog>
  );
}
