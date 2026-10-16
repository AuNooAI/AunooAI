import { useRef, useState } from 'react';
import { Icon, IconButton, Panel, Stack, Text } from '@aunoo/ui';
import { downloadElementPng } from '../../shared/exports';

/*
 * A Panel whose chart can be saved as a PNG ("Download as image"), as the old module tabs'
 * ChartDownloadButton. The whole panel, title included, goes into the image; the button itself
 * is left out of it.
 */
type PanelProps = React.ComponentProps<typeof Panel>;

export function ImagePanel({ filename, headerAside, ...props }: PanelProps & { filename: string }) {
  const box = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    if (!box.current) return;
    setBusy(true);
    setError(null);
    try {
      await downloadElementPng(box.current, `${filename}.png`);
    } catch (e) {
      setError(`The image wasn’t saved: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div ref={box}>
      <Panel
        {...props}
        headerAside={
          <Stack direction="row" gap="sm" wrap={false}>
            {headerAside}
            <span data-html2canvas-ignore="true">
              <IconButton icon={<Icon name="DownloadSimple" size="sm" />} label={`Download “${typeof props.title === 'string' ? props.title : filename}” as an image`} disabled={busy} onClick={() => void save()} />
            </span>
          </Stack>
        }
      >
        {props.children}
        {error && <Text variant="caption" tone="error">{error}</Text>}
      </Panel>
    </div>
  );
}
