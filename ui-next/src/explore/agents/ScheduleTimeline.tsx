import { Stack, Text } from '@aunoo/ui';
import type { ResearchAgent } from '@monolith/researchAgentsApi';
import type { SystemSchedule, SystemType } from './schedules';
import './agents.css';

/*
 * Scheduled runs over the next 24 hours, as the old ScheduleTimelineBar. The old strip used a
 * midnight-to-midnight axis and wrapped tomorrow's runs back onto it, so a run at 18:00 tomorrow sat
 * where 18:00 today would be. This one starts at now and runs 24 hours forward, labelled with clock
 * times. Agents sit above the line, the site's own jobs below.
 */

const SYS_SHORT: Record<SystemType, string> = { emerging_topics: 'ET', newsfeed: 'NF', autoprocessing: 'AC', geopolitical: 'GH' };
const SYS_NAME: Record<SystemType, string> = { emerging_topics: 'Emerging topics', newsfeed: 'News feed dashboard', autoprocessing: 'Article collection', geopolitical: 'GeoHotSpots' };

const W = 600;
const H = 84;
const PAD = 24;
const BAR_Y = 34;
const BAR_H = 10;
const DAY_MS = 86_400_000;

const time = (d: Date) => d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });

export function ScheduleTimeline({ agents, systems }: { agents: ResearchAgent[]; systems: SystemSchedule[] }) {
  const now = Date.now();
  const x = (t: number) => PAD + ((t - now) / DAY_MS) * (W - PAD * 2);
  const inWindow = (iso: string | null) => {
    if (!iso) return null;
    const t = new Date(iso).getTime();
    return t >= now && t <= now + DAY_MS ? t : null;
  };
  const agentRuns = agents.filter((a) => a.schedule_enabled).map((a) => ({ a, t: inWindow(a.next_run_at) })).filter((r): r is { a: ResearchAgent; t: number } => r.t !== null);
  const sysRuns = systems.map((s) => ({ s, t: inWindow(s.next_run_at) })).filter((r): r is { s: SystemSchedule; t: number } => r.t !== null);

  if (!agentRuns.length && !sysRuns.length) return <Text variant="caption">Nothing is scheduled to run in the next 24 hours.</Text>;

  const ticks = [0, 6, 12, 18, 24].map((h) => now + h * 3_600_000);
  const dotClass = (a: ResearchAgent) =>
    a.last_run_status === 'running' ? 'ag-dot--running' : a.last_run_status === 'error' ? 'ag-dot--error' : a.is_active ? 'ag-dot--active' : 'ag-dot--paused';
  const usedTypes = [...new Set(sysRuns.map((r) => r.s.type))];

  return (
    <Stack gap="sm">
      <svg className="ag-timeline" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Scheduled runs in the next 24 hours: ${[...agentRuns.map((r) => `${r.a.name} at ${time(new Date(r.t))}`), ...sysRuns.map((r) => `${r.s.name} at ${time(new Date(r.t))}`)].join('; ')}`}>
        <rect className="ag-timeline__track" x={PAD} y={BAR_Y} width={W - PAD * 2} height={BAR_H} rx={4} />
        {ticks.map((t, i) => (
          <g key={t}>
            <line className="ag-timeline__tick" x1={x(t)} y1={BAR_Y - 4} x2={x(t)} y2={BAR_Y + BAR_H + 4} />
            <text className="ag-timeline__label" x={x(t)} y={BAR_Y - 20} textAnchor={i === 0 ? 'start' : i === 4 ? 'end' : 'middle'}>{i === 0 ? 'now' : time(new Date(t))}</text>
          </g>
        ))}
        <line className="ag-timeline__now" x1={x(now)} y1={BAR_Y - 8} x2={x(now)} y2={BAR_Y + BAR_H + 8} />
        {agentRuns.map(({ a, t }, i) => {
          const cy = BAR_Y - 6 - (i % 2) * 10;
          return (
            <g key={a.id}>
              <line className={`ag-timeline__link ${dotClass(a)}`} x1={x(t)} y1={cy} x2={x(t)} y2={BAR_Y} />
              <circle className={dotClass(a)} cx={x(t)} cy={cy} r={5} />
              <title>{`${a.name}: next run ${new Date(t).toLocaleString('en-GB')}${a.is_active ? '' : ' (paused)'}${a.last_run_status ? `, last run ${a.last_run_status}` : ''}`}</title>
            </g>
          );
        })}
        {sysRuns.map(({ s, t }, i) => {
          const cy = BAR_Y + BAR_H + 12 + (i % 2) * 14;
          return (
            <g key={`${s.type}-${i}`}>
              <line className={`ag-timeline__link ag-sys--${s.type}`} x1={x(t)} y1={BAR_Y + BAR_H} x2={x(t)} y2={cy - 6} />
              <rect className={`ag-sys--${s.type}`} x={x(t) - 10} y={cy - 6} width={20} height={12} rx={3} />
              <text className="ag-sys__text" x={x(t)} y={cy + 3} textAnchor="middle">{SYS_SHORT[s.type]}</text>
              <title>{`${s.name}: next run ${new Date(t).toLocaleString('en-GB')}${s.last_run_status ? `, last run ${s.last_run_status}` : ''}`}</title>
            </g>
          );
        })}
      </svg>
      <Stack direction="row" gap="md">
        <Text as="span" variant="caption"><span className="ag-legend ag-dot--active" />Active agent</Text>
        <Text as="span" variant="caption"><span className="ag-legend ag-dot--paused" />Paused agent</Text>
        <Text as="span" variant="caption"><span className="ag-legend ag-dot--error" />Last run failed</Text>
        {usedTypes.map((t) => <Text key={t} as="span" variant="caption"><span className={`ag-legend ag-legend--box ag-sys--${t}`} />{`${SYS_NAME[t]} (${SYS_SHORT[t]})`}</Text>)}
      </Stack>
    </Stack>
  );
}
