import { Checkbox, Chip, Icon, IconButton, Popover, ReorderList, Stack, Text } from '@aunoo/ui';
import { TABS, tabById } from '../lib/tabs';

interface Props {
  order: string[];
  hidden: string[];
  activeTab: string;
  onReorder: (ids: string[]) => void;
  onVisibleChange: (id: string, visible: boolean) => void;
}

/** "Manage Tabs": drag (or ↑/↓) to reorder, checkbox to show/hide. The active and last visible tab can't be hidden. */
export function ManageTabsPopover({ order, hidden, activeTab, onReorder, onVisibleChange }: Props) {
  const visibleCount = TABS.length - hidden.length;
  return (
    <Popover
      title="Manage Tabs"
      width="wide"
      trigger={<IconButton surface="dark" icon={<Icon name="SlidersHorizontal" size="md" />} label="Manage dashboard tabs" />}
      footer={<Text variant="label">{visibleCount} of {TABS.length} tabs visible</Text>}
    >
      <Stack gap="sm">
        <Text>Drag to reorder, click a checkbox to show or hide.</Text>
        <ReorderList
          label="Dashboard tabs"
          onReorder={onReorder}
          items={order.map((id) => {
            const tab = tabById(id)!;
            const isActive = id === activeTab;
            const isLastVisible = !hidden.includes(id) && visibleCount === 1;
            return {
              id,
              label: tab.label,
              content: (
                <Stack direction="row" wrap={false} gap="sm">
                  <Checkbox
                    label={tab.label}
                    checked={!hidden.includes(id)}
                    disabled={isActive || isLastVisible}
                    onCheckedChange={(checked) => onVisibleChange(id, checked)}
                  />
                  {isActive && <Chip size="sm" tone="accent">active</Chip>}
                </Stack>
              ),
            };
          })}
        />
      </Stack>
    </Popover>
  );
}
