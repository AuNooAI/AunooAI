/**
 * Agent Schedules Table
 * Shows all scheduled agents and system tasks (ET, Newsfeed) in one unified table
 */

import { useMemo } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';
import { Badge } from '../ui/badge';
import {
  CheckCircle,
  XCircle,
  Play,
  Clock,
  AlertTriangle,
  Sparkles,
  Newspaper,
  Bot,
} from 'lucide-react';
import { formatDistanceToNow, format } from 'date-fns';
import { type ResearchAgent, type SignalAlert } from '../../services/researchAgentsApi';
import { type SystemSchedule } from './ScheduleTimelineBar';

interface AgentStatsTableProps {
  agents: ResearchAgent[];
  alerts: SignalAlert[];
  runningAgents?: Set<number>;
  systemSchedules?: SystemSchedule[];
}

// Unified row type for both agents and system schedules
interface ScheduleRow {
  id: string;
  name: string;
  type: 'agent' | 'emerging_topics' | 'newsfeed' | 'autoprocessing';
  status: 'running' | 'scheduled' | 'active' | 'paused' | 'error';
  lastRun: string | null;
  nextRun: string | null;
  runCount?: number;
  alertCount?: number;
  unreadCount?: number;
  topic?: string | null;
}

export function AgentStatsTable({
  agents,
  alerts,
  runningAgents,
  systemSchedules = [],
}: AgentStatsTableProps) {
  // Build unified schedule rows
  const scheduleRows = useMemo(() => {
    const rows: ScheduleRow[] = [];

    // Add system schedules first
    for (const schedule of systemSchedules) {
      rows.push({
        id: `system-${schedule.type}`,
        name: schedule.name,
        type: schedule.type,
        status: schedule.last_run_status === 'error' ? 'error' :
                schedule.enabled ? 'scheduled' : 'paused',
        lastRun: schedule.last_run_at || null,
        nextRun: schedule.next_run_at,
        runCount: undefined,
        alertCount: undefined,
        unreadCount: undefined,
      });
    }

    // Add research agents
    for (const agent of agents) {
      const agentAlerts = alerts.filter(a => a.instruction_id === agent.id);
      const unacknowledged = agentAlerts.filter(a => !a.acknowledged).length;
      const isRunning = runningAgents?.has(agent.id) || false;

      rows.push({
        id: `agent-${agent.id}`,
        name: agent.name,
        type: 'agent',
        status: isRunning ? 'running' :
                !agent.is_active ? 'paused' :
                agent.schedule_enabled ? 'scheduled' : 'active',
        lastRun: agent.last_run_at,
        nextRun: agent.next_run_at,
        runCount: agent.run_count || 0,
        alertCount: agentAlerts.length,
        unreadCount: unacknowledged,
        topic: agent.topic,
      });
    }

    return rows;
  }, [agents, alerts, runningAgents, systemSchedules]);

  if (scheduleRows.length === 0) {
    return null;
  }

  const formatTime = (dateStr: string | null) => {
    if (!dateStr) return '—';
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diffHours = (date.getTime() - now.getTime()) / (1000 * 60 * 60);

      // If in the past, show relative time
      if (diffHours < 0) {
        return formatDistanceToNow(date, { addSuffix: true });
      }
      // If within 24 hours, show time
      if (diffHours < 24) {
        return format(date, 'HH:mm');
      }
      // Otherwise show date and time
      return format(date, 'MMM d, HH:mm');
    } catch {
      return '—';
    }
  };

  const getTypeIcon = (type: ScheduleRow['type']) => {
    switch (type) {
      case 'emerging_topics':
        return <Sparkles className="w-4 h-4 text-amber-500" />;
      case 'newsfeed':
        return <Newspaper className="w-4 h-4 text-blue-500" />;
      case 'autoprocessing':
        return <Clock className="w-4 h-4 text-purple-500" />;
      default:
        return <Bot className="w-4 h-4 text-gray-700 dark:text-gray-300" />;
    }
  };

  const getStatusBadge = (row: ScheduleRow) => {
    switch (row.status) {
      case 'running':
        return (
          <Badge variant="outline" className="bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
            <Play className="w-3 h-3 mr-1 animate-pulse" />
            Running
          </Badge>
        );
      case 'error':
        return (
          <Badge variant="outline" className="bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300">
            <XCircle className="w-3 h-3 mr-1" />
            Error
          </Badge>
        );
      case 'paused':
        return (
          <Badge variant="outline" className="bg-gray-50 text-gray-600 dark:bg-gray-800 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400">
            <XCircle className="w-3 h-3 mr-1" />
            Paused
          </Badge>
        );
      case 'scheduled':
        return (
          <Badge variant="outline" className="bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300">
            <Clock className="w-3 h-3 mr-1" />
            Scheduled
          </Badge>
        );
      default:
        return (
          <Badge variant="outline" className="bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300">
            <CheckCircle className="w-3 h-3 mr-1" />
            Active
          </Badge>
        );
    }
  };

  return (
    <div className="rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[220px]">Name</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Last Run</TableHead>
            <TableHead>Next Run</TableHead>
            <TableHead className="text-center">Alerts</TableHead>
            <TableHead className="text-center">Unread</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {scheduleRows.map(row => (
            <TableRow key={row.id}>
              <TableCell className="font-medium">
                <div className="flex items-center gap-2">
                  {getTypeIcon(row.type)}
                  <div className="flex flex-col">
                    <span className="truncate max-w-[180px]" title={row.name}>
                      {row.name}
                    </span>
                    {row.topic && (
                      <span className="text-xs text-muted-foreground truncate max-w-[180px]">
                        {row.topic}
                      </span>
                    )}
                  </div>
                </div>
              </TableCell>
              <TableCell>{getStatusBadge(row)}</TableCell>
              <TableCell>
                <span className="text-sm text-muted-foreground">
                  {formatTime(row.lastRun)}
                </span>
              </TableCell>
              <TableCell>
                <span className="text-sm text-muted-foreground">
                  {formatTime(row.nextRun)}
                </span>
              </TableCell>
              <TableCell className="text-center">
                {row.alertCount !== undefined ? (
                  <span className="text-sm font-medium">{row.alertCount}</span>
                ) : (
                  <span className="text-sm text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell className="text-center">
                {row.unreadCount !== undefined ? (
                  row.unreadCount > 0 ? (
                    <Badge variant="secondary" className="bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
                      <AlertTriangle className="w-3 h-3 mr-1" />
                      {row.unreadCount}
                    </Badge>
                  ) : (
                    <span className="text-sm text-muted-foreground">0</span>
                  )
                ) : (
                  <span className="text-sm text-muted-foreground">—</span>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
