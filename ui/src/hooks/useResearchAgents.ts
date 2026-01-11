/**
 * useResearchAgents Hook
 * Manages state for Research Agents (signal instructions) functionality
 */

import { useState, useEffect, useCallback } from 'react';
import {
  getResearchAgents,
  createResearchAgent,
  updateResearchAgent,
  deleteResearchAgent,
  runResearchAgents,
  getSignalAlerts,
  acknowledgeAlert,
  acknowledgeAllAlerts,
  type ResearchAgent,
  type SignalAlert,
  type CreateAgentRequest,
  type UpdateAgentRequest,
  type PodcastSummary,
} from '../services/researchAgentsApi';

export interface UseResearchAgentsState {
  agents: ResearchAgent[];
  alerts: SignalAlert[];
  podcastSummaries: PodcastSummary[];
  unacknowledgedCount: number;
  loading: boolean;
  loadingAgents: boolean;
  loadingAlerts: boolean;
  runningAgents: Set<number>;
  error: string | null;
}

export interface UseResearchAgentsActions {
  fetchAgents: (topic?: string) => Promise<void>;
  fetchAlerts: (params?: { topic?: string; instructionId?: number }) => Promise<void>;
  addAgent: (agent: CreateAgentRequest) => Promise<boolean>;
  updateAgent: (agentId: number, updates: UpdateAgentRequest) => Promise<boolean>;
  removeAgent: (agentId: number) => Promise<boolean>;
  runAgent: (agentId: number, options?: { topic?: string; daysBack?: number }) => Promise<boolean>;
  runAllAgents: (options?: { topic?: string; daysBack?: number; tagArticles?: boolean; generateUnifiedReport?: boolean }) => Promise<boolean>;
  acknowledgeOne: (alertId: number) => Promise<boolean>;
  acknowledgeAll: (params?: { instructionId?: number; topic?: string }) => Promise<number>;
  clearError: () => void;
}

export function useResearchAgents(initialTopic?: string): UseResearchAgentsState & UseResearchAgentsActions {
  const [agents, setAgents] = useState<ResearchAgent[]>([]);
  const [alerts, setAlerts] = useState<SignalAlert[]>([]);
  const [podcastSummaries, setPodcastSummaries] = useState<PodcastSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const [loadingAlerts, setLoadingAlerts] = useState(false);
  const [runningAgents, setRunningAgents] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);

  // Calculate unacknowledged count
  const unacknowledgedCount = alerts.filter(a => !a.acknowledged).length;

  // Fetch agents
  const fetchAgents = useCallback(async (topic?: string) => {
    setLoadingAgents(true);
    setError(null);
    try {
      const response = await getResearchAgents({ topic, activeOnly: false });
      setAgents(response.instructions || []);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch research agents';
      setError(message);
      console.error('Error fetching research agents:', err);
    } finally {
      setLoadingAgents(false);
    }
  }, []);

  // Fetch alerts
  const fetchAlerts = useCallback(async (params?: { topic?: string; instructionId?: number }) => {
    setLoadingAlerts(true);
    try {
      const response = await getSignalAlerts({
        ...params,
        acknowledged: false, // Only fetch unacknowledged by default
        limit: 100,
      });
      setAlerts(response.alerts || []);
    } catch (err) {
      console.error('Error fetching signal alerts:', err);
      // Don't set error for alerts - it's secondary data
    } finally {
      setLoadingAlerts(false);
    }
  }, []);

  // Add new agent
  const addAgent = useCallback(async (agent: CreateAgentRequest): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      await createResearchAgent(agent);
      // Refresh the list
      await fetchAgents(initialTopic);
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create research agent';
      setError(message);
      console.error('Error creating research agent:', err);
      return false;
    } finally {
      setLoading(false);
    }
  }, [fetchAgents, initialTopic]);

  // Update agent
  const updateAgent = useCallback(async (agentId: number, updates: UpdateAgentRequest): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      await updateResearchAgent(agentId, updates);
      // Refresh the list
      await fetchAgents(initialTopic);
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update research agent';
      setError(message);
      console.error('Error updating research agent:', err);
      return false;
    } finally {
      setLoading(false);
    }
  }, [fetchAgents, initialTopic]);

  // Remove agent
  const removeAgent = useCallback(async (agentId: number): Promise<boolean> => {
    setError(null);
    try {
      await deleteResearchAgent(agentId);
      // Remove from local state immediately
      setAgents(prev => prev.filter(a => a.id !== agentId));
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete research agent';
      setError(message);
      console.error('Error deleting research agent:', err);
      return false;
    }
  }, []);

  // Run a single agent
  const runAgent = useCallback(async (
    agentId: number,
    options?: { topic?: string; daysBack?: number; tagArticles?: boolean }
  ): Promise<boolean> => {
    setRunningAgents(prev => new Set(prev).add(agentId));
    setError(null);
    try {
      const response = await runResearchAgents({
        instruction_ids: [agentId],
        topic: options?.topic,
        days_back: options?.daysBack || 7,
        tag_flagged_articles: options?.tagArticles !== false,
      });

      if (response.success) {
        // Capture podcast summaries if any
        if (response.podcast_summaries && response.podcast_summaries.length > 0) {
          setPodcastSummaries(prev => [...response.podcast_summaries!, ...prev]);
        }
        // Refresh alerts after running
        await fetchAlerts({ topic: options?.topic });
        return true;
      } else {
        setError(response.message || 'Failed to run research agent');
        return false;
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to run research agent';
      setError(message);
      console.error('Error running research agent:', err);
      return false;
    } finally {
      setRunningAgents(prev => {
        const next = new Set(prev);
        next.delete(agentId);
        return next;
      });
    }
  }, [fetchAlerts]);

  // Run all active agents
  const runAllAgents = useCallback(async (
    options?: { topic?: string; daysBack?: number; tagArticles?: boolean; generateUnifiedReport?: boolean }
  ): Promise<boolean> => {
    const activeAgentIds = agents.filter(a => a.is_active).map(a => a.id);
    if (activeAgentIds.length === 0) {
      setError('No active research agents to run');
      return false;
    }

    setRunningAgents(new Set(activeAgentIds));
    setError(null);
    try {
      const response = await runResearchAgents({
        instruction_ids: activeAgentIds,
        topic: options?.topic,
        days_back: options?.daysBack || 7,
        tag_flagged_articles: options?.tagArticles !== false,
        generate_report: options?.generateUnifiedReport || false,
      });

      if (response.success) {
        // Capture podcast summaries if any
        if (response.podcast_summaries && response.podcast_summaries.length > 0) {
          setPodcastSummaries(prev => [...response.podcast_summaries!, ...prev]);
        }
        // Refresh alerts after running
        await fetchAlerts({ topic: options?.topic });
        // Notify about generated unified report
        if (response.report) {
          // Use browser alert for now - can be replaced with proper toast later
          window.alert(`Unified report generated!\n\nReport: ${response.report.name}\nArticles analyzed: ${response.report.articles_used}\n\nView in Saved Reports.`);
        }
        return true;
      } else {
        setError(response.message || 'Failed to run research agents');
        return false;
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to run research agents';
      setError(message);
      console.error('Error running research agents:', err);
      return false;
    } finally {
      setRunningAgents(new Set());
    }
  }, [agents, fetchAlerts]);

  // Acknowledge single alert
  const acknowledgeOne = useCallback(async (alertId: number): Promise<boolean> => {
    try {
      await acknowledgeAlert(alertId);
      // Update local state
      setAlerts(prev => prev.filter(a => a.id !== alertId));
      return true;
    } catch (err) {
      console.error('Error acknowledging alert:', err);
      return false;
    }
  }, []);

  // Acknowledge all alerts
  const acknowledgeAll = useCallback(async (
    params?: { instructionId?: number; topic?: string }
  ): Promise<number> => {
    try {
      const result = await acknowledgeAllAlerts(params);
      // Refresh alerts
      await fetchAlerts(params);
      return result.acknowledged_count;
    } catch (err) {
      console.error('Error acknowledging all alerts:', err);
      return 0;
    }
  }, [fetchAlerts]);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchAgents(initialTopic);
    fetchAlerts({ topic: initialTopic });
  }, [initialTopic, fetchAgents, fetchAlerts]);

  return {
    // State
    agents,
    alerts,
    podcastSummaries,
    unacknowledgedCount,
    loading,
    loadingAgents,
    loadingAlerts,
    runningAgents,
    error,
    // Actions
    fetchAgents,
    fetchAlerts,
    addAgent,
    updateAgent,
    removeAgent,
    runAgent,
    runAllAgents,
    acknowledgeOne,
    acknowledgeAll,
    clearError,
  };
}
