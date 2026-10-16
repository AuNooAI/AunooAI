import { Button, Dialog, DialogClose, Icon, Skeleton, Stack, Text } from '@aunoo/ui';
import { Markdown } from '../../shell/Markdown';

/*
 * The AI summary of a set of articles (the old page's "Auspex Summary" modal). Opening it never
 * runs anything; the page asks first and only then calls the model.
 */

export interface SummaryState {
  title: string;
  /** null while the model is writing */
  text: string | null;
  error?: string | null;
  articles: { title: string; uri: string }[];
}

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function SummaryDialog({ state, onClose }: { state: SummaryState | null; onClose: () => void }) {
  if (!state) return null;
  const md = state.text
    ? `# ${state.title}\n\n${state.text}\n\n## Articles\n\n${state.articles.map((a) => `- [${a.title}](${a.uri})`).join('\n')}\n\n_Written by AI from the listed articles; check the sources before relying on it._\n`
    : '';
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      size="lg"
      title={state.title}
      description={`${state.articles.length} article${state.articles.length === 1 ? '' : 's'}`}
      footer={
        <>
          {state.text && <Button variant="secondary" size="lg" iconStart={<Icon name="DownloadSimple" size="sm" />} onClick={() => download('summary.md', md)}>Download as Markdown</Button>}
          <DialogClose><Button size="lg">Close</Button></DialogClose>
        </>
      }
    >
      {state.error ? <Text tone="error">{state.error}</Text>
        : state.text === null ? (
          <Stack gap="sm">
            <Text variant="caption">The AI is reading the articles. This usually takes under a minute.</Text>
            <Skeleton variant="text" lines={8} />
          </Stack>
        ) : (
          <Stack gap="md">
            <Markdown text={state.text} />
            <Text variant="caption">Written by AI from the articles listed; check the sources before relying on it.</Text>
          </Stack>
        )}
    </Dialog>
  );
}
