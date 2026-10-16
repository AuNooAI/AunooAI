import { SettingRow, Select, Stack, Switch, Text, TextField } from '@aunoo/ui';
import type { ResearchAgent } from '@monolith/researchAgentsApi';
import type { AgentForm, ScheduleType, ScheduleUnit } from './form';

const DAYS_BACK = [
  { value: '1', label: 'Last 24 hours' },
  { value: '3', label: 'Last 3 days' },
  { value: '7', label: 'Last 7 days' },
  { value: '14', label: 'Last 2 weeks' },
  { value: '30', label: 'Last 30 days' },
];
const UNIT_MAX: Record<ScheduleUnit, number> = { minutes: 1440, hours: 168, days: 30 };
const when = (iso: string) => new Date(iso).toLocaleString('en-GB');

/** Whether "Run all" includes the agent, and its own schedule. */
export function SchedulePanel({ f, set, disabled, agent }: { f: AgentForm; set: (p: Partial<AgentForm>) => void; disabled: boolean; agent: ResearchAgent | null }) {
  return (
    <Stack gap="md">
      <Switch
        label="Active"
        description={f.isActive ? 'Included when you press “Run all”.' : 'Paused: left out of “Run all”. You can still run it on its own.'}
        checked={f.isActive}
        onCheckedChange={(isActive) => set({ isActive })}
        disabled={disabled}
      />
      <Switch
        label="Run on a schedule"
        description={f.scheduleEnabled ? 'The agent runs on its own at the times below. Each run calls the AI on every article it reads.' : 'Off: the agent runs only when someone runs it.'}
        checked={f.scheduleEnabled}
        onCheckedChange={(scheduleEnabled) => set({ scheduleEnabled })}
        disabled={disabled}
      />
      {f.scheduleEnabled && (
        <Stack gap="md">
          <Select
            label="When"
            options={[{ value: 'interval', label: 'Every so often' }, { value: 'daily', label: 'Daily at a set time' }]}
            value={f.scheduleType}
            onValueChange={(v) => set({ scheduleType: v as ScheduleType })}
            disabled={disabled}
            fullWidth
          />
          {f.scheduleType === 'interval' ? (
            <Stack direction="row" gap="sm">
              <TextField
                label="Run every"
                type="number"
                min={1}
                max={UNIT_MAX[f.scheduleUnit]}
                value={String(f.scheduleInterval)}
                onChange={(v) => set({ scheduleInterval: Math.min(UNIT_MAX[f.scheduleUnit], Math.max(1, parseInt(v) || 1)) })}
                disabled={disabled}
              />
              <Select
                label="Unit"
                options={[{ value: 'minutes', label: 'Minutes' }, { value: 'hours', label: 'Hours' }, { value: 'days', label: 'Days' }]}
                value={f.scheduleUnit}
                onValueChange={(v) => set({ scheduleUnit: v as ScheduleUnit, scheduleInterval: Math.min(UNIT_MAX[v as ScheduleUnit], f.scheduleInterval) })}
                disabled={disabled}
              />
            </Stack>
          ) : (
            <TextField label="Time of day" type="time" hint="Server time." value={f.scheduleTime} onChange={(scheduleTime) => set({ scheduleTime })} disabled={disabled} />
          )}
          <Select
            label="Articles each run reads"
            hint={`Each run reads articles from the last ${f.daysBack} day${f.daysBack === 1 ? '' : 's'}.`}
            options={DAYS_BACK}
            value={String(f.daysBack)}
            onValueChange={(v) => set({ daysBack: Number(v) })}
            disabled={disabled}
            fullWidth
          />
          <Text variant="caption">Email for scheduled runs is set on the “When it finds matches” tab.</Text>
          {agent?.next_run_at && (
            <SettingRow
              title={`Next run ${when(agent.next_run_at)}`}
              description={agent.last_run_at ? `Last run ${when(agent.last_run_at)}${agent.last_run_status ? `: ${agent.last_run_status}` : ''}` : 'Not run yet.'}
            />
          )}
        </Stack>
      )}
    </Stack>
  );
}
