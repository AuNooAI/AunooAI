import { Button, Checkbox, Icon, IconButton, Popover, PopoverClose, ReorderList, Stack, TabPanel, Tabs, Text } from '@aunoo/ui';
import { METRICS, SECTIONS, type usePageLayout } from './pageLayout';

type PageSettingsProps = ReturnType<typeof usePageLayout>;

const metricLabel = Object.fromEntries(METRICS.map((m) => [m.id, m.label])) as Record<string, string>;

/** Top-bar Settings button + dropdown: show/hide page sections, show/hide and reorder metric cards. */
export function PageSettings({ layout, setSection, setMetricShown, setMetricOrder }: PageSettingsProps) {
  return (
    <Popover
      label="Page settings"
      trigger={<IconButton surface="dark" icon={<Icon name="GearSix" size="md" />} label="Settings" />}
      footer={
        <PopoverClose>
          <Button variant="secondary" fullWidth>Done</Button>
        </PopoverClose>
      }
    >
      <Tabs
        label="Page settings"
        stretch
        items={[
          { value: 'sections', label: 'Sections' },
          { value: 'metrics', label: 'Metrics' },
        ]}
      >
        <TabPanel value="sections">
          <Stack gap="sm">
            <Text>Show or hide page sections</Text>
            <div>
              {SECTIONS.map((section) => (
                <Checkbox
                  key={section.id}
                  boxPosition="end"
                  label={section.label}
                  checked={layout.sections[section.id]}
                  onCheckedChange={(checked) => setSection(section.id, checked)}
                />
              ))}
            </div>
          </Stack>
        </TabPanel>
        <TabPanel value="metrics">
          <Stack gap="sm">
            <Text>Drag to reorder, click to show or hide</Text>
            <ReorderList
              label="Metrics"
              onReorder={setMetricOrder}
              items={layout.metricOrder.map((id) => ({
                id,
                label: metricLabel[id],
                content: (
                  <Checkbox
                    label={metricLabel[id]}
                    checked={!layout.hiddenMetrics.includes(id)}
                    onCheckedChange={(checked) => setMetricShown(id, checked)}
                  />
                ),
              }))}
            />
          </Stack>
        </TabPanel>
      </Tabs>
    </Popover>
  );
}
