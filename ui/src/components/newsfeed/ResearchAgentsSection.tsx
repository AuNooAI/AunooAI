/**
 * Research Agents Section
 * Displays research agents (signal instructions) and their alerts
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Bot,
  Plus,
  Play,
  Trash2,
  Pencil,
  Bell,
  CheckCircle,
  AlertTriangle,
  AlertCircle,
  Loader2,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Calendar,
  FileText,
  Workflow,
  Mic,
  X,
} from 'lucide-react';
import { Button } from '../ui/button';
import { AddAgentModal } from './AddAgentModal';
import { RunAgentModal, type RunAgentOptions } from './RunAgentModal';
import { ScheduleTimelineBar, type SystemSchedule } from './ScheduleTimelineBar';
import { AgentStatsTable } from './AgentStatsTable';
import { type ResearchAgent, type SignalAlert, type CreateAgentRequest, type UpdateAgentRequest, type PodcastSummary } from '../../services/researchAgentsApi';

interface ResearchAgentsSectionProps {
  agents: ResearchAgent[];
  alerts: SignalAlert[];
  podcastSummaries: PodcastSummary[];
  unacknowledgedCount: number;
  loading: boolean;
  loadingAgents: boolean;
  loadingAlerts: boolean;
  runningAgents: Set<number>;
  error: string | null;
  onAddAgent: (agent: CreateAgentRequest) => Promise<boolean>;
  onUpdateAgent: (agentId: number, updates: UpdateAgentRequest) => Promise<boolean>;
  onDeleteAgent: (agentId: number) => Promise<boolean>;
  onRunAgent: (agentId: number, options?: { daysBack?: number; tagArticles?: boolean }) => Promise<boolean>;
  onRunAllAgents: (options?: { daysBack?: number; tagArticles?: boolean; generateUnifiedReport?: boolean }) => Promise<boolean>;
  onAcknowledgeAlert: (alertId: number) => Promise<boolean>;
  onAcknowledgeAll: () => Promise<number>;
  onDismissPodcast?: (index: number) => void;
  topics?: string[];
}

export function ResearchAgentsSection({
  agents,
  alerts,
  podcastSummaries,
  unacknowledgedCount,
  loading,
  loadingAgents,
  loadingAlerts,
  runningAgents,
  error,
  onAddAgent,
  onUpdateAgent,
  onDeleteAgent,
  onRunAgent,
  onRunAllAgents,
  onAcknowledgeAlert,
  onAcknowledgeAll,
  onDismissPodcast,
  topics = [],
}: ResearchAgentsSectionProps) {
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<ResearchAgent | null>(null);
  const [isRunModalOpen, setIsRunModalOpen] = useState(false);
  const [runModalAgent, setRunModalAgent] = useState<ResearchAgent | null>(null);
  const [expandedAgents, setExpandedAgents] = useState<Set<number>>(new Set());
  const [runningAll, setRunningAll] = useState(false);
  const [systemSchedules, setSystemSchedules] = useState<SystemSchedule[]>([]);

  // Fetch system schedules (Emerging Topics, Newsfeed, Autoprocessing)
  const fetchSystemSchedules = useCallback(async () => {
    const schedules: SystemSchedule[] = [];

    // Fetch Emerging Topics schedule
    try {
      const etRes = await fetch('/api/emerging-topics/schedule/status', { credentials: 'include' });
      if (etRes.ok) {
        const data = await etRes.json();
        if (data.settings?.schedule_enabled) {
          schedules.push({
            name: 'Emerging Themes',
            type: 'emerging_topics',
            enabled: true,
            // API returns next_check_time, not next_run_time
            next_run_at: data.status?.next_check_time || null,
            last_run_at: data.status?.last_check_time || null,
            last_run_status: data.status?.last_error ? 'error' : (data.status?.topics_detected !== null ? 'success' : null),
          });
        }
      }
    } catch (e) {
      console.error('Failed to fetch emerging topics schedule:', e);
    }

    // Fetch Newsfeed Dashboard schedule
    try {
      const nfRes = await fetch('/api/news-feed/dashboard/schedule/status', { credentials: 'include' });
      if (nfRes.ok) {
        const data = await nfRes.json();
        if (data.settings?.schedule_enabled) {
          schedules.push({
            name: 'Newsfeed Dashboard',
            type: 'newsfeed',
            enabled: true,
            next_run_at: data.status?.next_run_time || null,
            last_run_at: data.status?.last_run_time || null,
            last_run_status: data.status?.last_run_status || null,
          });
        }
      }
    } catch (e) {
      console.error('Failed to fetch newsfeed schedule:', e);
    }

    // Fetch Autoprocessing (Keyword Monitor) schedule
    try {
      const apRes = await fetch('/api/keyword-monitor/settings', { credentials: 'include' });
      if (apRes.ok) {
        const data = await apRes.json();
        if (data.is_enabled) {
          schedules.push({
            name: 'Article Collection',
            type: 'autoprocessing',
            enabled: true,
            next_run_at: data.next_run_time || null,
            last_run_at: data.last_run_time || null,
            last_run_status: null, // Keyword monitor doesn't track status
          });
        }
      }
    } catch (e) {
      console.error('Failed to fetch autoprocessing schedule:', e);
    }

    // Fetch Geopolitical Hotspots schedules
    try {
      const ghRes = await fetch('/api/geopolitical-hotspots/schedules', { credentials: 'include' });
      if (ghRes.ok) {
        const data = await ghRes.json();
        if (data.schedules && data.schedules.length > 0) {
          for (const schedule of data.schedules) {
            if (schedule.schedule_enabled) {
              schedules.push({
                name: schedule.name || 'Geopolitical Hotspots',
                type: 'geopolitical',
                enabled: true,
                next_run_at: schedule.next_run_at || null,
                last_run_at: schedule.last_run_at || null,
                last_run_status: schedule.last_run_status || null,
              });
            }
          }
        }
      }
    } catch (e) {
      console.error('Failed to fetch geopolitical hotspots schedules:', e);
    }

    setSystemSchedules(schedules);
  }, []);

  // Fetch system schedules on mount and periodically
  useEffect(() => {
    fetchSystemSchedules();
    const interval = setInterval(fetchSystemSchedules, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, [fetchSystemSchedules]);

  const toggleAgentExpanded = (agentId: number) => {
    setExpandedAgents(prev => {
      const next = new Set(prev);
      if (next.has(agentId)) {
        next.delete(agentId);
      } else {
        next.add(agentId);
      }
      return next;
    });
  };

  const handleRunAgent = (agent: ResearchAgent) => {
    setRunModalAgent(agent);
    setIsRunModalOpen(true);
  };

  const handleRunAll = () => {
    setRunModalAgent(null); // null means run all
    setIsRunModalOpen(true);
  };

  const handleRunConfirm = async (options: RunAgentOptions) => {
    // Close modal immediately — progress shows on agent cards via runningAgents spinners
    setIsRunModalOpen(false);

    if (runModalAgent) {
      // Run single agent (fire-and-forget, hook manages runningAgents state)
      const agentId = runModalAgent.id;
      setRunModalAgent(null);
      onRunAgent(agentId, { daysBack: options.daysBack, tagArticles: options.tagArticles });
    } else {
      // Run all agents
      setRunModalAgent(null);
      setRunningAll(true);
      onRunAllAgents({
        daysBack: options.daysBack,
        tagArticles: options.tagArticles,
        generateUnifiedReport: options.generateUnifiedReport,
      }).finally(() => {
        setRunningAll(false);
      });
    }
  };

  const getThreatLevelColor = (level: string) => {
    switch (level?.toLowerCase()) {
      case 'high':
        return 'bg-red-100 text-red-800 border-red-200';
      case 'medium':
        return 'bg-amber-100 text-amber-800 border-amber-200';
      case 'low':
        return 'bg-green-100 text-green-800 border-green-200';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const getThreatLevelIcon = (level: string) => {
    switch (level?.toLowerCase()) {
      case 'high':
        return <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />;
      case 'medium':
        return <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />;
      default:
        return <Bell className="w-4 h-4 text-gray-600 shrink-0" />;
    }
  };

  // Group alerts by agent
  const alertsByAgent: Record<number, SignalAlert[]> = {};
  alerts.forEach(alert => {
    if (!alertsByAgent[alert.instruction_id]) {
      alertsByAgent[alert.instruction_id] = [];
    }
    alertsByAgent[alert.instruction_id].push(alert);
  });

  return (
    <section className="research-agents-section mb-8">
      {/* Section Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Bot className="w-5 h-5 text-pink-500" />
          <h2 className="text-xl font-semibold text-gray-900">Observer Agents</h2>
          {unacknowledgedCount > 0 && (
            <span className="ml-2 px-2 py-0.5 text-xs font-semibold bg-red-500 text-white rounded-full">
              {unacknowledgedCount} alert{unacknowledgedCount !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRunAll}
            disabled={runningAll || runningAgents.size > 0 || agents.filter(a => a.is_active).length === 0}
          >
            {runningAll || runningAgents.size > 0 ? (
              <Loader2 className="w-4 h-4 mr-1 animate-spin" />
            ) : (
              <Play className="w-4 h-4 mr-1" />
            )}
            Run All
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={() => setIsAddModalOpen(true)}
            className="bg-pink-500 hover:bg-pink-600"
          >
            <Plus className="w-4 h-4 mr-1" />
            Add Agent
          </Button>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-red-600" />
          <span className="text-sm text-red-800">{error}</span>
        </div>
      )}

      {/* Podcast Summaries - Hidden since podcast links are now embedded in reports */}

      {/* Loading State */}
      {loadingAgents && agents.length === 0 ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-pink-500" />
          <span className="ml-2 text-gray-700 dark:text-gray-700 dark:text-gray-300 dark:text-gray-700 dark:text-gray-300">Loading research agents...</span>
        </div>
      ) : agents.length === 0 ? (
        /* Empty State */
        <div className="bg-gray-50 rounded-lg p-8 text-center border border-dashed border-gray-400 dark:border-gray-600">
          <Bot className="w-12 h-12 text-gray-700 dark:text-gray-300 dark:text-gray-700 dark:text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No Research Agents Yet</h3>
          <p className="text-gray-700 dark:text-gray-700 dark:text-gray-300 dark:text-gray-700 dark:text-gray-300 mb-4 max-w-md mx-auto">
            Create AI-powered research agents to automatically monitor your news feed for specific topics,
            threats, opportunities, or custom criteria.
          </p>
          <Button
            onClick={() => setIsAddModalOpen(true)}
            className="bg-pink-500 hover:bg-pink-600"
          >
            <Plus className="w-4 h-4 mr-1" />
            Create Your First Agent
          </Button>
        </div>
      ) : (
        /* Agent List */
        <div className="space-y-3">
          {agents.map(agent => {
            const agentAlerts = alertsByAgent[agent.id] || [];
            const isExpanded = expandedAgents.has(agent.id);
            const isRunning = runningAgents.has(agent.id);

            return (
              <div
                key={agent.id}
                className="research-agent-card bg-white border border-gray-200 rounded-lg overflow-hidden"
              >
                {/* Agent Header */}
                <div className="flex items-center justify-between p-3 bg-gray-50">
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    <button
                      onClick={() => toggleAgentExpanded(agent.id)}
                      className="p-1 hover:bg-gray-200 rounded transition-colors"
                    >
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-gray-700 dark:text-gray-700 dark:text-gray-300 dark:text-gray-700 dark:text-gray-300" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-gray-700 dark:text-gray-700 dark:text-gray-300 dark:text-gray-700 dark:text-gray-300" />
                      )}
                    </button>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-gray-900">
                          {agent.name}
                        </span>
                        <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                          agent.is_active
                            ? 'bg-green-100 text-green-700'
                            : 'bg-gray-100 text-gray-600'
                        }`}>
                          {agent.is_active ? 'Active' : 'Paused'}
                        </span>
                        {agent.topic && (
                          <span className="px-2 py-0.5 text-xs font-medium bg-blue-50 text-blue-700 rounded-full">
                            {agent.topic}
                          </span>
                        )}
                        {agentAlerts.length > 0 && (
                          <span className="px-2 py-0.5 text-xs font-semibold bg-red-500 text-white rounded-full">
                            {agentAlerts.length} match{agentAlerts.length !== 1 ? 'es' : ''}
                          </span>
                        )}
                        {agent.last_run_at && (
                          <span className="text-xs text-gray-600 dark:text-gray-300" title={`Last run: ${new Date(agent.last_run_at).toLocaleString()}`}>
                            {new Date(agent.last_run_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}, {new Date(agent.last_run_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        )}
                      </div>
                      {agent.description && (
                        <p className="text-sm text-gray-700 dark:text-gray-700 dark:text-gray-300 dark:text-gray-700 dark:text-gray-300 truncate mt-0.5">
                          {agent.description}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 ml-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRunAgent(agent)}
                      disabled={isRunning || !agent.is_active}
                      title={!agent.is_active ? 'Agent is paused' : 'Run this agent'}
                    >
                      {isRunning ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Play className="w-4 h-4" />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditingAgent(agent)}
                      title="Edit agent"
                    >
                      <Pencil className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onDeleteAgent(agent.id)}
                      className="text-red-600 hover:text-red-700 hover:bg-red-50"
                      title="Delete agent"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>

                {/* Expanded Content */}
                {isExpanded && (
                  <div className="p-3 border-t border-gray-300 dark:border-gray-700">
                    <div className="mb-3">
                      <h4 className="text-xs font-medium text-gray-700 dark:text-gray-700 dark:text-gray-300 dark:text-gray-700 dark:text-gray-300 uppercase mb-1">
                        Research Instruction
                      </h4>
                      <p className="text-sm text-gray-700 bg-gray-50 p-2 rounded font-mono">
                        {agent.instruction}
                      </p>
                    </div>

                    {/* Agent Alerts */}
                    {agentAlerts.length > 0 ? (
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <h4 className="text-xs font-medium text-gray-700 dark:text-gray-700 dark:text-gray-300 dark:text-gray-700 dark:text-gray-300 uppercase">
                            Matches ({agentAlerts.length})
                          </h4>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onAcknowledgeAll()}
                            className="text-xs h-7"
                          >
                            <CheckCircle className="w-3 h-3 mr-1" />
                            Dismiss All
                          </Button>
                        </div>
                        <div className="space-y-2 max-h-80 overflow-y-auto">
                          {agentAlerts.map(alert => (
                            <div
                              key={alert.id}
                              className="p-3 bg-gray-50 rounded-lg border border-gray-300 dark:border-gray-700"
                            >
                              <div className="flex items-start gap-3">
                                {getThreatLevelIcon(alert.threat_level)}
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 mb-1">
                                    <a
                                      href={alert.article_uri}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="font-medium text-gray-900 hover:text-pink-600 line-clamp-1"
                                    >
                                      {alert.article_title}
                                    </a>
                                    <span className={`px-2 py-0.5 text-xs font-medium rounded border ${getThreatLevelColor(alert.threat_level)}`}>
                                      {alert.threat_level || 'info'}
                                    </span>
                                  </div>

                                  {/* Reasoning - Why this article is relevant */}
                                  {alert.reasoning && (
                                    <div className="mt-2 p-2 bg-white rounded border-l-2 border-pink-300">
                                      <p className="text-xs font-medium text-gray-700 dark:text-gray-700 dark:text-gray-300 dark:text-gray-700 dark:text-gray-300 mb-1">Why this is relevant:</p>
                                      <p className="text-sm text-gray-700">{alert.reasoning}</p>
                                    </div>
                                  )}

                                  <div className="flex items-center gap-3 mt-2 text-xs text-gray-600 dark:text-gray-300">
                                    {alert.article_source && (
                                      <span>{alert.article_source}</span>
                                    )}
                                    {alert.article_date && (
                                      <span>{new Date(alert.article_date).toLocaleDateString()}</span>
                                    )}
                                  </div>
                                </div>
                                <div className="flex items-center gap-1 shrink-0">
                                  <a
                                    href={alert.article_uri}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="p-1.5 hover:bg-gray-200 rounded"
                                    title="Open article"
                                  >
                                    <ExternalLink className="w-4 h-4 text-gray-600 dark:text-gray-300" />
                                  </a>
                                  <button
                                    onClick={() => onAcknowledgeAlert(alert.id)}
                                    className="p-1.5 hover:bg-green-100 rounded"
                                    title="Dismiss"
                                  >
                                    <CheckCircle className="w-4 h-4 text-gray-600 dark:text-gray-300 hover:text-green-600" />
                                  </button>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <p className="text-sm text-gray-700 dark:text-gray-700 dark:text-gray-300 dark:text-gray-700 dark:text-gray-300 text-center py-4 bg-gray-50 rounded">
                        No matches found yet. Run the agent to analyze recent articles.
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Schedule Timeline - shown when any agents or system tasks have scheduling enabled */}
      {(agents.some(a => a.schedule_enabled) || systemSchedules.length > 0) && (
        <div className="mt-6 pt-4 border-t border-gray-200">
          <h3 className="text-sm font-medium text-gray-700 mb-3">Scheduled Runs (24h)</h3>
          <ScheduleTimelineBar agents={agents} systemSchedules={systemSchedules} />
        </div>
      )}

      {/* Agent Schedules Table */}
      {(agents.length > 0 || systemSchedules.length > 0) && (
        <div className="mt-6 pt-4 border-t border-gray-200">
          <h3 className="text-sm font-medium text-gray-700 mb-3">Agent Schedules</h3>
          <AgentStatsTable
            agents={agents}
            alerts={alerts}
            runningAgents={runningAgents}
            systemSchedules={systemSchedules}
          />
        </div>
      )}

      {/* Add Agent Modal */}
      <AddAgentModal
        open={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onSave={async (agent) => {
          const success = await onAddAgent(agent);
          if (success) {
            setIsAddModalOpen(false);
          }
          return success;
        }}
        topics={topics}
        loading={loading}
      />

      {/* Edit Agent Modal */}
      <AddAgentModal
        open={!!editingAgent}
        onClose={() => setEditingAgent(null)}
        onSave={async (agent) => {
          if (!editingAgent) return false;
          const success = await onUpdateAgent(editingAgent.id, agent);
          if (success) {
            setEditingAgent(null);
          }
          return success;
        }}
        topics={topics}
        loading={loading}
        editAgent={editingAgent}
      />

      {/* Run Agent Modal */}
      <RunAgentModal
        open={isRunModalOpen}
        onClose={() => {
          setIsRunModalOpen(false);
          setRunModalAgent(null);
        }}
        onRun={handleRunConfirm}
        agentName={runModalAgent?.name}
        isRunningAll={!runModalAgent}
        loading={runningAll || runningAgents.size > 0}
      />
    </section>
  );
}
