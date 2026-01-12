/**
 * Schedule Timeline Bar
 * Displays a 24-hour timeline with scheduled agent runs and system tasks
 */

import { useMemo } from 'react';
import { type ResearchAgent } from '../../services/researchAgentsApi';

// System scheduled task (Emerging Topics, Newsfeed, Autoprocessing)
export interface SystemSchedule {
  name: string;
  type: 'emerging_topics' | 'newsfeed' | 'autoprocessing';
  enabled: boolean;
  next_run_at: string | null;
  last_run_at?: string | null;
  last_run_status?: string | null;
}

interface ScheduleTimelineBarProps {
  agents: ResearchAgent[];
  systemSchedules?: SystemSchedule[];
}

export function ScheduleTimelineBar({ agents, systemSchedules = [] }: ScheduleTimelineBarProps) {
  const scheduledAgents = agents.filter(a => a.schedule_enabled && a.next_run_at);
  const activeSystemSchedules = systemSchedules.filter(s => s.enabled && s.next_run_at);

  // Calculate current time position (0-24 hours)
  const now = new Date();
  const currentHour = now.getHours() + now.getMinutes() / 60;

  // Calculate positions for each agent's next run
  const agentPositions = useMemo(() => {
    const nowTime = now.getTime();

    return scheduledAgents.map(agent => {
      if (!agent.next_run_at) return null;

      const nextRun = new Date(agent.next_run_at);

      // Calculate hours from now until the next run
      const hoursUntilRun = (nextRun.getTime() - nowTime) / (1000 * 60 * 60);

      // Only show runs within the next 24 hours
      if (hoursUntilRun < 0 || hoursUntilRun > 24) return null;

      // Calculate position: current time + hours until run
      // This places it on the timeline relative to now
      const position = currentHour + hoursUntilRun;

      // Handle wrap-around past midnight
      const displayPosition = position > 24 ? position - 24 : position;

      return {
        agent,
        position: displayPosition,
        time: nextRun,
        hoursUntilRun,
      };
    }).filter(Boolean);
  }, [scheduledAgents, now, currentHour]);

  // Calculate positions for system schedules
  const systemPositions = useMemo(() => {
    const nowTime = now.getTime();

    return activeSystemSchedules.map(schedule => {
      if (!schedule.next_run_at) return null;

      const nextRun = new Date(schedule.next_run_at);
      const hoursUntilRun = (nextRun.getTime() - nowTime) / (1000 * 60 * 60);

      // Only show runs within the next 24 hours
      if (hoursUntilRun < 0 || hoursUntilRun > 24) return null;

      const position = currentHour + hoursUntilRun;
      const displayPosition = position > 24 ? position - 24 : position;

      return {
        schedule,
        position: displayPosition,
        time: nextRun,
        hoursUntilRun,
      };
    }).filter(Boolean);
  }, [activeSystemSchedules, now, currentHour]);

  // SVG dimensions
  const svgWidth = 600; // Fixed width for proper calculations
  const height = 80; // Increased height for system schedules below
  const barY = 30;
  const barHeight = 12;
  const padding = 20; // Padding on left and right

  // Hour markers
  const hourMarkers = [0, 6, 12, 18, 24];

  // Helper to calculate x position in pixels
  const getX = (hour: number) => {
    return padding + ((hour / 24) * (svgWidth - padding * 2));
  };

  // System schedule colors and icons
  const getSystemColor = (type: string) => {
    switch (type) {
      case 'emerging_topics': return '#f59e0b'; // amber
      case 'newsfeed': return '#3b82f6'; // blue
      case 'autoprocessing': return '#8b5cf6'; // purple
      default: return '#6b7280'; // gray
    }
  };

  const getSystemLabel = (type: string) => {
    switch (type) {
      case 'emerging_topics': return 'ET';
      case 'newsfeed': return 'NF';
      case 'autoprocessing': return 'AP';
      default: return '?';
    }
  };

  const getSystemName = (type: string) => {
    switch (type) {
      case 'emerging_topics': return 'Emerging Topics';
      case 'newsfeed': return 'Newsfeed Dashboard';
      case 'autoprocessing': return 'Autoprocessing';
      default: return type;
    }
  };

  const hasAnySchedules = scheduledAgents.length > 0 || activeSystemSchedules.length > 0;

  if (!hasAnySchedules) {
    return (
      <div className="text-sm text-gray-600 dark:text-gray-600 dark:text-gray-400 text-center py-4">
        No scheduled tasks. Enable scheduling in settings.
      </div>
    );
  }

  return (
    <div className="relative w-full">
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${svgWidth} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        className="overflow-visible"
      >
        {/* Background bar */}
        <rect
          x={padding}
          y={barY}
          width={svgWidth - padding * 2}
          height={barHeight}
          className="fill-gray-200 dark:fill-gray-700"
          rx={4}
        />

        {/* Hour markers */}
        {hourMarkers.map(hour => {
          const x = getX(hour);
          return (
            <g key={hour}>
              <line
                x1={x}
                y1={barY - 4}
                x2={x}
                y2={barY + barHeight + 4}
                className="stroke-gray-400 dark:stroke-gray-500"
                strokeWidth={1}
              />
              <text
                x={x}
                y={barY - 10}
                textAnchor="middle"
                fontSize={10}
                className="fill-gray-600 dark:fill-gray-400"
              >
                {hour.toString().padStart(2, '0')}:00
              </text>
            </g>
          );
        })}

        {/* Current time indicator */}
        <g>
          <line
            x1={getX(currentHour)}
            y1={barY - 8}
            x2={getX(currentHour)}
            y2={barY + barHeight + 8}
            stroke="#ec4899"
            strokeWidth={2}
          />
          <circle
            cx={getX(currentHour)}
            cy={barY - 10}
            r={3}
            fill="#ec4899"
          />
          <text
            x={getX(currentHour)}
            y={barY + barHeight + 22}
            textAnchor="middle"
            fontSize={9}
            fill="#ec4899"
            fontWeight="500"
          >
            Now
          </text>
        </g>

        {/* Agent markers (above the bar) */}
        {agentPositions.map((item, index) => {
          if (!item) return null;
          const { agent, position, time } = item;
          const x = getX(position);
          const isActive = agent.is_active;
          const status = agent.last_run_status;

          // Determine marker color
          let fillColor = isActive ? '#22c55e' : '#9ca3af'; // green for active, gray for paused
          if (status === 'error') fillColor = '#ef4444'; // red for error
          if (status === 'running') fillColor = '#f59e0b'; // amber for running

          // Stagger vertical position to avoid overlaps
          const yOffset = (index % 2) * -16;
          const markerY = barY + yOffset;

          return (
            <g key={agent.id} className="cursor-pointer">
              {/* Connecting line from marker to bar */}
              <line
                x1={x}
                y1={yOffset < 0 ? markerY + 10 : markerY}
                x2={x}
                y2={barY}
                stroke={fillColor}
                strokeWidth={1}
                strokeDasharray="2,2"
                opacity={0.5}
              />

              {/* Agent marker - using circle instead of rect for simpler positioning */}
              <circle
                cx={x}
                cy={markerY + 4}
                r={5}
                fill={fillColor}
                stroke="white"
                strokeWidth={1}
              />

              {/* Tooltip on hover */}
              <title>
{agent.name}
Next run: {time.toLocaleString()}
Status: {isActive ? 'Active' : 'Paused'}
{status ? `Last run: ${status}` : ''}
              </title>
            </g>
          );
        })}

        {/* System schedule markers (below the bar) */}
        {systemPositions.map((item, index) => {
          if (!item) return null;
          const { schedule, position, time } = item;
          const x = getX(position);
          const color = getSystemColor(schedule.type);
          const label = getSystemLabel(schedule.type);

          // Position below the bar, stagger if needed
          const yOffset = (index % 2) * 14;
          const markerY = barY + barHeight + 8 + yOffset;

          return (
            <g key={`${schedule.type}-${index}`} className="cursor-pointer">
              {/* Connecting line from bar to marker */}
              <line
                x1={x}
                y1={barY + barHeight}
                x2={x}
                y2={markerY - 6}
                stroke={color}
                strokeWidth={1}
                strokeDasharray="2,2"
                opacity={0.5}
              />

              {/* System marker - rounded rect with label */}
              <rect
                x={x - 10}
                y={markerY - 6}
                width={20}
                height={12}
                fill={color}
                rx={3}
              />
              <text
                x={x}
                y={markerY + 2}
                textAnchor="middle"
                fontSize={8}
                fill="white"
                fontWeight="600"
              >
                {label}
              </text>

              {/* Tooltip on hover */}
              <title>
{getSystemName(schedule.type)}
Next run: {time.toLocaleString()}
{schedule.last_run_status ? `Last run: ${schedule.last_run_status}` : ''}
              </title>
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="flex items-center justify-center gap-4 mt-2 text-xs text-gray-700 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400 flex-wrap">
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 bg-green-500 rounded-full" />
          <span>Active Agent</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 bg-gray-400 rounded-full" />
          <span>Paused</span>
        </div>
        {activeSystemSchedules.some(s => s.type === 'emerging_topics') && (
          <div className="flex items-center gap-1">
            <div className="w-3 h-2 bg-amber-500 rounded-sm" />
            <span>Emerging Topics</span>
          </div>
        )}
        {activeSystemSchedules.some(s => s.type === 'newsfeed') && (
          <div className="flex items-center gap-1">
            <div className="w-3 h-2 bg-blue-500 rounded-sm" />
            <span>Newsfeed</span>
          </div>
        )}
        {activeSystemSchedules.some(s => s.type === 'autoprocessing') && (
          <div className="flex items-center gap-1">
            <div className="w-3 h-2 bg-purple-500 rounded-sm" />
            <span>Autoprocessing</span>
          </div>
        )}
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 bg-pink-500 rounded-full" />
          <span>Now</span>
        </div>
      </div>
    </div>
  );
}
