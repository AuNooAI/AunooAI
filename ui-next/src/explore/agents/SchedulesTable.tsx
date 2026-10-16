import { Chip, Stack, Table, Text } from '@aunoo/ui';
import type { ResearchAgent, SignalAlert } from '@monolith/researchAgentsApi';
import { when, type SystemSchedule } from './schedules';

/*
 * Every agent and the site's scheduled jobs in one table, as the old AgentStatsTable. Match counts
 * are the unread matches loaded on this page; the site's jobs have none, so they show a dash.
 */

type Status = 'running' | 'error' | 'paused' | 'scheduled' | 'active';
interface Row {
  id: string;
  name: string;
  topic?: string | null;
  status: Status;
  lastRun: string | null;
  nextRun: string | null;
  runs?: number;
  unread?: number;
}

const STATUS: Record<Status, { label: string; tone: 'info' | 'error' | 'muted' | 'success' }> = {
  running: { label: 'Running', tone: 'info' },
  error: { label: 'Last run failed', tone: 'error' },
  paused: { label: 'Paused', tone: 'muted' },
  scheduled: { label: 'Scheduled', tone: 'success' },
  active: { label: 'Active, run by hand', tone: 'success' },
};

export function SchedulesTable({ agents, alerts, running, systems }: { agents: ResearchAgent[]; alerts: SignalAlert[]; running: Set<number>; systems: SystemSchedule[] }) {
  const rows: Row[] = [
    ...systems.map((s, i): Row => ({
      id: `sys-${s.type}-${i}`, name: s.name, status: s.last_run_status === 'error' ? 'error' : 'scheduled', lastRun: s.last_run_at, nextRun: s.next_run_at,
    })),
    ...agents.map((a): Row => ({
      id: `agent-${a.id}`, name: a.name, topic: a.topic,
      status: running.has(a.id) ? 'running' : a.last_run_status === 'error' ? 'error' : !a.is_active ? 'paused' : a.schedule_enabled ? 'scheduled' : 'active',
      lastRun: a.last_run_at, nextRun: a.schedule_enabled && a.is_active ? a.next_run_at : null,
      runs: a.run_count || 0,
      unread: alerts.filter((x) => x.instruction_id === a.id && !x.acknowledged).length,
    })),
  ];
  if (!rows.length) return null;
  return (
    <Table<Row>
      caption="Agent and job schedules"
      hideCaption
      rows={rows}
      rowKey={(r) => r.id}
      columns={[
        { key: 'name', header: 'Name', rowHeader: true, wrap: true, render: (r) => (
          <Stack gap="sm">
            <span>{r.name}</span>
            {r.topic && <Text as="span" variant="caption">{r.topic}</Text>}
            {r.runs === undefined && <Text as="span" variant="caption">Site job</Text>}
          </Stack>
        ) },
        { key: 'status', header: 'Status', render: (r) => <Chip tone={STATUS[r.status].tone} size="sm">{STATUS[r.status].label}</Chip> },
        { key: 'lastRun', header: 'Last run', render: (r) => when(r.lastRun) },
        { key: 'nextRun', header: 'Next run', render: (r) => when(r.nextRun) },
        { key: 'runs', header: 'Runs', align: 'end', render: (r) => (r.runs === undefined ? '—' : r.runs) },
        { key: 'unread', header: 'Unread matches', align: 'end', render: (r) => (r.unread === undefined ? '—' : r.unread) },
      ]}
    />
  );
}
