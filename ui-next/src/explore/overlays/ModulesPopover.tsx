import { Popover, Stack, Switch, Text } from '@aunoo/ui';
import type { ModuleInfo } from '../lib/useModules';

interface Props {
  modules: ModuleInfo[];
  onToggle: (id: string, enabled: boolean) => void;
  trigger: React.ReactElement;
}

/** Switch analysis modules on or off for the whole site (PUT /api/modules/{id}/toggle), as the old gear dialog did. */
export function ModulesPopover({ modules, onToggle, trigger }: Props) {
  return (
    <Popover title="Analysis modules" align="end" width="wide" trigger={trigger}>
      <Stack gap="md">
        <Text variant="caption">Each module adds a tab to Explore. Changes apply to everyone on this site.</Text>
        {modules.length === 0 && <Text>No modules are installed on this site.</Text>}
        {modules.map((m) => {
          const missingModel = m.has_model && m.model_available === false;
          return (
            <Switch
              key={m.id}
              label={m.tab_label || m.name}
              description={missingModel ? `${m.description ?? ''} Its model files aren’t installed, so it can’t be switched on.`.trim() : m.description}
              checked={m.enabled}
              disabled={missingModel && !m.enabled}
              onCheckedChange={(on) => onToggle(m.id, on)}
            />
          );
        })}
      </Stack>
    </Popover>
  );
}
