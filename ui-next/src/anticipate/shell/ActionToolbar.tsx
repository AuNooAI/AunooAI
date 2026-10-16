import { Button, Icon, Stack, type IconName } from '@aunoo/ui';

export type ToolbarAction = 'configure' | 'tune' | 'pdf' | 'png' | 'raw' | 'references' | 'save' | 'delete';

interface Props {
  tune: boolean;
  /** An analysis is on screen (exports need one). */
  hasData: boolean;
  /** A saved analysis is loaded (it can be deleted). */
  savedLoaded: boolean;
  onAction: (action: ToolbarAction) => void;
}

/** Setup on the left; exports for the analysis on screen on the right. */
export function ActionToolbar({ tune, hasData, savedLoaded, onAction }: Props) {
  const setup: { id: ToolbarAction; label: string; icon: IconName }[] = [
    { id: 'configure', label: 'Configure', icon: 'GearSix' },
    ...(tune ? [{ id: 'tune' as const, label: 'Tune', icon: 'SlidersHorizontal' as IconName }] : []),
  ];
  const exports: { id: ToolbarAction; label: string; icon: IconName }[] = [
    { id: 'pdf', label: 'PDF', icon: 'FileText' },
    { id: 'png', label: 'PNG', icon: 'DownloadSimple' },
    { id: 'raw', label: 'Raw', icon: 'ListBullets' },
    { id: 'references', label: 'References', icon: 'BookOpen' },
    { id: 'save', label: 'Save', icon: 'BookmarkSimple' },
    ...(savedLoaded ? [{ id: 'delete' as const, label: 'Delete saved', icon: 'Trash' as IconName }] : []),
  ];
  return (
    <Stack direction="row" justify="between" gap="sm" label="Analysis actions">
      <Stack direction="row" gap="sm">
        {setup.map((a) => (
          <Button key={a.id} variant="ghost" size="sm" iconStart={<Icon name={a.icon} size="sm" />} onClick={() => onAction(a.id)}>{a.label}</Button>
        ))}
      </Stack>
      <Stack direction="row" gap="sm">
        {exports.map((a) => (
          <Button key={a.id} variant="ghost" size="sm" iconStart={<Icon name={a.icon} size="sm" />} disabled={!hasData} onClick={() => onAction(a.id)}>{a.label}</Button>
        ))}
      </Stack>
    </Stack>
  );
}
