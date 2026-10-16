import { useState } from 'react';
import { Banner, Button, DialogClose, Dialog, Select, Stack, Text, TextField } from '@aunoo/ui';
import { writePiece, type BriefingDetail } from '@monolith/marketMonitorApi';
import { errorText } from '../../../../shell';
import { MarkdownEditor } from '../../../../anticipate/components/MarkdownEditor';

/**
 * Our own piece: an analysis or a note a person writes, in Markdown. It's saved as a draft; approving
 * it puts it on the market's front page, under Analysis, and into the feed, with the author named.
 * Saving also checks each citation against its source (no model call).
 */
export function PieceDialog({ open, onOpenChange, marketId, topic, onSaved }: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  marketId: number;
  /** The market's collection topic, which the editor's article search looks in */
  topic: string;
  onSaved: (row: BriefingDetail) => void;
}) {
  const [kind, setKind] = useState<'analysis' | 'note'>('analysis');
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const row = await writePiece(marketId, { kind, title: title.trim(), report_content: body, author: author.trim() || null });
      setTitle('');
      setBody('');
      onSaved(row);
      onOpenChange(false);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="xl"
      title="Write a piece"
      description="Your own analysis or note. It’s saved as a draft; approving it puts it on the market’s front page, under Analysis, and into the feed. The page says who wrote it."
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" busy={busy} disabled={!title.trim() || !body.trim()} onClick={() => void save()}>Save as draft</Button>
        </>
      }
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <Select label="Kind" options={[{ value: 'analysis', label: 'Analysis' }, { value: 'note', label: 'Note' }]} value={kind} onValueChange={(v) => setKind(v as 'analysis' | 'note')} />
          <TextField label="Title" maxLength={300} value={title} onChange={setTitle} />
          <TextField label="Author" placeholder="Your name" maxLength={120} value={author} onChange={setAuthor} />
        </Stack>
        <MarkdownEditor label="The piece" value={body} onChange={setBody} topic={topic} />
        {!topic && <Text variant="hint">This market has no collection topic yet, so the article search finds nothing.</Text>}
        {error && <Banner tone="error" title="Not saved" description={error} />}
      </Stack>
    </Dialog>
  );
}
