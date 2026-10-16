import { Button, Dialog, DialogClose, EmptyState, Stack, Text, TextLink } from '@aunoo/ui';
import { saveText } from '../lib/download';
import type { Reference } from '../lib/model';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  refs: Reference[];
  name: string;
}

/** The numbered sources behind the [n] citations, with a plain-text download. */
export function ReferencesDialog({ open, onOpenChange, refs, name }: Props) {
  const asText = () =>
    refs.map((r) => `[${r.n}] ${r.title}${r.source ? ` — ${r.source}` : ''}${r.published ? ` (${r.published.slice(0, 10)})` : ''}${r.url ? `\n    ${r.url}` : ''}`).join('\n');
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Reference articles"
      description={`Articles analyzed for this dashboard (${refs.length} total)`}
      footer={
        <>
          <Button variant="secondary" size="lg" disabled={!refs.length} onClick={() => saveText(asText(), `references-${name}.txt`)}>Download as TXT</Button>
          <DialogClose>
            <Button size="lg">Close</Button>
          </DialogClose>
        </>
      }
    >
      {refs.length === 0 ? (
        <EmptyState icon="BookOpen">No references for this analysis.</EmptyState>
      ) : (
        <Stack as="ul" gap="md" label="Reference articles">
          {refs.map((r) => (
            <li key={r.n}>
              <Stack gap="sm">
                <Text variant="description" as="div">
                  <strong>[{r.n}]</strong> {r.url ? <TextLink href={r.url} external>{r.title}</TextLink> : r.title}
                </Text>
                {(r.source || r.published) && (
                  <Text variant="caption" as="div">{[r.source && `Source: ${r.source}`, r.published && `Published ${r.published.slice(0, 10)}`].filter(Boolean).join(' · ')}</Text>
                )}
              </Stack>
            </li>
          ))}
        </Stack>
      )}
    </Dialog>
  );
}
