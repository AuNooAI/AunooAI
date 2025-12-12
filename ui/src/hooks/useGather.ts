/**
 * Custom hook for Gather page state management
 */

import { useState, useEffect, useCallback } from 'react';
import {
  getSettings,
  updateSettings,
  getKeywordGroups,
  createKeywordGroup,
  deleteKeywordGroup,
  getKeywords,
  addKeyword,
  updateKeyword,
  deleteKeyword,
  getMonitorStatus,
  getRelevanceStats,
  getGroupSummaries as fetchGroupSummaries,
  triggerKeywordCheck,
  getAvailableProviders,
  getTopics,
  type KeywordGroup,
  type MonitoredKeyword,
  type KeywordMonitorSettings,
  type MonitorStatus,
  type KeywordStats,
  type KeywordGroupSummary,
  type AvailableProvider,
} from '../services/gatherApi';

export interface GatherState {
  groups: KeywordGroup[];
  keywords: MonitoredKeyword[];
  settings: KeywordMonitorSettings | null;
  status: MonitorStatus | null;
  relevanceStats: KeywordStats[];
  groupSummaries: KeywordGroupSummary[];
  availableProviders: AvailableProvider[];
  topics: string[];
  loading: boolean;
  error: string | null;
  checkingKeywords: boolean;
}

export function useGather() {
  const [state, setState] = useState<GatherState>({
    groups: [],
    keywords: [],
    settings: null,
    status: null,
    relevanceStats: [],
    groupSummaries: [],
    availableProviders: [],
    topics: [],
    loading: true,
    error: null,
    checkingKeywords: false,
  });

  // Load all data
  const loadData = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));

    try {
      const [
        groupsRaw,
        keywordsRaw,
        settings,
        status,
        relevanceStatsRaw,
        groupSummariesRaw,
        availableProvidersRaw,
        topicsRaw,
      ] = await Promise.all([
        getKeywordGroups(),
        getKeywords(),
        getSettings(),
        getMonitorStatus(),
        getRelevanceStats(),
        fetchGroupSummaries(),
        getAvailableProviders(),
        getTopics(),
      ]);

      // Ensure all arrays are actually arrays
      const groups = Array.isArray(groupsRaw) ? groupsRaw : [];
      const keywords = Array.isArray(keywordsRaw) ? keywordsRaw : [];
      const relevanceStats = Array.isArray(relevanceStatsRaw) ? relevanceStatsRaw : [];
      const groupSummaries = Array.isArray(groupSummariesRaw) ? groupSummariesRaw : [];
      const availableProviders = Array.isArray(availableProvidersRaw) ? availableProvidersRaw : [];
      const topics = Array.isArray(topicsRaw) ? topicsRaw : [];

      setState(prev => ({
        ...prev,
        groups,
        keywords,
        settings,
        status,
        relevanceStats,
        groupSummaries,
        availableProviders,
        topics,
        loading: false,
      }));
    } catch (err) {
      setState(prev => ({
        ...prev,
        loading: false,
        error: err instanceof Error ? err.message : 'Failed to load data',
      }));
    }
  }, []);

  // Build group summaries from available data
  const buildGroupSummaries = (
    groups: KeywordGroup[],
    keywords: MonitoredKeyword[],
    relevanceStats: KeywordStats[],
    status: MonitorStatus | null
  ): KeywordGroupSummary[] => {
    return groups.map(group => {
      const groupKeywords = keywords.filter(k => k.group_id === group.id);
      const groupStats = relevanceStats.filter(s => s.group_id === group.id);

      const totalArticles = groupStats.reduce((sum, s) => sum + s.total_matches, 0);
      const avgRelevance = groupStats.length > 0
        ? groupStats.reduce((sum, s) => sum + s.avg_relevance, 0) / groupStats.length
        : 0;
      const highRelevancePct = groupStats.length > 0
        ? groupStats.reduce((sum, s) => sum + s.high_relevance_pct, 0) / groupStats.length
        : 0;

      // Find last checked time from keywords
      const lastCheckedKeyword = groupKeywords
        .filter(k => k.last_checked)
        .sort((a, b) => new Date(b.last_checked!).getTime() - new Date(a.last_checked!).getTime())[0];

      // Determine status
      let statusValue: 'success' | 'error' | 'pending' | 'never_run' = 'never_run';
      if (status?.last_error) {
        statusValue = 'error';
      } else if (lastCheckedKeyword) {
        statusValue = 'success';
      } else if (status?.running) {
        statusValue = 'pending';
      }

      return {
        id: group.id,
        name: group.name,
        topic: group.topic,
        keyword_count: groupKeywords.length,
        total_articles: totalArticles,
        avg_relevance: Math.round(avgRelevance * 100),
        high_relevance_pct: Math.round(highRelevancePct),
        recent_articles_24h: 0, // Would need additional API call
        last_checked: lastCheckedKeyword?.last_checked,
        last_error: status?.last_error,
        status: statusValue,
      };
    });
  };

  // Initial load
  useEffect(() => {
    loadData();
  }, [loadData]);

  // Refresh data
  const refresh = useCallback(() => {
    loadData();
  }, [loadData]);

  // Update settings
  const saveSettings = useCallback(async (newSettings: Partial<KeywordMonitorSettings>) => {
    try {
      // Merge with existing settings to ensure all required fields are present
      const fullSettings = state.settings
        ? { ...state.settings, ...newSettings }
        : newSettings;
      await updateSettings(fullSettings);
      setState(prev => ({
        ...prev,
        settings: prev.settings ? { ...prev.settings, ...newSettings } : null,
      }));
      return true;
    } catch (err) {
      setState(prev => ({
        ...prev,
        error: err instanceof Error ? err.message : 'Failed to save settings',
      }));
      return false;
    }
  }, [state.settings]);

  // Toggle auto-processing
  const toggleAutoProcessing = useCallback(async () => {
    if (!state.settings) return false;

    const newValue = !state.settings.auto_ingest_enabled;
    return saveSettings({ auto_ingest_enabled: newValue });
  }, [state.settings, saveSettings]);

  // Create group
  const createGroup = useCallback(async (name: string, topic: string) => {
    try {
      const newGroup = await createKeywordGroup(name, topic);
      setState(prev => ({
        ...prev,
        groups: [...prev.groups, newGroup],
      }));
      refresh(); // Refresh to get updated summaries
      return newGroup;
    } catch (err) {
      setState(prev => ({
        ...prev,
        error: err instanceof Error ? err.message : 'Failed to create group',
      }));
      return null;
    }
  }, [refresh]);

  // Delete group
  const removeGroup = useCallback(async (groupId: number) => {
    try {
      await deleteKeywordGroup(groupId);
      setState(prev => ({
        ...prev,
        groups: prev.groups.filter(g => g.id !== groupId),
        keywords: prev.keywords.filter(k => k.group_id !== groupId),
        groupSummaries: prev.groupSummaries.filter(s => s.id !== groupId),
      }));
      return true;
    } catch (err) {
      setState(prev => ({
        ...prev,
        error: err instanceof Error ? err.message : 'Failed to delete group',
      }));
      return false;
    }
  }, []);

  // Add keyword to group
  const addKeywordToGroup = useCallback(async (groupId: number, keyword: string) => {
    try {
      const newKeyword = await addKeyword(groupId, keyword);
      setState(prev => ({
        ...prev,
        keywords: [...prev.keywords, newKeyword],
      }));
      refresh(); // Refresh to get updated summaries
      return newKeyword;
    } catch (err) {
      setState(prev => ({
        ...prev,
        error: err instanceof Error ? err.message : 'Failed to add keyword',
      }));
      return null;
    }
  }, [refresh]);

  // Update keyword
  const editKeyword = useCallback(async (keywordId: number, newKeyword: string) => {
    try {
      await updateKeyword(keywordId, newKeyword);
      setState(prev => ({
        ...prev,
        keywords: prev.keywords.map(k =>
          k.id === keywordId ? { ...k, keyword: newKeyword } : k
        ),
      }));
      return true;
    } catch (err) {
      setState(prev => ({
        ...prev,
        error: err instanceof Error ? err.message : 'Failed to update keyword',
      }));
      return false;
    }
  }, []);

  // Remove keyword
  const removeKeyword = useCallback(async (keywordId: number) => {
    try {
      await deleteKeyword(keywordId);
      setState(prev => ({
        ...prev,
        keywords: prev.keywords.filter(k => k.id !== keywordId),
      }));
      refresh(); // Refresh to get updated summaries
      return true;
    } catch (err) {
      setState(prev => ({
        ...prev,
        error: err instanceof Error ? err.message : 'Failed to delete keyword',
      }));
      return false;
    }
  }, [refresh]);

  // Trigger keyword check
  const checkKeywords = useCallback(async (groupId?: number) => {
    setState(prev => ({ ...prev, checkingKeywords: true }));

    try {
      const result = await triggerKeywordCheck(groupId);
      setState(prev => ({ ...prev, checkingKeywords: false }));

      // Refresh data after check
      setTimeout(() => refresh(), 2000);

      return result;
    } catch (err) {
      setState(prev => ({
        ...prev,
        checkingKeywords: false,
        error: err instanceof Error ? err.message : 'Failed to check keywords',
      }));
      return null;
    }
  }, [refresh]);

  // Clear error
  const clearError = useCallback(() => {
    setState(prev => ({ ...prev, error: null }));
  }, []);

  return {
    ...state,
    refresh,
    saveSettings,
    toggleAutoProcessing,
    createGroup,
    removeGroup,
    addKeywordToGroup,
    editKeyword,
    removeKeyword,
    checkKeywords,
    clearError,
  };
}
