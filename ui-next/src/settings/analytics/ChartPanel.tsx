import { useRef } from 'react';
import { Icon, IconButton, Panel, Stack } from '@aunoo/ui';
import { downloadElementPng } from '../../explore/shared/exports';
import { errorText } from '../../shell';

/** A chart in a panel, with "Download as image" in the header (the old page's Plotly camera button) */
export function ChartPanel({ title, description, file, notify, aside, children }: {
  title: string;
  description?: React.ReactNode;
  /** File name for the PNG, without extension */
  file: string;
  notify: (m: string) => void;
  aside?: React.ReactNode;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const save = async () => {
    if (!ref.current) return;
    try {
      await downloadElementPng(ref.current, `${file}.png`);
    } catch (e) {
      notify(`The image wasn’t saved: ${errorText(e)}`);
    }
  };
  return (
    <div ref={ref}>
      <Panel
        title={title}
        description={description}
        headerAside={
          <Stack direction="row" gap="sm">
            {aside}
            <IconButton icon={<Icon name="DownloadSimple" size="sm" />} label={`Download “${title}” as an image`} onClick={() => void save()} />
          </Stack>
        }
      >
        {children}
      </Panel>
    </div>
  );
}
