import { useCallback, useEffect, useState } from 'react';
import { Banner, Button, Checkbox, Chip, Icon, IconButton, Skeleton, Stack, Text, TextArea } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { errorText } from '../../shell';
import { Markdown } from '../../shell/Markdown';
import { addAnnotation, deleteAnnotation, listAnnotations, updateAnnotation, type Annotation } from './api';

/** Analyst notes on one article. A private note is kept out of the AI analysis. */
export function Annotations({ uri, notify, askConfirm }: { uri: string; notify: (m: string) => void; askConfirm: (c: Confirm) => void }) {
  const [items, setItems] = useState<Annotation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [priv, setPriv] = useState(false);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<{ id: number; content: string; priv: boolean } | null>(null);

  const load = useCallback(() => {
    setError(null);
    listAnnotations(uri).then(setItems, (e) => {
      setItems([]);
      setError(errorText(e));
    });
  }, [uri]);
  useEffect(() => {
    setItems(null);
    setEditing(null);
    setDraft('');
    load();
  }, [load]);

  const add = async () => {
    if (!draft.trim()) return;
    setBusy(true);
    try {
      await addAnnotation(uri, draft.trim(), priv);
      setDraft('');
      setPriv(false);
      notify('Note added');
      load();
    } catch (e) {
      notify(`Note not saved: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const saveEdit = async () => {
    if (!editing) return;
    setBusy(true);
    try {
      await updateAnnotation(uri, editing.id, editing.content, editing.priv);
      setEditing(null);
      notify('Note updated');
      load();
    } catch (e) {
      notify(`Note not updated: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const remove = (a: Annotation) =>
    askConfirm({
      title: 'Delete this note?',
      message: 'The note is removed for everyone. This can’t be undone.',
      action: 'Delete note',
      onConfirm: () =>
        void deleteAnnotation(uri, a.id).then(
          () => {
            notify('Note deleted');
            load();
          },
          (e) => notify(`Note not deleted: ${errorText(e)}`),
        ),
    });

  return (
    <Stack gap="md">
      <Text variant="label">Notes</Text>
      {error && <Banner tone="error" title="Notes didn’t load" description={error} />}
      {!items ? <Skeleton variant="text" lines={2} /> : items.length === 0 ? <Text variant="caption">No notes on this article yet.</Text> : (
        <Stack as="ul" gap="sm" label="Notes on this article">
          {items.map((a) => (
            <li key={a.id}>
              {editing?.id === a.id ? (
                <Stack gap="sm">
                  <TextArea label="Edit the note" hideLabel rows={3} value={editing.content} onChange={(content) => setEditing({ ...editing, content })} />
                  <Checkbox label="Private note (kept out of the analysis)" checked={editing.priv} onCheckedChange={(p) => setEditing({ ...editing, priv: p })} />
                  <Stack direction="row" gap="sm">
                    <Button size="sm" disabled={busy || !editing.content.trim()} onClick={() => void saveEdit()}>Save</Button>
                    <Button size="sm" variant="secondary" onClick={() => setEditing(null)}>Cancel</Button>
                  </Stack>
                </Stack>
              ) : (
                <Stack gap="sm">
                  <Stack direction="row" justify="between" gap="sm" wrap={false}>
                    <Text variant="caption">
                      {`${a.author} · ${new Date(a.created_at).toLocaleString('en-GB')}`}
                    </Text>
                    <Stack direction="row" gap="sm" wrap={false}>
                      {a.is_private && <Chip tone="muted" size="sm">Private</Chip>}
                      <IconButton icon={<Icon name="PencilSimple" size="sm" />} label="Edit this note" onClick={() => setEditing({ id: a.id, content: a.content, priv: a.is_private })} />
                      <IconButton tone="danger" icon={<Icon name="Trash" size="sm" />} label="Delete this note" onClick={() => remove(a)} />
                    </Stack>
                  </Stack>
                  <Markdown text={a.content} />
                </Stack>
              )}
            </li>
          ))}
        </Stack>
      )}
      <TextArea label="Add a note" rows={3} placeholder="Your analysis or comments…" value={draft} onChange={setDraft} />
      <Checkbox label="Private note (kept out of the analysis)" checked={priv} onCheckedChange={setPriv} />
      <div>
        <Button size="sm" iconStart={<Icon name="Plus" size="sm" />} disabled={busy || !draft.trim()} onClick={() => void add()}>Add note</Button>
      </div>
    </Stack>
  );
}
