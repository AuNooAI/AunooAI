import { useEffect, useState } from 'react';
import { Banner, Button, Checkbox, Dialog, DialogClose, Stack, Text } from '@aunoo/ui';
import { errorText } from '../../shell';
import { deleteTopic } from './api';

/*
 * Deleting a topic, with the choice of also deleting its articles. One dialog instead of the old
 * page's two browser confirm boxes.
 */
export function DeleteTopicDialog({ name, onOpenChange, onDeleted }: { name: string | null; onOpenChange: (open: boolean) => void; onDeleted: (name: string) => void }) {
  const [withArticles, setWithArticles] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setWithArticles(false);
    setError(null);
  }, [name]);

  const run = async () => {
    if (!name) return;
    setBusy(true);
    setError(null);
    try {
      await deleteTopic(name, withArticles);
      onDeleted(name);
      onOpenChange(false);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={name !== null}
      onOpenChange={onOpenChange}
      title={`Delete “${name ?? ''}”?`}
      description="The topic leaves the site’s settings and stops being collected and analysed."
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button variant="danger" size="lg" busy={busy} disabled={busy} onClick={() => void run()}>{withArticles ? 'Delete topic and articles' : 'Delete topic'}</Button>
        </>
      }
    >
      <Stack gap="md">
        <Checkbox label="Also delete all of this topic’s articles from the database" checked={withArticles} onCheckedChange={setWithArticles} />
        <Text variant="caption">
          {withArticles ? 'The articles can’t be brought back afterwards.' : 'The articles already collected stay in the database.'}
        </Text>
        {error && <Banner tone="error" title="The topic wasn’t deleted" description={error} />}
      </Stack>
    </Dialog>
  );
}
